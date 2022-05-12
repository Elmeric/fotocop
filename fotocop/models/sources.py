"""The images' sources management model.

The SourceManager singleton enumerates images' sources connected to the computer.
Each found source is saved into a dedicated dict:
- devices: the connected removable logical disks (e.g. USB disk or SD card), identified
    by their name
- logicalDisks: the mappped drives (e.g. local HDD, DVD reader or network drive),
    identified by their device id (drive letter)

"""
import logging

from typing import Optional, Tuple, List, Dict, NamedTuple, Any, Iterator
from dataclasses import dataclass
from enum import IntEnum, Enum, auto
from datetime import datetime
from pathlib import Path
from multiprocessing import Pipe

import wmi

from fotocop.util.cache import LRUCache
from fotocop.util import qtutil as QtUtil
from fotocop.util.threadutil import StoppableThread, ConnectionListener
from fotocop.util.basicpatterns import Singleton
from fotocop.models import settings as Config
from fotocop.models.timeline import Timeline
from fotocop.models.imagescanner import ImageScanner
from fotocop.models.exifloader import ExifLoader
from fotocop.models.sqlpersistence import DownloadedDB

__all__ = [
    "MediaType",
    "DriveType",
    "Source",
    "Image",
    "SourceManager",
    "Datation",
    "Device",
    "LogicalDisk",
    "ImageProperty",
    "ImageKey",
]


logger = logging.getLogger(__name__)

ImageKey = str


def _makeDefaultImageSample() -> "Image":
    imageSample = Image("IMG_0001.RAF", "L:/path/to/images")
    d = datetime.today()
    imageSample.datetime = Datation(
        str(d.year), str(d.month), str(d.day), str(d.hour), str(d.minute), str(d.second)
    )
    return imageSample


class MediaType(Enum):
    DEVICE = auto()
    LOGICAL_DISK = auto()
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
class Media:
    name: str
    driveLetter: str
    path: Path
    driveType: DriveType

    def __post_init__(self) -> None:
        if self.driveType == DriveType.NETWORK:
            self.caption: str = f"{self.name} ({self.path}) ({self.driveLetter})"
        else:
            self.caption: str = f"{self.name} ({self.driveLetter})"


@dataclass()
class LogicalDisk(Media):
    pass


@dataclass()
class Device(Media):
    pass


