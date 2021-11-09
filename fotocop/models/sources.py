import logging
import time

from typing import Optional, Tuple, List,  Union
from dataclasses import dataclass
from enum import IntEnum, Enum, auto
from pathlib import Path
from multiprocessing import Pipe, Event
from threading import Thread

import wmi

from fotocop.util.lru import LRUCache
from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Singleton
from fotocop.models.timeline import Timeline
from fotocop.models.imagescanner import ImageScanner
from fotocop.models.exifloader import ExifLoader

logger = logging.getLogger(__name__)


class SourceType(Enum):
    DEVICE = auto()
    DRIVE = auto()
    UNKNOWN = auto()


class DriveType(IntEnum):
    REMOVABLE = 2
    LOCAL = 3
    NETWORK = 4
    CD = 5


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
    source: Optional[Union[Device, LogicalDisk]] = None
    kind: SourceType = SourceType.UNKNOWN

    THUMBNAIL_CACHE_SIZE = 50

    def __post_init__(self):
        self.images = dict()
        self.timeline = Timeline()
        self.thumbnailCache = LRUCache(Selection.THUMBNAIL_CACHE_SIZE)

        self._requestedExifCount = 0
        self._receivedExifCount = 0

    def __len__(self) -> int:
        return len(self.images)

    @property
    def path(self) -> str:
        source = self.source
        if source is None:
            return ''

        kind = self.kind
        if kind == SourceType.DEVICE:
            return source.logicalDisk.path.as_posix()
        elif kind == SourceType.DRIVE:
            return source.selectedPath.as_posix()
        else:
            return ''

    def updateImages(self, batch: int, images: List[Tuple[str, str]]):
        currentPath = self.path
        newImages = {path: Image(name, path) for name, path in images if path.startswith(currentPath)}
        if newImages:
            self.images.update(newImages)
            logger.debug(f"Received batch: {batch} containing {len(newImages)} images")
            SourceManager().imagesBatchLoaded.emit(
                newImages,
                f"images from batch {batch} containing {len(newImages)} images"
            )

    def loadExifs(self):
        logger.info(f"Loading exif for {self.path}...")
        self._receivedExifCount = 0                                              # noqa
        requestedExifCount = 0
        for n, image in enumerate(self.images.values()):
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
                logger.info(f"Datetime yet loaded for {image.name}: skipped")
        self._requestedExifCount = requestedExifCount                            # noqa
        logger.info(f"{requestedExifCount} exif load requests sent for {self.path}")

    def receiveDatetime(self, imageKey: str, datetime_):
        try:
            image = self.images[imageKey]
        except KeyError:
            # selection has been reset or has changed: ignore old data
            self._receivedExifCount = 0
            logger.debug(f"{imageKey} is not found in current source selection")
        else:
            receivedExifCount = self._receivedExifCount
            requestedExifCount = self._requestedExifCount
            # scanStopped = self.imageScanStopped
            receivedExifCount += 1
            logger.debug(f"Received datetime for image {imageKey} "
                         f"({receivedExifCount}/{requestedExifCount}")
            image.datetime = datetime_
            image.loadingInProgress = False
            self.addToTimeline(datetime_, receivedExifCount)
            if receivedExifCount == requestedExifCount:
                receivedExifCount = 0
            self._receivedExifCount = receivedExifCount                          # noqa

    def addToTimeline(self, dateTime: Tuple[str, str, str, str, str, str], imageIndex):
        self.timeline.addDatetime(dateTime)
        SourceManager().datetimeLoaded.emit(imageIndex, self._requestedExifCount)

    def receiveThumbnail(self, imageKey: int, thumbnail):
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


@dataclass()
class Image:
    name: str
    path: str

    def __post_init__(self):
        self.isSelected: bool = True
        self._datetime: Optional[Tuple[str, str, str, str, str, str]] = None
        self.loadingInProgress = False

    @property
    def isLoaded(self) -> bool:
        return self._datetime is not None

    @property
    def datetime(self) -> Optional[Tuple[str, str, str, str, str, str]]:
        if self._datetime is None:
            if not self.loadingInProgress:
                logger.debug(f"Datetime cache missed for image: {self.name}")
                self.loadingInProgress = True   # noqa
                SourceManager().exifLoaderConnection.send(
                    (ExifLoader.Command.LOAD_DATE, (self.name, self.path))
                )
            else:
                logger.debug(f"Loading in progress: {self.name}")
        return self._datetime

    @datetime.setter
    def datetime(self, value: Optional[Tuple[str, str, str, str, str, str]]):
        self._datetime = value  # noqa

    def getExif(self, command: ExifLoader.Command):
        SourceManager().exifLoaderConnection.send(
            (command, (self.name, self.path))
        )

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
                self.loadingInProgress = True   # noqa
                # Load date/time only if not yet loaded to avoid double count in the timeline
                if self._datetime is None:
                    command = ExifLoader.Command.LOAD_ALL
                else:
                    command = ExifLoader.Command.LOAD_THUMB
                sourceManager.exifLoaderConnection.send(
                    (command, (name, path))
                )
            else:
                logger.debug(f"Loading in progress: {name}")
            return "loading", 0.0, 0
        else:
            logger.debug(f"Got image: {self.name} {aspectRatio} {orientation} from cache")
            return imgdata, aspectRatio, orientation


