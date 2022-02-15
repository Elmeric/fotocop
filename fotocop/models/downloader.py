import json
import logging
from typing import TYPE_CHECKING, List, Tuple, Optional
from datetime import datetime, date
from dataclasses import dataclass
from pathlib import Path

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config
from fotocop.models.sources import Image, Datation
from fotocop.models.naming import (
    NamingTemplates,
    NamingTemplatesError,
)

if TYPE_CHECKING:
    from fotocop.models.sources import Selection
    from fotocop.models.naming import NamingTemplate, Token

logger = logging.getLogger(__name__)


class Downloader:

    imageSampleChanged = QtUtil.QtSignalAdapter(str)
    destinationSelected = QtUtil.QtSignalAdapter(Path)

    destination: Path

    def __init__(self):
        self._namingTemplates = NamingTemplates()
        self._sequences = Sequences()

        self._source = None
        self._imageNamingTemplate = self._namingTemplates.builtinImageNamingTemplates[
            NamingTemplates.defaultImageNamingTemplate
        ]

        # self.selectLastDestination()
        # self.destination = Path(shell.SHGetFolderPath(0, shellcon.CSIDL_MYPICTURES, None, 0))
        # print(self.destination)
        self._destinationNamingTemplate = None
        self._imageSample = self._makeDefaultImageSample()
        self.renameImageSample()

    def setImageNamingTemplate(self, key: str):
        template = self.getImageNamingTemplateByKey(key)
        # Keep previously selected extension unchanged
        template.extension = self._imageNamingTemplate.extension
        self._imageNamingTemplate = template
        self.renameImageSample()

    def setExtension(self, extensionKind: str):
        self._imageNamingTemplate.extension = extensionKind
        self.renameImageSample()

    def setDestinationNamingTemplate(self, template: "NamingTemplate"):
        self._destinationNamingTemplate = template

    def renameImage(self, image: "Image", downloadTime: datetime = datetime.now()) -> str:
        return self._imageNamingTemplate.format(image, self._sequences, downloadTime)

    def renameImageSample(self):
        sampleName = self.renameImage(self._imageSample)
        self.imageSampleChanged.emit(sampleName)

    def selectDestination(self, destination: Path) -> None:
        self.destination = destination
        Config.fotocopSettings.lastDestination = destination
        self.destinationSelected.emit(destination)

    def makeDestinationFolder(self, image: "Image", downloadTime: datetime = datetime.now()) -> Path:
        return Path(self._destinationNamingTemplate.format(image, self._sequences, downloadTime))

    def download(self, images: List["Image"]):
        downloadTime = datetime.now()
        for image in images:
            if image.isSelected:
                name = self.renameImage(image, downloadTime)
                path = self.makeDestinationFolder(image, downloadTime) / name
                print(f"{path.as_posix()}")

    def setSourceSelection(self, selection: "Selection"):
        """Call on SourceManager.sourceSelected(Selection) signal"""
        self._source = selection
        self._imageSample = self._makeDefaultImageSample()
        self.renameImageSample()

    def updateImageSample(self):
        """Call on SourceManager.timelineBuilt() signal"""
        images = self._source.images     # may be an empty dict
        if len(images) > 0:
            # A source with at least one image is selected: get the first one.
            imageKey = next(iter(images))
            self._imageSample = images[imageKey]
        else:
            # No source or an empty source is selected: create our own image sample.
            self._imageSample = self._makeDefaultImageSample()
        self.renameImageSample()

    @staticmethod
    def _makeDefaultImageSample() -> "Image":
        imageSample = Image("IMG_0001.RAF", "L:/path/to/images")
        d = datetime.today()
        imageSample.datetime = Datation(
            str(d.year), str(d.month), str(d.day),
            str(d.hour), str(d.minute), str(d.second)
        )
        return imageSample

    def listBuiltinImageNamingTemplates(self) -> List["NamingTemplate"]:
        return list(self._namingTemplates.listBuiltinImageNamingTemplates())

    def listCustomImageNamingTemplates(self) -> List["NamingTemplate"]:
        return list(self._namingTemplates.listCustomImageNamingTemplates())

    def getImageNamingTemplateByKey(self, key: str) -> Optional["NamingTemplate"]:
        return self._namingTemplates.getImageNamingTemplateByKey(key)

    def addCustomImageNamingTemplates(self, name: str, template: Tuple["Token", ...]) -> "NamingTemplate":
        return self._namingTemplates.addCustomImageNamingTemplate(name, template)

    def deleteCustomImageNamingTemplate(self, templateKey: str):
        self._namingTemplates.deleteCustomImageNamingTemplate(templateKey)

    def changeCustomImageNamingTemplate(self, templateKey: str, template: Tuple["Token", ...]):
        self._namingTemplates.changeCustomImageNamingTemplate(templateKey, template)
        self.renameImageSample()

    def saveCustomNamingTemplates(self) -> Tuple[bool, str]:
        try:
            self._namingTemplates.save()
            return True, "Custom naming templates successfully saved"
        except NamingTemplatesError as e:
            return False, str(e)

    # def selectLastDestination(self):
    #     lastDestination = Config.fotocopSettings.lastDestination
    #     if lastDestination is None:
    #         lastDestination = shell.SHGetFolderPath(0, shellcon.CSIDL_MYPICTURES, None, 0)
    #
    #     self.selectDestination(Path(lastDestination))


