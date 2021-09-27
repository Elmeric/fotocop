import base64
import logging
import time

from typing import Optional, Tuple, List, Union
from dataclasses import dataclass
from enum import IntEnum, Enum, auto
from pathlib import Path
from multiprocessing import Pipe, Event
from threading import Thread

import wmi

from fotocop.util import exiftool
from fotocop.util.lru import LRUCache
from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Singleton
from fotocop.models.imageloader import ImageLoader

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

    @property
    def datetime(self) -> Optional[Tuple[str, str, str, str, str, str]]:
        if self._datetime is None:
            dateTime = SourceManager().exifTool.get_tag("EXIF:DateTimeOriginal", self.path)
            if dateTime:  # "YYYY:MM:DD HH:MM:SS"
                date, time_ = dateTime.split(" ", 1)
                year, month, day = date.split(":")
                hour, minute, second = time_.split(":")
                self._datetime = (year, month, day, hour, minute, second)    # noqa

        return self._datetime

    def getThumbnail(self) -> Tuple[Optional[bytes], float, int]:
        path = self.path
        sourceManager = SourceManager()
        thumbnailCache = sourceManager.thumbnailCache
        try:
            imgdata, aspectRatio, orientation = thumbnailCache[path]
            # print(f"Got image: {path} {aspectRatio} {orientation} from cache")
        except KeyError:
            pass
        else:
            return imgdata, aspectRatio, orientation

        exif = sourceManager.exifTool.get_tags(
            [
                "EXIF:ThumbnailImage",
                "EXIF:ThumbnailTIFF",
                "EXIF:ImageWidth",
                "EXIF:ImageHeight",
                "EXIF:ExifImageWidth",
                "EXIF:ExifImageHeight",
                "EXIF:Orientation",
            ],
            path,
        )
        try:
            imgstring = exif["EXIF:ThumbnailImage"]
        except KeyError:
            try:
                imgstring = exif["EXIF:ThumbnailTIFF"]
            except KeyError:
                imgstring = None

        try:
            width = exif["EXIF:ExifImageWidth"]
            height = exif["EXIF:ExifImageHeight"]
            aspectRatio = (
                round(width / height, 1) if width > height else round(height / width, 1)
            )
        except KeyError:
            try:
                width = exif["EXIF:ImageWidth"]
                height = exif["EXIF:ImageHeight"]
                aspectRatio = (
                    round(width / height, 1)
                    if width > height
                    else round(height / width, 1)
                )
            except KeyError:
                aspectRatio = 0

        try:
            rawOrient = exif["EXIF:Orientation"]
            orientation = 90 if rawOrient == 6 else -90 if rawOrient == 8 else 0
        except KeyError:
            orientation = 0

        if imgstring:
            imgstring = imgstring[7:]
            imgdata = base64.b64decode(imgstring)
            thumbnailCache[path] = (imgdata, aspectRatio, orientation)
            logger.debug(f"Loading image: {path} {aspectRatio} {orientation}")
            return imgdata, aspectRatio, orientation

        thumbnailCache[path] = (None, 0, 0)
        return None, 0, 0


class ImagesLoaderListener(Thread):
    def __init__(self, conn, imagesBatchLoaded):
        super().__init__()
        self.imageLoaderConnection = conn
        self.imagesBatchLoaded = imagesBatchLoaded
        self.alive = Event()
        self.alive.set()

    def run(self):
        while self.alive.is_set():
            try:
                if self.imageLoaderConnection.poll(timeout=0.01):
                    k, v = self.imageLoaderConnection.recv()
                    content, batch = k.split("#")
                    if content != "images":
                        continue
                    images = [Image(name, path) for name, path in v]
                    logger.debug(f"Received batch: {batch} containing {len(images)} images")
                    self.imagesBatchLoaded.emit(
                        images,
                        f"Loading images from batch {batch} containing {len(images)} images"
                    )
            except (OSError, EOFError, BrokenPipeError):
                self.alive.clear()

    def join(self, timeout=None):
        self.alive.clear()
        self.imageLoaderConnection.close()
        super().join(timeout)


class SourceManager(metaclass=Singleton):

    sourceSelected = QtUtil.QtSignalAdapter(Selection)
    imagesBatchLoaded = QtUtil.QtSignalAdapter(list, str)

    def __init__(self):
        self.devices = dict()
        self.logicalDisks = dict()

        self.selection = Selection()

        self.thumbnailCache = LRUCache(500)

        logger.info("Starting ExifTool...")
        self.exifTool = exiftool.ExifTool()
        self.exifTool.start()

        # Start the image loader process and establish a Pipe connection with it
        logger.info("Starting image loader...")
        conn, child_conn = Pipe()
        self.imageLoaderConnection = conn
        self.imageLoader = ImageLoader(child_conn)
        self.imageLoader.start()
        child_conn.close()

        # Start a thread listening to the imageLoader process messages
        self.imagesLoaderListener = ImagesLoaderListener(
            conn,
            self.imagesBatchLoaded,
        )
        self.imagesLoaderListener.start()

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
        self.imageLoaderConnection.send(
            (ImageLoader.Command.SCAN, (path.as_posix(), includeSubDirs))
        )

    def close(self):
        self.imageLoaderConnection.send((ImageLoader.Command.STOP, 0))
        self.imageLoaderConnection.close()
        self.imagesLoaderListener.join()
        logger.info("Stopping ExifTool...")
        self.exifTool.terminate()

    @staticmethod
    def eject():
        from win32comext.shell import shell, shellcon

        shell.SHChangeNotify(
            shellcon.SHCNE_DRIVEREMOVED, shellcon.SHCNF_PATH, str.encode("L:\\")
        )
