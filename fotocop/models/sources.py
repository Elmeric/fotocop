import logging
import time

from typing import Optional, Tuple, List, Union, Iterator
from datetime import datetime
from collections import Counter
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

    def __post_init__(self):
        self.images = dict()
        self.expectedImagesCount = 0
        self.imageScanStopped = False
        self.timeline = Timeline()
        self.thumbnailCache = LRUCache(50)

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
                    (ExifLoader.Command.LOAD_DATE, (self.name, self.path))
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
            try:
                if self.imageLoaderConnection.poll(timeout=0.01):
                    sourceManager = SourceManager()
                    currentPath = sourceManager.selection.path
                    k, v = self.imageLoaderConnection.recv()
                    content, batch = k.split("#")
                    if content != "images":
                        continue
                    if batch == "ScanComplete":
                        imagesCount, stopped = v
                        logger.info(f"All batches received: {imagesCount} images - "
                                    f"Status: {'stopped' if stopped else 'complete'}")
                        sourceManager.imageScanCompleted.emit(*v)
                        if stopped:
                            sourceManager.selection.expectedImagesCount = 0
                        else:
                            sourceManager.selection.expectedImagesCount = imagesCount
                        sourceManager.selection.imageScanStopped = stopped
                        continue
                    newImages = {path: Image(name, path) for name, path in v if path.startswith(currentPath)}
                    if newImages:
                        sourceManager.selection.images.update(newImages)
                        logger.debug(f"Received batch: {batch} containing {len(newImages)} images")
                        self.imagesBatchLoaded.emit(
                            newImages,
                            f"images from batch {batch} containing {len(newImages)} images"
                        )
                        for image in newImages.values():
                            image.getThumbnail()
            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        self.imageLoaderConnection.close()
        super().join(timeout)


class ExifLoaderListener(Thread):
    def __init__(self, conn):
        super().__init__()
        self.exifLoaderConnection = conn
        self.alive = Event()

    def run(self):
        self.alive.set()
        receivedImagesCount = 0
        while self.alive.is_set():
            try:
                if self.exifLoaderConnection.poll(timeout=0.01):
                    content, data, imageKey = self.exifLoaderConnection.recv()
                    sourceManager = SourceManager()
                    expectedImagesCount = sourceManager.selection.expectedImagesCount
                    scanStopped = sourceManager.selection.imageScanStopped
                    try:
                        image = sourceManager.selection.images[imageKey]
                    except KeyError:
                        # selection has been reset or has changed: ignore old data
                        receivedImagesCount = 0
                        logger.debug(f"{imageKey} is not found in current source selection")
                        continue
                    else:
                        if content == "datetime":
                            receivedImagesCount += 1
                            logger.debug(f"Received datetime for image {imageKey} "
                                         f"({receivedImagesCount}/{expectedImagesCount} - "
                                         f"{'stopped' if scanStopped else 'running'})")
                            image.datetime = data
                            sourceManager.selection.timeline.addDatetime(data)
                            sourceManager.datetimeLoaded.emit(receivedImagesCount, expectedImagesCount)
                            if scanStopped or receivedImagesCount == expectedImagesCount:
                                receivedImagesCount = 0
                        elif content == "thumbnail":
                            logger.debug(f"Received thumbnail for image {imageKey}")
                            sourceManager.selection.thumbnailCache[image.path] = data
                            image.loadingInProgress = False
                            sourceManager.thumbnailLoaded.emit(imageKey)
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
    imageScanCompleted = QtUtil.QtSignalAdapter(int, bool)  # imagesCount, status
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

        self.sourceSelected.emit(self.selection)

    def setDriveSubDirsState(self, state: bool):
        selection = self.selection
        source = selection.source
        kind = selection.kind
        if source and kind == SourceType.DRIVE:
            self.selectDrive(source.id, Path(selection.path), subDirs=True)

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
