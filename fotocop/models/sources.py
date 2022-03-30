import logging

from typing import Optional, Tuple, List, Dict, Union, NamedTuple
from dataclasses import dataclass
from enum import IntEnum, Enum, auto
from datetime import datetime
from pathlib import Path
from multiprocessing import Pipe, Event
from threading import Thread

import wmi

from fotocop.util.cache import LRUCache
from fotocop.util import qtutil as QtUtil
from fotocop.util.threadutil import StoppableThread
from fotocop.util.basicpatterns import Singleton
from fotocop.models import settings as Config
from fotocop.models.timeline import Timeline
from fotocop.models.imagescanner import ImageScanner
from fotocop.models.exifloader import ExifLoader
from fotocop.models.sqlpersistence import DownloadedDB

__all__ = [
    "SourceType",
    "DriveType",
    "Selection",
    "Image",
    "SourceManager",
    "Datation",
    "Source",
    "Device",
    "LogicalDisk",
    "ImageProperty",
    "DownloadInfo",
    "ImageKey",
]


logger = logging.getLogger(__name__)

Source = Optional[Union["Device", "LogicalDisk"]]
ImageKey = str


class SourceType(Enum):
    DEVICE = auto()
    DRIVE = auto()
    UNKNOWN = auto()


class DriveType(IntEnum):
    REMOVABLE = 2
    LOCAL = 3
    NETWORK = 4
    CD = 5


class ImageProperty(Enum):
    NAME = auto()
    PATH = auto()
    THUMBNAIL = auto()
    DATETIME = auto()
    IS_SELECTED = auto()
    SESSION = auto()
    DOWNLOAD_INFO = auto()


@dataclass()
class LogicalDisk:
    id: str
    volumeName: str
    providerName: str
    description: str
    kind: DriveType

    def __post_init__(self):
        if self.kind == DriveType.NETWORK:
            self.name: str = self.providerName.split("\\")[-1]
            self.path: Path = Path("\\".join(self.providerName.split("\\")[:-1]))
            self.caption: str = f"{self.name} ({self.path}) ({self.id})"
        else:
            self.name: str = self.volumeName or self.description
            self.path: Path = Path(f"{self.id}\\")
            self.caption: str = f"{self.name} ({self.id})"

        self.selectedPath: Optional[Path] = None
        self.subDirs: bool = False


@dataclass()
class Device:
    name: str
    logicalDisk: LogicalDisk

    def __post_init__(self):
        self.caption = f"{self.name} ({self.logicalDisk.id})"

        self.eject: bool = False


