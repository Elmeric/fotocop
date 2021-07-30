import base64
from typing import Optional, Tuple, List, Union
from dataclasses import dataclass
from enum import IntEnum, Enum, auto
from pathlib import Path

import wmi

import PyQt5.QtCore as QtCore

from fotocop.util import exiftool
from fotocop.util.lru import LRUCache


class SourceType(Enum):
    DEVICE = auto()
    DRIVE = auto()


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
    selectedPath: Path = None
    subDirs: bool = False

    @property
    def name(self) -> str:
        if self.kind == DriveType.NETWORK:
            return self.providerName.split("\\")[-1]

        return self.volumeName or self.description

    @property
    def path(self) -> Path:
        if self.kind == DriveType.NETWORK:
            return Path("\\".join(self.providerName.split("\\")[:-1]))

        return Path(f"{self.id}\\")

    @property
    def caption(self) -> str:
        if self.kind == DriveType.NETWORK:
            return f"{self.name} ({self.path}) ({self.id})"

        return f"{self.name} ({self.id})"


@dataclass()
class Device:
    name: str
    logicalDisk: LogicalDisk
    eject: bool = False

    @property
    def caption(self) -> str:
        return f"{self.name} ({self.logicalDisk.id})"


@dataclass()
class Image:
    name: str
    path: str
    isSelected: bool = True


class QtSignalAdapter:
    def __init__(self, name: str = None, argsType: Tuple = None):
        super().__init__()

        self.signalName = name

        if argsType is None:
            argsType = tuple()
        self.argsType = argsType

    def __set_name__(self, owner, name):
        self.name = name

        if self.signalName is None:
            self.signalName = name

        QtSignal = type(
            "QtSignal",
            (QtCore.QObject,),
            {
                f"{self.name}": QtCore.pyqtSignal(self.argsType, name=self.signalName),
            },
        )
        self.qtSignal = QtSignal()

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(self.qtSignal, self.name)


class SourceManager:

    sourceSelected = QtSignalAdapter()

    def __init__(self):
        self.devices = dict()
        self.logicalDisks = dict()
        self.sourceType = None
        self.selectedDevice = None
        self.selectedDrive = None

        self.thumbnailCache = LRUCache(500)

        self.exifTool = exiftool.ExifTool()
        self.exifTool.start()

    def enumerateSources(self, kind: Tuple[DriveType] = None):
        kind = kind or tuple(DriveType)

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

    def getSelectedSource(
        self,
    ) -> Tuple[Optional[Union[Device, LogicalDisk]], Optional[SourceType]]:
        sourceType = self.sourceType
        if sourceType == SourceType.DEVICE:
            return self.selectedDevice, sourceType

        if sourceType == SourceType.DRIVE:
            return self.selectedDrive, sourceType

        return None, None

    def selectDevice(self, name: str, eject: bool = False):
        try:
            self.selectedDevice = self.devices[name]
            self.selectedDevice.eject = eject
            self.sourceType = SourceType.DEVICE
        except KeyError:
            self.selectedDevice = None
            self.sourceType = None

        self.sourceSelected.emit()

    def selectDrive(self, driveId: str, path: Path, subDirs: bool = False):
        try:
            self.selectedDrive = self.logicalDisks[driveId]
            self.selectedDrive.selectedPath = path
            self.selectedDrive.subDirs = subDirs
            self.sourceType = SourceType.DRIVE
        except KeyError:
            self.selectedDrive = None
            self.sourceType = None

        self.sourceSelected.emit()

    def setDriveSubDirsState(self, state: bool):
        source, kind = self.getSelectedSource()
        if kind == SourceType.DRIVE:
            source.subDirs = state
            self.sourceSelected.emit()

    def setDeviceEjectState(self, state: bool):
        source, kind = self.getSelectedSource()
        if kind == SourceType.DEVICE:
            source.eject = state

    def getImages(self) -> List[Image]:
        sourceType = self.sourceType
        if sourceType is None:
            return list()

        if sourceType == SourceType.DEVICE:
            path = self.selectedDevice.logicalDisk.path
            subDirs = True
        else:
            path = self.selectedDrive.selectedPath
            subDirs = self.selectedDrive.subDirs

        if subDirs:
            images = [
                Image(f.name, f.as_posix()) for f in path.rglob("*") if self._isImage(f)
            ]
            # images = ((f.name, f.as_posix()) for f in path.rglob("*") if self._isImage(f))
        else:
            images = [
                Image(f.name, f.as_posix()) for f in path.glob("*") if self._isImage(f)
            ]
            # images = ((f.name, f.as_posix()) for f in path.glob("*") if self._isImage(f))

        return images

    def getThumbnail(self, path: str) -> Tuple[Optional[bytes], float, int]:
        try:
            #     # print(f"Got image: {imageName} from cache")
            imgdata, aspectRatio, orientation = self.thumbnailCache[path]
            # print(f"Got image: {path} {aspectRatio} {orientation} from cache")
            return imgdata, aspectRatio, orientation
        except KeyError:
            pass

        exif = self.exifTool.get_tags(
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
            self.thumbnailCache[path] = (imgdata, aspectRatio, orientation)
            print(f"Loading image: {path} {aspectRatio} {orientation}")
            return imgdata, aspectRatio, orientation

        self.thumbnailCache[path] = (None, 0, 0)
        return None, 0, 0

    def getDateTime(self, path: str) -> Optional[Tuple[str, str, str, str, str, str]]:
        dateTime = self.exifTool.get_tag("EXIF:DateTimeOriginal", path)
        if dateTime:  # "YYYY:MM:DD HH:MM:SS"
            date, time = dateTime.split(" ", 1)
            year, month, day = date.split(":")
            hour, minute, second = time.split(":")
            return year, month, day, hour, minute, second
        return None

    @staticmethod
    def _isImage(path: Path) -> bool:
        return path.suffix.lower() in (".jpg", ".raf", ".nef", ".dng")

    def stopExifTool(self):
        self.exifTool.terminate()

    @staticmethod
    def eject():
        from win32comext.shell import shell, shellcon

        shell.SHChangeNotify(
            shellcon.SHCNE_DRIVEREMOVED, shellcon.SHCNF_PATH, str.encode("L:\\")
        )


if __name__ == "__main__":
    sm = SourceManager()
    sm.enumerateSources()
    print(sm.devices)
    print(sm.logicalDisks)
    for d in sm.logicalDisks.values():
        print(d.name)
        print(d.path)
    # sm.eject()