class Source:

    THUMBNAIL_CACHE_SIZE = 10000

    media: Optional[Media]
    eject: bool
    selectedPath: Path
    subDirs: bool

    def __init__(self, media: Optional[Media] = None) -> None:
        self.media = media

        self._images: Dict["ImageKey", "Image"] = dict()
        self.imageSample: "Image" = _makeDefaultImageSample()
        self.timeline: "Timeline" = Timeline()
        self._thumbnailCache: "LRUCache" = LRUCache(Source.THUMBNAIL_CACHE_SIZE)

        self.selectedImagesCount: int = 0

        self.imagesCount: int = -1
        self._receivedExifCount: int = 0

        self.timelineBuilt: bool = False

    @classmethod
    def fromDevice(cls, device: Device, eject: bool = False):
        s = cls(device)
        s.eject = eject
        return s

    @classmethod
    def fromLogicalDisk(cls, logicalDisk: LogicalDisk, path: Path, subDirs: bool = False):
        s = cls(logicalDisk)
        s.selectedPath = path
        s.subDirs = subDirs
        return s

    @property
    def isEmpty(self) -> bool:
        return self.media is None

    @property
    def isDevice(self) -> bool:
        return self.media is not None and isinstance(self.media, Device)

    @property
    def isLogicalDisk(self) -> bool:
        return self.media is not None and isinstance(self.media, LogicalDisk)

    @property
    def path(self) -> str:
        if self.isEmpty:
            return ""
        elif self.isDevice:
            return self.media.path.as_posix()
        elif self.isLogicalDisk:
            return self.selectedPath.as_posix()
        else:
            return ""

    @property
    def imageKeys(self) -> Iterator["ImageKey"]:
        return (imageKey for imageKey in self._images.keys())

    @property
    def images(self) -> Iterator["Image"]:
        return (image for image in self._images.values())

    def getImageProperty(self, imageKey: "ImageKey", pty: "ImageProperty") -> Any:
        try:
            image = self._images[imageKey]
        except KeyError:
            logger.warning(
                f"No image for key: {imageKey}, cannot get image property {pty}"
            )
            return

        if pty is ImageProperty.NAME:
            return image.name

        elif pty is ImageProperty.PATH:
            return image.path

        elif pty is ImageProperty.THUMBNAIL:
            return self._getImageThumbnail(imageKey)

        elif pty is ImageProperty.DATETIME:
            return self._getImageDatetime(imageKey)

        elif pty is ImageProperty.IS_SELECTED:
            return image.isSelected

        elif pty is ImageProperty.SESSION:
            return image.session

        elif pty is ImageProperty.DOWNLOAD_INFO:
            return DownloadInfo(
                image.isPreviouslyDownloaded, image.downloadPath, image.downloadTime
            )

        else:
            logger.warning(f"Unknown image property: {pty}")

    def _getImageDatetime(self, imageKey: "ImageKey") -> Optional[datetime]:
        image = self._images[imageKey]
        name = image.name
        datetime_ = image.datetime

        if datetime_ is not None:
            return datetime_.asDatetime()

        if not image.loadingInProgress:
            logger.debug(f"Datetime cache missed for image: {name}")
            image.loadingInProgress = True  # noqa
            SourceManager().exifLoaderConnection.send(
                (ExifLoader.Command.LOAD_DATE, imageKey)
            )
        else:
            logger.debug(f"Loading in progress: {name}")
        return None

    def _getImageThumbnail(
        self, imageKey: "ImageKey"
    ) -> Tuple[bytes, float, int]:
        image = self._images[imageKey]
        name = image.name
        try:
            imgdata, aspectRatio, orientation = self._thumbnailCache[imageKey]
        except KeyError:
            if not image.loadingInProgress:
                logger.debug(f"Thumbnail cache missed for image: {name}")
                image.loadingInProgress = True  # noqa
                # Load date/time only if not yet loaded to avoid double count in the timeline
                if image.datetime is None:
                    command = ExifLoader.Command.LOAD_ALL
                else:
                    command = ExifLoader.Command.LOAD_THUMB
                SourceManager().exifLoaderConnection.send((command, imageKey))
            else:
                logger.debug(f"Loading in progress: {name}")
            return b"loading", 0.0, 0
        else:
            logger.debug(f"Got image: {name} {aspectRatio} {orientation} from cache")
            return imgdata, aspectRatio, orientation

    def receiveImages(
        self, batch: int, images: List[Tuple[str, "ImageKey", str, datetime]]
    ):
        currentPath = self.path
        newImages = dict()
        deselCount = 0
        for name, imageKey, downloadPath, downloadTime in images:
            if imageKey.startswith(currentPath):
                image = Image(name, imageKey, downloadPath, downloadTime)
                if downloadPath is not None:
                    image.isPreviouslyDownloaded = True
                    image.isSelected = False
                    deselCount += 1
                newImages[imageKey] = image

        if newImages:
            self._images.update(newImages)
            # New images are selected except if previously downloaded
            imagesCount = len(newImages)
            self.selectedImagesCount += imagesCount - deselCount
            logger.debug(
                f"Received batch: {batch} containing {imagesCount} images,"
                f" {deselCount} was previously downloaded"
            )
            SourceManager().imagesBatchLoaded.emit(newImages)
            SourceManager().imagesInfoChanged.emit(
                list(newImages), ImageProperty.IS_SELECTED, True
            )

    def receiveDatetime(
        self, imageKey: "ImageKey", datetime_: Tuple[str, str, str, str, str, str]
    ):
        images = self._images
        try:
            image = images[imageKey]
        except KeyError:
            # source has been reset or has changed: ignore old data
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
            image.loadingInProgress = False
            self.timeline.addDatetime(datetime_)
            sourceManager.backgroundActionProgressChanged.emit(receivedExifCount)
            if 0 < imagesCount == receivedExifCount:
                self.imageSample = imageSample = images[next(iter(images))]
                logger.debug(
                    f"Image sample is now: {imageSample.name} "
                    f"in {imageSample.path} "
                    f"with date {imageSample.datetime}"
                )
                logger.info(
                    f"Received exif for {receivedExifCount} images: Timeline built"
                )
                sourceManager.backgroundActionCompleted.emit("Timeline built!")
                receivedExifCount = 0
                self.timelineBuilt = True  # noqa
                sourceManager.timelineBuilt.emit()
                sourceManager.imageSampleChanged.emit()
                sourceManager._buildTimelineInProgress = False
            sourceManager.imagesInfoChanged.emit(
                [imageKey], ImageProperty.DATETIME, image.datetime
            )
            self._receivedExifCount = receivedExifCount  # noqa

    def receiveThumbnail(self, imageKey: "ImageKey", thumbnail):
        try:
            image = self._images[imageKey]
        except KeyError:
            # source has been reset or has changed: ignore old data
            logger.debug(f"{imageKey} is not found in current source selection")
        else:
            logger.debug(f"Received thumbnail for image {imageKey}")
            self._thumbnailCache[imageKey] = thumbnail
            image.loadingInProgress = False
            SourceManager().thumbnailLoaded.emit(imageKey)

    def markImagesAsSelected(self, imageKeys: List["ImageKey"], value: bool) -> None:
        changed = list()
        for imageKey in imageKeys:
            oldValue = self._images[imageKey].isSelected
            if oldValue != value:
                self._images[imageKey].isSelected = value
                changed.append(imageKey)

        sel = 1 if value else -1
        self.selectedImagesCount += sel * len(changed)

        if changed:
            SourceManager().imagesInfoChanged.emit(
                changed, ImageProperty.IS_SELECTED, value
            )

    def getImagesRequiringSession(self) -> List["ImageKey"]:
        return [
            key
            for key, image in self._images.items()
            if image.isSelected and not image.session
        ]

    def setImagesSession(self, imageKeys: List["ImageKey"], value: str) -> None:
        for imageKey in imageKeys:
            self._images[imageKey].session = value

        SourceManager().imagesInfoChanged.emit(imageKeys, ImageProperty.SESSION, value)

    def markImagesAsPreviouslyDownloaded(
        self, imagesInfo: List[Tuple["ImageKey", Optional[datetime], Optional[Path]]]
    ) -> None:
        records = list()
        deselCount = 0
        deselImageKeys = list()
        now = datetime.now()

        for imageKey, downloadTime, downloadPath in imagesInfo:
            if downloadTime is None:
                downloadTime = now
            if downloadPath is None:
                downloadPath = Path(".")
            try:
                image = self._images[imageKey]
            except KeyError as e:
                logger.warning(
                    f"Cannot mark {imageKey} as downloaded: image not found ({e})"
                )
            else:
                image.isPreviouslyDownloaded = True  # noqa
                image.isSelected = False
                deselCount += 1
                deselImageKeys.append(imageKey)
                image.downloadPath = downloadPath.as_posix()
                image.downloadTime = downloadTime
                name = image.name
                stat = Path(image.path).stat()
                size = stat.st_size
                mtime = stat.st_mtime
                records.append(
                    (name, size, mtime, downloadPath.as_posix(), downloadTime)
                )

        SourceManager().downloadedDb.addDownloadedFiles(records)
        if deselCount:
            self.selectedImagesCount -= deselCount
            SourceManager().imagesInfoChanged.emit(
                deselImageKeys, ImageProperty.IS_SELECTED, False
            )


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
        self.extension: str = Path(self.name).suffix
        self.stem: str = Path(self.name).stem
        self.isPreviouslyDownloaded: bool = False
        self.isSelected: bool = True
        self.datetime: Optional[Datation] = None
        self.session: str = ""
        self.loadingInProgress: bool = False

    @property
    def key(self) -> "ImageKey":
        return self.path

    @property
    def isLoaded(self) -> bool:
        return self.datetime is not None