@dataclass()
class Selection:
    source: Source = None
    kind: SourceType = SourceType.UNKNOWN

    THUMBNAIL_CACHE_SIZE = 10000

    def __post_init__(self):
        self.images: Dict[ImageKey, Image] = dict()
        self.timeline = Timeline()
        self.thumbnailCache = LRUCache(Selection.THUMBNAIL_CACHE_SIZE)

        self.selectedImagesCount = 0

        self.imagesCount = -1
        self._receivedExifCount = 0

    @property
    def path(self) -> str:
        source = self.source
        if source is None:
            return ""

        kind = self.kind
        if kind == SourceType.DEVICE:
            return source.logicalDisk.path.as_posix()
        elif kind == SourceType.DRIVE:
            return source.selectedPath.as_posix()
        else:
            return ""

    def getImageProperty(self, imageKey: "ImageKey", pty: ImageProperty):
        if pty is ImageProperty.NAME:
            return self.images[imageKey].name

        elif pty is ImageProperty.PATH:
            return self.images[imageKey].path

        elif pty is ImageProperty.THUMBNAIL:
            return self.images[imageKey].getThumbnail()

        elif pty is ImageProperty.DATETIME:
            datetime_ = self.images[imageKey].datetime
            if datetime_ is not None:
                return datetime_.asDatetime()
            return None

        elif pty is ImageProperty.IS_SELECTED:
            return self.images[imageKey].isSelected

        elif pty is ImageProperty.SESSION:
            return self.images[imageKey].session

        elif pty is ImageProperty.DOWNLOAD_INFO:
            image = self.images[imageKey]
            return DownloadInfo(
                image.isPreviouslyDownloaded, image.downloadPath, image.downloadTime
            )

        else:
            logger.warning(f"Unknown image property: {pty}")

    def updateImages(self, batch: int, images: List[Tuple[str, str, str, datetime]]):
        currentPath = self.path
        newImages = {
            path: Image(name, path, downloadPath, downloadTime)
            for name, path, downloadPath, downloadTime in images
            if path.startswith(currentPath)
        }
        if newImages:
            self.images.update(newImages)
            # New images are selected by default
            self.selectedImagesCount += len(newImages)
            logger.debug(f"Received batch: {batch} containing {len(newImages)} images")
            SourceManager().imagesBatchLoaded.emit(newImages)

    def receiveDatetime(
        self, imageKey: ImageKey, datetime_: Tuple[str, str, str, str, str, str]
    ):
        try:
            image = self.images[imageKey]
        except KeyError:
            # selection has been reset or has changed: ignore old data
            logger.debug(f"{imageKey} is not found in current source selection")
        else:
            sourceManager = SourceManager()
            receivedExifCount = self._receivedExifCount
            imagesCount = self.imagesCount
            receivedExifCount += 1
            logger.debug(
                f"Received datetime for image {imageKey} "
                f"({receivedExifCount}/{imagesCount})"
            )
            image.datetime = Datation(*datetime_)
            # image.datetime = datetime_
            image.loadingInProgress = False
            self.timeline.addDatetime(datetime_)
            sourceManager.backgroundActionProgressChanged.emit(receivedExifCount)
            if receivedExifCount % 100 == 0:
                sourceManager.datetimeLoaded.emit()
            if 0 < imagesCount == receivedExifCount:
                sourceManager.backgroundActionCompleted.emit("Timeline built!")
                receivedExifCount = 0
                sourceManager.timelineBuilt.emit()
                sourceManager._buildTimelineInProgress = False
            self._receivedExifCount = receivedExifCount  # noqa

    def receiveThumbnail(self, imageKey: ImageKey, thumbnail):
        try:
            image = self.images[imageKey]
        except KeyError:
            # selection has been reset or has changed: ignore old data
            logger.debug(f"{imageKey} is not found in current source selection")
        else:
            logger.debug(f"Received thumbnail for image {imageKey}")
            self.thumbnailCache[image.path] = thumbnail
            image.loadingInProgress = False
            SourceManager().thumbnailLoaded.emit(imageKey)

    def setImagesSelectedState(self, imageKeys: List[ImageKey], value: bool) -> None:
        for imageKey in imageKeys:
            self.images[imageKey].isSelected = value

        SourceManager().imagesSelectionChanged.emit()

    def setImagesSession(self, imageKeys: List[ImageKey], value: str) -> None:
        for imageKey in imageKeys:
            self.images[imageKey].session = value

        SourceManager().imagesSessionChanged.emit()

    def markImagesAsPreviouslyDownloaded(self, imageKeys: List[ImageKey]) -> None:
        records = list()
        now = datetime.now()

        for imageKey in imageKeys:
            image = self.images[imageKey]
            if not image.isPreviouslyDownloaded:
                image.isPreviouslyDownloaded = True  # noqa
                image.isSelected = False
                image.downloadPath = "."
                image.downloadTime = now
                name = image.name
                stat = Path(image.path).stat()
                size = stat.st_size
                mtime = stat.st_mtime
                records.append((name, size, mtime, ".", now))

        SourceManager().downloadedDb.addDownloadedFiles(records)


class Datation(NamedTuple):
    year: str
    month: str
    day: str
    hour: str
    minute: str
    second: str

    def asDatetime(self) -> datetime:
        return datetime(*[int(s) for s in self])


class DownloadInfo(NamedTuple):
    isPreviouslyDownloaded: bool
    downloadPath: Optional[str]
    downloadTime: Optional[datetime]