class ImageScannerListener(Thread):
    def __init__(self, conn):
        super().__init__()
        self.name = "ImageScannerListener"
        self.imageLoaderConnection = conn
        self.alive = Event()

    def run(self):
        self.alive.set()
        while self.alive.is_set():
            try:
                if self.imageLoaderConnection.poll(timeout=0.01):
                    header, data = self.imageLoaderConnection.recv()
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
        self.imageLoaderConnection.close()
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

                    elif content == 'thumbnail':
                        sourceManager.selection.receiveThumbnail(imageKey, data)

                    else:
                        logger.warning(f"Received unknown content: {content}")

            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        self.exifLoaderConnection.close()
        super().join(timeout)


class SourceManager(metaclass=Singleton):

    sourceSelected = QtUtil.QtSignalAdapter(Selection)
    imageScanCompleted = QtUtil.QtSignalAdapter(int)        # imagesCount
    imagesBatchLoaded = QtUtil.QtSignalAdapter(dict, str)   # images, msg
    thumbnailLoaded = QtUtil.QtSignalAdapter(str)           # name
    datetimeLoaded = QtUtil.QtSignalAdapter(int, int)

    def __init__(self):
        self.devices = dict()
        self.logicalDisks = dict()

        self.selection = Selection()

        # Start the image scanner process and establish a Pipe connection with it
        logger.info("Starting image scanner...")
        imageScannerConnection, child_conn1 = Pipe()
        self.imageScannerConnection = imageScannerConnection
        self.imageScanner = ImageScanner(child_conn1)
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

    def enumerateSources(self, kind: Tuple[DriveType] = None):
        kind = kind or tuple(DriveType)

        # https://docs.microsoft.com/fr-fr/windows/win32/wmisdk/wmi-tasks--disks-and-file-systems
        # https://stackoverflow.com/questions/123927/how-to-find-usb-drive-letter
        c = wmi.WMI()

        self.devices.clear()
        self.logicalDisks.clear()
        for logicalDisk in c.Win32_LogicalDisk():
            if logicalDisk.DriveType in kind and logicalDisk.FileSystem:
                drive = LogicalDisk(
                    logicalDisk.DeviceId,
                    logicalDisk.VolumeName,
                    logicalDisk.ProviderName,
                    logicalDisk.Description,
                    logicalDisk.DriveType,
                )
                self.logicalDisks[logicalDisk.DeviceId] = drive

                if logicalDisk.DriveType == DriveType.REMOVABLE:
                    name = (
                        logicalDisk.ProviderName
                        or logicalDisk.VolumeName
                        or logicalDisk.Description
                    )
                    self.devices[name] = Device(name, drive)

    def getDevices(self) -> List[Device]:
        return list(self.devices.values())

    def getDrives(self) -> List[LogicalDisk]:
        return list(self.logicalDisks.values())

    def selectDevice(self, name: str, eject: bool = False):
        self.stopScannning()
        try:
            device = self.devices[name]
        except KeyError:
            self.selection = Selection()
        else:
            self.selection = Selection(device, SourceType.DEVICE)
            self.selection.source.eject = eject
            path = self.selection.source.logicalDisk.path
            self.scanImages(path, includeSubDirs=True)

        self.sourceSelected.emit(self.selection)

    def selectDrive(self, driveId: str, path: Path, subDirs: bool = False):
        self.stopScannning()
        try:
            drive = self.logicalDisks[driveId]
        except KeyError:
            self.selection = Selection()
        else:
            self.selection = Selection(drive, SourceType.DRIVE)
            self.selection.source.selectedPath = path
            self.selection.source.subDirs = subDirs
            self.scanImages(path, subDirs)

        self.sourceSelected.emit(self.selection)

    def setDriveSubDirsState(self, state: bool):
        selection = self.selection
        source = selection.source
        kind = selection.kind
        if source and kind == SourceType.DRIVE:
            self.selectDrive(source.id, Path(selection.path), subDirs=state)

    def setDeviceEjectState(self, state: bool):
        source = self.selection.source
        kind = self.selection.kind
        if source and kind == SourceType.DEVICE:
            source.eject = state

    def scanImages(self, path: Path, includeSubDirs: bool = False):
        self.imageScannerConnection.send(
            (ImageScanner.Command.SCAN, (path.as_posix(), includeSubDirs))
        )

    def stopScannning(self):
        self.imageScannerConnection.send(
            (ImageScanner.Command.ABORT, 0)
        )

    def scanComplete(self, imagesCount: int, isStopped: bool):
        logger.info(f"All batches received: {imagesCount} images - "
                    f"Status: {'stopped' if isStopped else 'complete'}")
        if not isStopped:
            self.imageScanCompleted.emit(imagesCount)
            self.selection.loadExifs()

    def close(self):
        timeline = self.selection.timeline
        print(timeline, timeline.childCount(), timeline.maxWeightByDepth)
        for year in self.selection.timeline:
            print("Year ", year)
            for month in year:
                print("  Month ", month)
                for day in month:
                    print("    Day ", day)
                    for hour in day:
                        print("      Hour ", hour)
        self.imageScannerConnection.send((ImageScanner.Command.STOP, 0))
        self.imageScannerConnection.close()
        self.imagesScannerListener.join()
        self.exifLoaderConnection.send((ExifLoader.Command.STOP, 0))
        self.exifLoaderConnection.close()
        self.exifLoaderListener.join()

    @staticmethod
    def eject():
        from win32comext.shell import shell, shellcon

        shell.SHChangeNotify(
            shellcon.SHCNE_DRIVEREMOVED, shellcon.SHCNF_PATH, str.encode("L:\\")
        )
