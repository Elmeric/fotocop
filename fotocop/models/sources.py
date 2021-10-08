import base64
import logging
import time

from typing import Optional, Tuple, List, Union
from dataclasses import dataclass
from enum import IntEnum, Enum, auto
from pathlib import Path
from multiprocessing import Pipe, Event
from threading import Thread, enumerate

import wmi

# from fotocop.util import exiftool
from fotocop.util.lru import LRUCache
from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Singleton
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

    def __post_init__(self):
        self.images = dict()
        self.thumbnailCache = LRUCache(500)

    @property
    def path(self) -> str:
        source = self.source
        kind = self.kind
        if source is None:
            return ''

        if kind == SourceType.DEVICE:
            return source.logicalDisk.path.as_posix()
        elif kind == SourceType.DRIVE:
            return source.selectedPath.as_posix()
        else:
            return ''

    def getImages(self):
        source = self.source
        kind = self.kind
        if source is None:
            return

        if kind == SourceType.DEVICE:
            path = source.logicalDisk.path
            subDirs = True
        elif kind == SourceType.DRIVE:
            path = source.selectedPath
            subDirs = source.subDirs
        else:
            return

        SourceManager().scanImages(path, subDirs)


@dataclass()
class Image:
    name: str
    path: str

    def __post_init__(self):
        self.isSelected: bool = True
        self._datetime: Optional[Tuple[str, str, str, str, str, str]] = None
        self.loadingInProgress = False

    @property
    def datetime(self) -> Optional[Tuple[str, str, str, str, str, str]]:
        if self._datetime is None:
            if not self.loadingInProgress:
                logger.debug(f"Thumbnail cache missed for image: {self.name}")
                self.loadingInProgress = True   # noqa
                SourceManager().exifLoaderConnection.send(
                    (ExifLoader.Command.LOAD_ALL, (self.name, self.path))
                )
            else:
                logger.debug(f"Loading in progress: {self.name}")
        return self._datetime

    @datetime.setter
    def datetime(self, value: Optional[Tuple[str, str, str, str, str, str]]):
        self._datetime = value  # noqa

    def getThumbnail(self) -> Tuple[Optional[bytes], float, int]:
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
                sourceManager.exifLoaderConnection.send(
                    (ExifLoader.Command.LOAD_ALL, (name, path))
                )
            else:
                logger.debug(f"Loading in progress: {name}")
            return "loading", 0, 0
        else:
            logger.debug(f"Got image: {self.name} {aspectRatio} {orientation} from cache")
            return imgdata, aspectRatio, orientation


class ImageScannerListener(Thread):
    def __init__(self, conn, imagesBatchLoaded):
        super().__init__()
        self.imageLoaderConnection = conn
        self.imagesBatchLoaded = imagesBatchLoaded
        self.alive = Event()

    def run(self):
        self.alive.set()
        while self.alive.is_set():
            newImages = dict()
            try:
                if self.imageLoaderConnection.poll(timeout=0.01):
                    # if SourceManager().abortScanning.is_set():
                    #     # logger.info("ImageScannerListener: Image scanning aborted")
                    #     continue
                    currentPath = SourceManager().selection.path
                    k, v = self.imageLoaderConnection.recv()
                    content, batch = k.split("#")
                    if content != "images":
                        continue
                    newImages = {path: Image(name, path) for name, path in v if path.startswith(currentPath)}
                    if newImages:
                        SourceManager().selection.images.update(newImages)
                        logger.debug(f"Received batch: {batch} containing {len(newImages)} images")
                        self.imagesBatchLoaded.emit(
                            newImages,
                            f"images from batch {batch} containing {len(newImages)} images"
                        )
                        for image in newImages.values():
                            # if SourceManager().abortScanning.is_set():
                            #     break
                            image.getThumbnail()
            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        self.imageLoaderConnection.close()
        super().join(timeout)