@dataclass
class DownloadsToday:
    date: date = date.today()
    count: int = 1

    def get(self) -> int:
        """Reset to 0 and save the date when day changes.
        """
        today = date.today()
        if self.date < today:
            self.date = today
            self.count = 0
        return self.count

    def set(self, count: int):
        self.get()
        self.count = count

    def increment(self):
        count = self.get()
        self.count = count + 1

    def toJson(self) -> Tuple[str, int]:
        date_ = self.date
        return f"{date_.year}-{date_.month}-{date_.day}", self.count

    def fromJson(self, value: Tuple[str, int]) -> "DownloadsToday":
        year, month, day = value[0].split("-")
        self.date = date(int(year), int(month), int(day))
        self.count = value[1]
        return self


class SequencesError(Exception):
    """Exception raised on sequences saving error."""
    pass


class Sequences:
    def __init__(self):
        self.sessionNumber = 1
        self._sequencesFile = Config.fotocopSettings.appDirs.user_config_dir / "sequences.json"
        self._downloadsToday = None
        self._storedNumber = None
        # self._downloadsToday, self._storedNumber = self.load()

    def __str__(self) -> str:
        return f"Today: {self.downloadsToday}, Stored: {self.storedNumber}," \
               f" Session: {self.sessionNumber}, Letters: {self.sequenceLetter}"

    @property
    def downloadsToday(self) -> 'DownloadsToday':
        if self._downloadsToday is None:
            self._downloadsToday, self._storedNumber = self.load()
        return self._downloadsToday

    @downloadsToday.setter
    def downloadsToday(self, value: int):
        self._downloadsToday.set(value)
        self.save()

    @property
    def storedNumber(self) -> int:
        if self._storedNumber is None:
            self._downloadsToday, self._storedNumber = self.load()
        return self._storedNumber

    @storedNumber.setter
    def storedNumber(self, value: int):
        self._storedNumber = value
        self.save()

    @property
    def sequenceLetter(self) -> str:
        return self._toLetters(self.sessionNumber)

    def load(self) -> Tuple[DownloadsToday, int]:
        try:
            with self._sequencesFile.open() as fh:
                sequences = json.load(fh)
                domnloadsToday = DownloadsToday().fromJson(sequences["downloadsToday"])
                return domnloadsToday, sequences["storedNumber"]
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Cannot load persistent sequences number: {e}")
            return DownloadsToday(), 1

    def save(self):
        if self._downloadsToday is None or self._storedNumber is None:
            return

        sequences = {
            "downloadsToday": self._downloadsToday.toJson(),
            "storedNumber": self._storedNumber,
        }
        try:
            with self._sequencesFile.open(mode="w") as fh:
                json.dump(sequences, fh, indent=4)
        except (OSError, TypeError) as e:
            msg = f"Cannot save persistent sequences number: {e}"
            logger.warning(msg)
            raise SequencesError(msg)

    def increment(self):
        self.storedNumber += 1
        self.sessionNumber += 1
        self.downloadsToday.increment()
        self.save()

    @staticmethod
    def _divmod26(n: int) -> Tuple[int, int]:
        assert n > 0
        a, b = divmod(n, 26)
        if b == 0:
            return a - 1, b + 26
        return a, b

    def _toLetters(self, num: int) -> str:
        if num <= 0:
            return ""
        letters = ""
        while num > 0:
            num, d = self._divmod26(num)
            letters = "".join((chr(d + 64), letters))
        return letters


if __name__ == '__main__':
    seq = Sequences()
    print(seq)
    seq.increment()
    print(seq)
    seq.downloadsToday = 10
    seq.storedNumber = 10
    seq.sessionNumber = 10
    print(seq)
    seq.increment()
    print(seq)