class ImageScannerListener(ConnectionListener):
    def __init__(self, conn):
        super().__init__(conn, name="ImageScannerListener")

    def handleMessage(self, msg: Any) -> None:
        header, data = msg
        content, batch = header.split("#")

        if content == "images":

            if batch == "ScanComplete":
                # All images received for current source
                SourceManager().scanComplete(*data)
            else:
                # New images batch received for current source
                SourceManager().source.receiveImages(batch, data)

        else:
            logger.warning(f"Received unknown content: {content}")


class ExifLoaderListener(ConnectionListener):
    def __init__(self, conn):
        super().__init__(conn, name="ExifLoaderListener")

    def handleMessage(self, msg: Any) -> None:
        content, data, imageKey = msg
        sourceManager = SourceManager()

        if content == "datetime":
            sourceManager.source.receiveDatetime(imageKey, data)

        elif content == "thumbnail":
            sourceManager.source.receiveThumbnail(imageKey, data)

        else:
            logger.warning(f"Received unknown content: {content}")


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
        source = sourceManager.source
        imagesCount = source.imagesCount
        logger.info(f"Loading exif for {source.path}...")
        sourceManager.backgroundActionStarted.emit(
            f"Building timeline for {imagesCount} images...", imagesCount
        )
        requestedExifCount = 0
        stopped = False
        for image in source.images:
            if self.stopped():
                logger.info(f"Stop requesting exif for {source.path}")
                stopped = True
                break
            if not image.isLoaded and not image.loadingInProgress:
                image.loadingInProgress = True
                requestedExifCount += 1
                if requestedExifCount < Source.THUMBNAIL_CACHE_SIZE:
                    # Load both datetime and thumbnail while the thumbnails cache is not full.
                    command = ExifLoader.Command.LOAD_ALL
                else:
                    # Load only datetime once the thumbnails cache is full.
                    command = ExifLoader.Command.LOAD_DATE
                sourceManager.exifLoaderConnection.send((command, image.key))
            else:
                logger.debug(
                    f"Datetime yet loaded or in progress for {image.name}: skipped"
                )
        if not stopped:
            logger.info(
                f"{requestedExifCount} exif load requests sent for {source.path}"
            )