class ExifLoaderListener(Thread):
    def __init__(self, conn, datetimeLoaded, thumbnailLoaded):
        super().__init__()
        self.exifLoaderConnection = conn
        self.datetimeLoaded = datetimeLoaded
        self.thumbnailLoaded = thumbnailLoaded
        self.alive = Event()

    def run(self):
        self.alive.set()
        while self.alive.is_set():
            try:
                if self.exifLoaderConnection.poll(timeout=0.01):
                    # if SourceManager().abortScanning.is_set():
                    #     # logger.info("ExifLoaderListener: Exif loading aborted")
                    #     continue
                    content, data, imageKey = self.exifLoaderConnection.recv()
                    sourceManager = SourceManager()
                    try:
                        image = sourceManager.selection.images[imageKey]
                    except KeyError:
                        # selection has been reset or has changed: ignore old data
                        logger.debug(f"{imageKey} is not found in current source selection")
                        continue
                    else:
                        if content == "datetime":
                            logger.debug(f"Received datetime for image {imageKey}")
                            image.datetime = data
                            self.datetimeLoaded.emit(imageKey)
                        elif content == "thumbnail":
                            logger.debug(f"Received thumbnail for image {imageKey}")
                            sourceManager.selection.thumbnailCache[image.path] = data
                            image.loadingInProgress = False
                            self.thumbnailLoaded.emit(imageKey)
                        else:
                            logger.warning(f"Received unknown content: {content}")
                            continue
            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        self.exifLoaderConnection.close()
        super().join(timeout)


class SourceManager(metaclass=Singleton):

    sourceSelected = QtUtil.QtSignalAdapter(Selection)
    imagesBatchLoaded = QtUtil.QtSignalAdapter(dict, str)   # images, msg
    thumbnailLoaded = QtUtil.QtSignalAdapter(str)           # name
    datetimeLoaded = QtUtil.QtSignalAdapter(str)            # name

    def __init__(self):
        self.devices = dict()
        self.logicalDisks = dict()

        self.selection = Selection()

        # Start the image scanner process and establish a Pipe connection with it
        logger.info("Starting image scanner...")
        imageScannerConnection, child_conn1 = Pipe()
        self.scanInProgress = Event()
        self.imageScannerConnection = imageScannerConnection
        self.imageScanner = ImageScanner(child_conn1, self.scanInProgress)
        self.imageScanner.start()
        child_conn1.close()

        # Start a thread listening to the imageScanner process messages
        self.imagesScannerListener = ImageScannerListener(
            imageScannerConnection,
            self.imagesBatchLoaded,
        )
        self.imagesScannerListener.start()

        # Start the exif loader process and establish a Pipe connection with it
        logger.info("Starting exif loader...")
        exifLoaderConnection, child_conn2 = Pipe()
        self.exifLoaderConnection = exifLoaderConnection
        self.exifLoader = ExifLoader(child_conn2)
        self.exifLoader.start()
        child_conn2.close()

        # Start a thread listening to the imageScanner process messages
        self.exifLoaderListener = ExifLoaderListener(
            exifLoaderConnection,
            self.datetimeLoaded,
            self.thumbnailLoaded,
        )
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
        try:
            device = self.devices[name]
        except KeyError:
            self.selection = Selection()
        else:
            self.selection = Selection(device, SourceType.DEVICE)
            self.selection.source.eject = eject

        self.sourceSelected.emit(self.selection)

    def selectDrive(self, driveId: str, path: Path, subDirs: bool = False):
        try:
            drive = self.logicalDisks[driveId]
        except KeyError:
            self.selection = Selection()
        else:
            self.selection = Selection(drive, SourceType.DRIVE)
            self.selection.source.selectedPath = path
            self.selection.source.subDirs = subDirs

        self.sourceSelected.emit(self.selection)

    def setDriveSubDirsState(self, state: bool):
        source = self.selection.source
        kind = self.selection.kind
        if source and kind == SourceType.DRIVE:
            source.subDirs = state
            self.sourceSelected.emit(self.selection)

    def setDeviceEjectState(self, state: bool):
        source = self.selection.source
        kind = self.selection.kind
        if source and kind == SourceType.DEVICE:
            source.eject = state

    def scanImages(self, path: Path, includeSubDirs: bool = False):
        if self.scanInProgress.is_set():
        #     logger.info("Abort scanning request")
        #     self.abortScanning.set()
            self.imageScannerConnection.send(
                (ImageScanner.Command.ABORT, 0)
            )
        self.imageScannerConnection.send(
            (ImageScanner.Command.SCAN, (path.as_posix(), includeSubDirs))
        )

    def close(self):
        self.imageScannerConnection.send((ImageScanner.Command.STOP, 0))
        self.imageScannerConnection.close()
        self.imagesScannerListener.join()
        self.exifLoaderConnection.send((ExifLoader.Command.STOP, 0))
        self.exifLoaderConnection.close()
        self.exifLoaderListener.join()
        print(enumerate())

    @staticmethod
    def eject():
        from win32comext.shell import shell, shellcon

        shell.SHChangeNotify(
            shellcon.SHCNE_DRIVEREMOVED, shellcon.SHCNF_PATH, str.encode("L:\\")
        )