@dataclass()
class Image:
    name: str
    path: str
    downloadPath: str = None
    downloadTime: datetime = None

    def __post_init__(self):
        self.extension = Path(self.name).suffix
        self.stem = Path(self.name).stem
        self.isPreviouslyDownloaded: bool = False
        self._isSelected: bool = True
        self._datetime: Optional[Datation] = None
        self._session = ""
        self.loadingInProgress = False

        if self.downloadPath is not None:
            self.isPreviouslyDownloaded = True
            self.isSelected = False

    @property
    def isLoaded(self) -> bool:
        return self._datetime is not None

    @property
    def isSelected(self) -> bool:
        return self._isSelected

    @isSelected.setter
    def isSelected(self, value: bool):
        old = self._isSelected
        if value != old:
            self._isSelected = value  # noqa
            sel = 1 if value else -1
            SourceManager().selection.selectedImagesCount += sel

    @property
    def datetime(self) -> Optional[Datation]:
        if self._datetime is None:
            if not self.loadingInProgress:
                logger.debug(f"Datetime cache missed for image: {self.name}")
                self.loadingInProgress = True  # noqa
                SourceManager().exifLoaderConnection.send(
                    (ExifLoader.Command.LOAD_DATE, (self.name, self.path))
                )
            else:
                logger.debug(f"Loading in progress: {self.name}")
        return self._datetime

    @datetime.setter
    def datetime(self, value: Optional[Datation]):
        self._datetime = value  # noqa

    @property
    def session(self) -> str:
        return self._session

    @session.setter
    def session(self, value: str) -> None:
        old = self._session
        if value != old:
            self._session = value  # noqa

    def getExif(self, command: ExifLoader.Command):
        SourceManager().exifLoaderConnection.send((command, (self.name, self.path)))

    def getThumbnail(self) -> Tuple[Optional[Union[bytes, str]], float, int]:
        name = self.name
        path = self.path
        sourceManager = SourceManager()
        thumbnailCache = sourceManager.selection.thumbnailCache
        try:
            imgdata, aspectRatio, orientation = thumbnailCache[path]
        except KeyError:
            if not self.loadingInProgress:
                logger.debug(f"Thumbnail cache missed for image: {name}")
                self.loadingInProgress = True  # noqa
                # Load date/time only if not yet loaded to avoid double count in the timeline
                if self._datetime is None:
                    command = ExifLoader.Command.LOAD_ALL
                else:
                    command = ExifLoader.Command.LOAD_THUMB
                sourceManager.exifLoaderConnection.send((command, (name, path)))
            else:
                logger.debug(f"Loading in progress: {name}")
            return "loading", 0.0, 0
        else:
            logger.debug(
                f"Got image: {self.name} {aspectRatio} {orientation} from cache"
            )
            return imgdata, aspectRatio, orientation


class ImageScannerListener(Thread):
    def __init__(self, conn):
        super().__init__()
        self.name = "ImageScannerListener"
        self.imageScannerConnection = conn
        self.alive = Event()

    def run(self):
        self.alive.set()
        while self.alive.is_set():
            try:
                if self.imageScannerConnection.poll(timeout=0.01):
                    header, data = self.imageScannerConnection.recv()
                    content, batch = header.split("#")

                    if content == "images":

                        if batch == "ScanComplete":
                            # All images received for current selection
                            SourceManager().scanComplete(*data)
                        else:
                            # New images batch received for current selection
                            SourceManager().selection.updateImages(batch, data)

                    else:
                        logger.warning(f"Received unknown content: {content}")

            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        super().join(timeout)


class ExifLoaderListener(Thread):
    def __init__(self, conn):
        super().__init__()
        self.name = "ExifLoaderListener"
        self.exifLoaderConnection = conn
        self.alive = Event()

    def run(self):
        self.alive.set()
        while self.alive.is_set():
            try:
                if self.exifLoaderConnection.poll(timeout=0.01):
                    content, data, imageKey = self.exifLoaderConnection.recv()
                    sourceManager = SourceManager()

                    if content == "datetime":
                        sourceManager.selection.receiveDatetime(imageKey, data)

                    elif content == "thumbnail":
                        sourceManager.selection.receiveThumbnail(imageKey, data)

                    else:
                        logger.warning(f"Received unknown content: {content}")

            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        super().join(timeout)