class SourceManager(metaclass=Singleton):

    sourcesChanged = QtUtil.QtSignalAdapter()
    sourceSelected = QtUtil.QtSignalAdapter(Source)
    imageScanCompleted = QtUtil.QtSignalAdapter(int)  # imagesCount
    imagesBatchLoaded = QtUtil.QtSignalAdapter(dict)  # images
    thumbnailLoaded = QtUtil.QtSignalAdapter(str)  # name
    imagesInfoChanged = QtUtil.QtSignalAdapter(
        list, Enum, object
    )  # imageKeys, imageProperty, values
    timelineBuilt = QtUtil.QtSignalAdapter()
    imageSampleChanged = QtUtil.QtSignalAdapter()
    backgroundActionStarted = QtUtil.QtSignalAdapter(str, int)  # msg, max value
    backgroundActionProgressChanged = QtUtil.QtSignalAdapter(int)  # progress value
    backgroundActionCompleted = QtUtil.QtSignalAdapter(str)  # msg

    def __init__(self):
        self._devices = dict()
        self._logicalDisks = dict()

        self.source = Source()
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

    @property
    def devices(self) -> Iterator["Device"]:
        return (device for device in self._devices.values())

    @property
    def logicalDisks(self) -> Iterator["LogicalDisk"]:
        return (logicalDisk for logicalDisk in self._logicalDisks.values())

    def enumerateSources(self, kind: Tuple[DriveType] = None):
        kind = kind or tuple(DriveType)

        # https://docs.microsoft.com/fr-fr/windows/win32/wmisdk/wmi-tasks--disks-and-file-systems
        # http://timgolden.me.uk/python/wmi/tutorial.html
        # https://stackoverflow.com/questions/123927/how-to-find-usb-drive-letter
        # https://stackoverflow.com/questions/14428707/python-function-is-unable-to-run-in-new-thread/14428972

        # for u in wmi.WMI().Win32_USBControllerDevice():
        #     d = u.Dependent
        #     print(d.Manufacturer, d.Name, d.PNPDeviceID)
        # https://stackoverflow.com/questions/21122468/how-do-i-create-an-instance-of-iportabledevicemanager-in-python
        # https://drautb.github.io/2015/07/27/the-perfect-exchange-mtp-with-python/
        # https://stackoverflow.com/questions/64910317/mount-mtp-device-on-windows

        # Get a connection to the local machine Windows Management Instrumentation
        c = wmi.WMI()

        # If call after first source manager initialization, abort any images scanning,
        # exif loading, clear the source and logicalDisks and devices dictionary.
        self._reset()

        for logicalDisk in c.Win32_LogicalDisk():
            # Capture only disk of the requested type, with an effective filesystem
            # (exclude DVD reader with no DVD inserted)
            # logicalDisk.DeviceId:     F:
            # logicalDisk.VolumeName:   Data
            # logicalDisk.ProviderName: \\DiskStation\homes\Maison (for a network drive)
            # logicalDisk.Description:  Disque fixe local
            # logicalDisk.DriveType:    3
            if logicalDisk.DriveType in kind and logicalDisk.FileSystem:
                driveLetter = logicalDisk.DeviceId
                driveType = logicalDisk.DriveType
                if driveType == DriveType.NETWORK:
                    providerName = logicalDisk.ProviderName
                    name = providerName.split("\\")[-1]
                    path = Path("\\".join(providerName.split("\\")[:-1]))
                else:
                    name = logicalDisk.VolumeName or logicalDisk.Description
                    path = Path(f"{driveLetter}\\")
                self._logicalDisks[driveLetter] = LogicalDisk(
                    name, driveLetter, path, driveType
                )

                # Removable logical disks are also referred as Devices (e.g. USB disk or SD card)
                if logicalDisk.DriveType == DriveType.REMOVABLE:
                    name = (
                        logicalDisk.ProviderName
                        or logicalDisk.VolumeName
                        or logicalDisk.Description
                    )
                    path = Path(f"{driveLetter}\\")
                    self._devices[name] = Device(
                        name, driveLetter, path, driveType
                    )

        self.sourcesChanged.emit()
        self._autoSourceSelect()

    def selectDevice(self, name: Optional[str], eject: bool = False):
        if (
            name is not None
            and self.source.isDevice
            and name == self.source.media.name
        ):
            # this device is already the selected one: nothing to do.
            return

        # Abort any exif loading or images scanning before changing the source
        self._abortExifLoading()
        self._abortScannning()

        try:
            device = self._devices[name]

        except KeyError:
            # If the selected device is not found, change to an empty source
            self._resetSelection()

        else:
            # Set the device as the source with its eject status and start to scan
            # images on the corresponding path (including subfolders)
            self.source = Source.fromDevice(device, eject)
            path = Path(self.source.path)
            self._scanImages(path, includeSubDirs=True)

        finally:
            self._addToRecentSources()
            self.sourceSelected.emit(self.source)
            self.imageSampleChanged.emit()

    def selectLogicalDisk(self, driveId: Optional[str], path: Path, subDirs: bool = False):
        source = self.source
        if (
            driveId is not None
            and self.source.isLogicalDisk
            and path == source.selectedPath
            and subDirs == source.subDirs
        ):
            # this drive/folder is already the selected one: nothing to do.
            return

        # Abort any exif loading or images scanning before changing the source
        self._abortExifLoading()
        self._abortScannning()

        try:
            drive = self._logicalDisks[driveId]

        except KeyError:
            # If the selected device is not found, change to an empty source
            self._resetSelection()

        else:
            # Set the drive as the source with its subfolders status and path
            # and start images scanning on that path (including subfolders)
            self.source = Source.fromLogicalDisk(drive, path, subDirs)
            self._scanImages(path, subDirs)

        finally:
            self._addToRecentSources()
            self.sourceSelected.emit(self.source)
            self.imageSampleChanged.emit()

    def setDriveSubDirsState(self, state: bool):
        # If a logical disk is selected, re-select it but with the new subfolders state.
        source = self.source
        media = source.media
        if source.isLogicalDisk:
            self.selectLogicalDisk(media.driveLetter, Path(source.path), subDirs=state)

    def setDeviceEjectState(self, state: bool):
        # If a device is selected, update the eject property to 'state'.
        source = self.source
        if source.isDevice:
            source.eject = state

    def scanComplete(self, imagesCount: int, isStopped: bool):
        # Call by the images' scanner listener when the scan process is finished (either
        # complete or stopped)
        logger.info(
            f"All batches received: {imagesCount} images - "
            f"Status: {'stopped' if isStopped else 'complete'}"
        )
        if not isStopped:
            # Store the images count of the source and, if at least an images is
            # found, start to build the timeline by requesting exif data in a
            # dedicated thread
            self._scanInProgress = False
            self.backgroundActionCompleted.emit(f"Found {imagesCount} images")
            self.source.imagesCount = imagesCount
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

    def _autoSourceSelect(self) -> None:
        srcTypeStr, srcName, srcPath, srcSubDirs = Config.fotocopSettings.lastSource
        srcType = MediaType[srcTypeStr]
        if len(self._devices) < 1:
            # No connected devices: re-select the last selected source if any.
            if srcType == MediaType.DEVICE:
                self.selectDevice(srcName)
            elif srcType == MediaType.LOGICAL_DISK:
                self.selectLogicalDisk(srcName, Path(srcPath), srcSubDirs)
            else:
                self._resetSelection()
                self.sourceSelected.emit(self.source)

        elif srcName in self._devices:
            # At least one device is connected and the devices' dict contains the last
            # selected sources: re-select it.
            self.selectDevice(srcName)

        else:
            # At least one device is connected but not the last selected source: select
            # the first connected device.
            device = next(iter(self._devices.values()))
            self.selectDevice(device.name)

    def _reset(self):
        self._abortExifLoading()
        self._abortScannning()
        self._resetSelection()
        self._devices.clear()
        self._logicalDisks.clear()

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

    def _addToRecentSources(self) -> None:
        source = self.source
        media = source.media
        if source.isEmpty:
            kind = MediaType.UNKNOWN
            name = path = subDirs = None
        elif source.isLogicalDisk:
            kind = MediaType.LOGICAL_DISK
            name = media.driveLetter
            path = source.selectedPath
            subDirs = source.subDirs
        elif source.isDevice:
            kind = MediaType.DEVICE
            name = media.name
            path = subDirs = None
        else:  # for robustness but cannot be reached
            kind = MediaType.UNKNOWN
            name = path = subDirs = None
        Config.fotocopSettings.lastSource = (kind.name, name, path, subDirs)

    def _resetSelection(self) -> None:
        self.source = Source()
        SourceManager().imagesInfoChanged.emit([], ImageProperty.IS_SELECTED, False)