class ExifRequestor(StoppableThread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "ExifRequestor"

    def run(self):
        try:
            self.requestExif()
        except (OSError, EOFError, BrokenPipeError):
            pass

    def requestExif(self):
        sourceManager = SourceManager()
        selection = sourceManager.selection
        imagesCount = selection.imagesCount
        logger.info(f"Loading exif for {selection.path}...")
        sourceManager.backgroundActionStarted.emit(
            f"Building timeline for {imagesCount} images...", imagesCount
        )
        requestedExifCount = 0
        stopped = False
        for image in selection.images.values():
            if self.stopped():
                logger.info(f"Stop requesting exif for {selection.path}")
                stopped = True
                break
            if not image.isLoaded and not image.loadingInProgress:
                image.loadingInProgress = True
                requestedExifCount += 1
                if requestedExifCount < Selection.THUMBNAIL_CACHE_SIZE:
                    # Load both datetime and thumbnail while the thumbnails cache is not full.
                    image.getExif(ExifLoader.Command.LOAD_ALL)
                else:
                    # Load only datetime once the thumbnails cache is full.
                    image.getExif(ExifLoader.Command.LOAD_DATE)
            else:
                logger.debug(
                    f"Datetime yet loaded or in progress for {image.name}: skipped"
                )
        if not stopped:
            logger.info(
                f"{requestedExifCount} exif load requests sent for {selection.path}"
            )


class SourceManager(metaclass=Singleton):

    sourceEnumerated = QtUtil.QtSignalAdapter()
    sourceSelected = QtUtil.QtSignalAdapter(Selection)
    imageScanCompleted = QtUtil.QtSignalAdapter(int)  # imagesCount
    imagesBatchLoaded = QtUtil.QtSignalAdapter(dict)  # images
    thumbnailLoaded = QtUtil.QtSignalAdapter(str)  # name
    datetimeLoaded = QtUtil.QtSignalAdapter()
    imagesSelectionChanged = QtUtil.QtSignalAdapter()
    imagesSessionChanged = QtUtil.QtSignalAdapter()
    timelineBuilt = QtUtil.QtSignalAdapter()
    backgroundActionStarted = QtUtil.QtSignalAdapter(str, int)  # msg, max value
    backgroundActionProgressChanged = QtUtil.QtSignalAdapter(int)  # progress value
    backgroundActionCompleted = QtUtil.QtSignalAdapter(str)  # msg

    def __init__(self):
        self.devices = dict()
        self.logicalDisks = dict()

        self.selection = Selection()
        self._scanInProgress = False
        self._buildTimelineInProgress = False
        self._exifRequestor = None

        self.downloadedDb = DownloadedDB()

        # Start the image scanner process and establish a Pipe connection with it
        logger.info("Starting image scanner...")
        imageScannerConnection, child_conn1 = Pipe()
        self.imageScannerConnection = imageScannerConnection
        self.imageScanner = ImageScanner(child_conn1, self.downloadedDb)
        self.imageScanner.start()
        child_conn1.close()

        # Start a thread listening to the imageScanner process messages
        self.imagesScannerListener = ImageScannerListener(imageScannerConnection)
        self.imagesScannerListener.start()

        # Start the exif loader process and establish a Pipe connection with it
        logger.info("Starting exif loader...")
        exifLoaderConnection, child_conn2 = Pipe()
        self.exifLoaderConnection = exifLoaderConnection
        self.exifLoader = ExifLoader(child_conn2)
        self.exifLoader.start()
        child_conn2.close()

        # Start a thread listening to the exifLoader process messages
        self.exifLoaderListener = ExifLoaderListener(exifLoaderConnection)
        self.exifLoaderListener.start()

    def enumerateSources(self, kind: Tuple[DriveType] = None, noSignal: bool = False):
        kind = kind or tuple(DriveType)

        # https://docs.microsoft.com/fr-fr/windows/win32/wmisdk/wmi-tasks--disks-and-file-systems
        # http://timgolden.me.uk/python/wmi/tutorial.html
        # https://stackoverflow.com/questions/123927/how-to-find-usb-drive-letter
        # https://stackoverflow.com/questions/14428707/python-function-is-unable-to-run-in-new-thread/14428972
        # Get a connection to the local machine Windows Management Instrumentation
        c = wmi.WMI()

        # If call after first source manager initialization, abort any images scanning,
        # exif loading, clear the selection and logicalDisks and devices dictionary.
        self._reset()

        for logicalDisk in c.Win32_LogicalDisk():
            # Capture only disk of the requested type, with an effective filesystem
            # (exclude DVD reader with no DCD inserted)
            if logicalDisk.DriveType in kind and logicalDisk.FileSystem:
                drive = LogicalDisk(
                    logicalDisk.DeviceId,  # F:
                    logicalDisk.VolumeName,  # Data
                    logicalDisk.ProviderName,  # \\DiskStation\homes\Maison (for a network drive)
                    logicalDisk.Description,  # Disque fixe local
                    logicalDisk.DriveType,  # 3
                )
                self.logicalDisks[logicalDisk.DeviceId] = drive

                # Removable logical disks are also referred as Devices (e.g. USB disk or SD card)
                if logicalDisk.DriveType == DriveType.REMOVABLE:
                    name = (
                        logicalDisk.ProviderName
                        or logicalDisk.VolumeName
                        or logicalDisk.Description
                    )
                    self.devices[name] = Device(name, drive)

        if not noSignal:
            self.sourceEnumerated.emit()

        # Re-select the previous source if any
        # self.selectLastSource(Config.fotocopSettings.lastSource)

    def getSources(
        self, enumerateFirst: bool = False
    ) -> Tuple[List[Device], List[LogicalDisk]]:
        if enumerateFirst:
            # Enumeration required or sources not yet enumerated: do it! (do not test on
            # self.devices as it may be empty after sources enumeration if no devices
            # are connected).
            self.enumerateSources(noSignal=True)

        return list(self.devices.values()), list(self.logicalDisks.values())

    def selectLastSource(self, lastSource: Tuple[str, str, str, bool]):
        sourceType = SourceType[lastSource[1]]

        if sourceType == SourceType.DEVICE:
            self.selectDevice(lastSource[0])

        elif sourceType == SourceType.DRIVE:
            self.selectDrive(lastSource[0], Path(lastSource[2]), lastSource[3])

        else:
            self.sourceSelected.emit(Selection())

    def selectDevice(self, name: str, eject: bool = False):
        # Abort any exif loading or images scanning before changing the selection
        self._abortExifLoading()
        self._abortScannning()

        try:
            device = self.devices[name]

        except KeyError:
            # If the selected device is not found, change to an empty selection
            self.selection = Selection()

        else:
            # Set the device as the selection with its eject status and start to scan
            # images on the corresponding path (including subfolders)
            self.selection = Selection(device, SourceType.DEVICE)
            self.selection.source.eject = eject
            path = self.selection.source.logicalDisk.path
            self._scanImages(path, includeSubDirs=True)

        self._addToRecentSources(self.selection.source, self.selection.kind)
        self.sourceSelected.emit(self.selection)

    def selectDrive(self, driveId: str, path: Path, subDirs: bool = False):
        # Abort any exif loading or images scanning before changing the selection
        self._abortExifLoading()
        self._abortScannning()

        try:
            drive = self.logicalDisks[driveId]

        except KeyError:
            # If the selected device is not found, change to an empty selection
            self.selection = Selection()

        else:
            # Set the drive as the selection with its subfolders status and path
            # and start images scanning on that path (including subfolders)
            self.selection = Selection(drive, SourceType.DRIVE)
            self.selection.source.selectedPath = path
            self.selection.source.subDirs = subDirs
            self._scanImages(path, subDirs)

        self._addToRecentSources(self.selection.source, self.selection.kind)
        self.sourceSelected.emit(self.selection)

    def setDriveSubDirsState(self, state: bool):
        # If a drive is selected, re-select it but with the new subfolders state
        selection = self.selection
        source = selection.source
        kind = selection.kind
        if source and kind == SourceType.DRIVE:
            self.selectDrive(source.id, Path(selection.path), subDirs=state)

    def setDeviceEjectState(self, state: bool):
        # If a device is selected, update its eject property to 'state'
        source = self.selection.source
        kind = self.selection.kind
        if source and kind == SourceType.DEVICE:
            source.eject = state

    def scanComplete(self, imagesCount: int, isStopped: bool):
        # Call by the images' scanner listener when the scan process is finished (either
        # complete or stopped)
        logger.info(
            f"All batches received: {imagesCount} images - "
            f"Status: {'stopped' if isStopped else 'complete'}"
        )
        if not isStopped:
            # Store the images count of the selection and, if at least an images is
            # found, start to build the timeline by requesting exif data in a
            # dedicated thread
            self._scanInProgress = False
            self.backgroundActionCompleted.emit(f"Found {imagesCount} images")
            self.selection.imagesCount = imagesCount
            self.imageScanCompleted.emit(imagesCount)
            if imagesCount > 0:
                self._exifRequestor = ExifRequestor()
                self._exifRequestor.start()
                self._buildTimelineInProgress = True

    def close(self):
        # Organize a kindly shutdown when quitting the application

        # Stop and join the exif requestor thread
        self._stopExifRequestor()

        # Stop and join the images' scanner process ant its listener thread
        logger.info("Request images scanner to stop...")
        self.imageScannerConnection.send((ImageScanner.Command.STOP, 0))
        self.imageScanner.join(timeout=0.25)
        if self.imageScanner.is_alive():
            self.imageScanner.terminate()
        self.imageScannerConnection.close()
        self.imagesScannerListener.join()

        # Stop and join the exif loader process ant its listener thread
        logger.info("Request exif loader to stop...")
        self.exifLoaderConnection.send((ExifLoader.Command.STOP, 0))
        # timeout is set to 5s to give time to the exiftool process to kindly terminate
        self.exifLoader.join(timeout=5)
        self.exifLoaderConnection.close()
        self.exifLoaderListener.join()

    def _reset(self):
        self._abortExifLoading()
        self._abortScannning()
        self.selection = Selection()
        self.devices.clear()
        self.logicalDisks.clear()

    def _scanImages(self, path: Path, includeSubDirs: bool = False):
        self.backgroundActionStarted.emit(f"Scanning {path} for images...", 0)
        self.imageScannerConnection.send(
            (ImageScanner.Command.SCAN, (path.as_posix(), includeSubDirs))
        )
        self._scanInProgress = True

    def _abortScannning(self):
        if self._scanInProgress:
            # Scanning in progress: abort it
            self.backgroundActionCompleted.emit(f"Images scanning aborted!")
            self.imageScannerConnection.send((ImageScanner.Command.ABORT, 0))
            self._scanInProgress = False

    def _abortExifLoading(self):
        if self._buildTimelineInProgress:
            self.backgroundActionCompleted.emit(f"Timeline building aborted!")
            self._exifRequestor.stop()
            self._exifRequestor = None
            self._buildTimelineInProgress = False

    def _stopExifRequestor(self):
        exifRequestor = self._exifRequestor
        if exifRequestor and exifRequestor.is_alive():
            logger.info("Stopping exif requestor...")
            exifRequestor.stop()
            exifRequestor.join(timeout=0.5)
            if exifRequestor.is_alive():
                logger.warning("Cannot join exif requestor")
            else:
                logger.info("Exif requestor stopped")
        else:
            logger.info("Exif requestor no more running")

    @staticmethod
    def _addToRecentSources(source: Source, kind: SourceType):
        if source:
            if kind == SourceType.DRIVE:
                name = source.id
                path = source.selectedPath
                subDirs = source.subDirs
            elif kind == SourceType.DEVICE:
                name = source.name
                path = subDirs = None
            else:  # for robustness but cannot be reached
                name = path = subDirs = None
        else:
            name = path = subDirs = None
        Config.fotocopSettings.lastSource = (name, kind.name, path, subDirs)
