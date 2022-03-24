import json
import logging
from typing import TYPE_CHECKING, Tuple, Optional
from datetime import datetime, date
from dataclasses import dataclass
from pathlib import Path
from multiprocessing import Pipe, Event
from threading import Thread

from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Singleton, DelegatedAttribute
from fotocop.models import settings as Config
from fotocop.models.sources import Image, Datation
from fotocop.models.naming import (Case, TemplateType, NamingTemplates)
from fotocop.models.imagesmover import ImageMover

if TYPE_CHECKING:
    from fotocop.models.sources import Selection

logger = logging.getLogger(__name__)


class ImageMoverListener(Thread):
    def __init__(self, conn):
        super().__init__()
        self.name = "ImageMoverListener"
        self._imageMoverConnection = conn
        self._alive = Event()

    def run(self):
        self._alive.set()
        while self._alive.is_set():
            try:
                if self._imageMoverConnection.poll(timeout=0.01):
                    content, *data = self._imageMoverConnection.recv()
                    downloader = Downloader()

                    if content == "image_preview":
                        sampleName, samplePath = data
                        logger.debug(
                            f"Received image sample preview: {sampleName}, {samplePath}"
                        )
                        downloader.imageSampleChanged.emit(
                            sampleName,
                            Path(samplePath).as_posix()
                        )

                    elif content == "folder_preview":
                        previewFolders, *_ = data
                        logger.debug(
                            f"Received folder preview: {previewFolders}"
                        )
                        downloader.folderPreviewChanged.emit(previewFolders)

                    else:
                        logger.warning(f"Received unknown content: {content}")

            except (OSError, EOFError, BrokenPipeError):
                self._alive.clear()

    def join(self, timeout=None):
        self._alive.clear()
        super().join(timeout)


class Downloader(metaclass=Singleton):

    imageSampleChanged = QtUtil.QtSignalAdapter(str, str)    # image name, image path
    destinationSelected = QtUtil.QtSignalAdapter(Path)
    imageNamingTemplateSelected = QtUtil.QtSignalAdapter(str)
    imageNamingExtensionSelected = QtUtil.QtSignalAdapter(Case)
    destinationNamingTemplateSelected = QtUtil.QtSignalAdapter(str)
    sessionRequired = QtUtil.QtSignalAdapter(bool)
    folderPreviewChanged = QtUtil.QtSignalAdapter(set)

    listBuiltinNamingTemplates = DelegatedAttribute("_namingTemplates", "listBuiltins")
    listCustomNamingTemplates = DelegatedAttribute("_namingTemplates", "listCustoms")
    getNamingTemplateByKey = DelegatedAttribute("_namingTemplates", "getByKey")
    getDefaultNamingTemplate = DelegatedAttribute("_namingTemplates", "getDefault")
    addCustomNamingTemplate = DelegatedAttribute("_namingTemplates", "add")
    deleteCustomNamingTemplate = DelegatedAttribute("_namingTemplates", "delete")
    changeCustomNamingTemplate = DelegatedAttribute("_namingTemplates", "change")
    saveCustomNamingTemplates = DelegatedAttribute("_namingTemplates", "save")
    saveSequences = DelegatedAttribute("_sequences", "save")

    def __init__(self):
        self.destination: Optional[Path] = None
        namingTemplates = NamingTemplates()

        self.imageNamingTemplate = namingTemplates.getDefault(TemplateType.IMAGE)
        self.destinationNamingTemplate = namingTemplates.getDefault(TemplateType.DESTINATION)

        self._namingTemplates = namingTemplates
        self._sequences = Sequences()
        self._source = None
        self._imageSample = self._makeDefaultImageSample()

        # Start the images' mover process and establish a Pipe connection with it
        logger.info("Starting images mover...")
        imageMoverConnection, child_conn1 = Pipe()
        self._imageMoverConnection = imageMoverConnection
        self._imageMover = ImageMover(child_conn1)
        self._imageMover.start()
        child_conn1.close()

        # Start a thread listening to the imageMover process messages
        self._imagesMoverListener = ImageMoverListener(imageMoverConnection)
        self._imagesMoverListener.start()

        self._updatePreview(imageOnly=True)

    def setSourceSelection(self, selection: "Selection"):
        """Call on SourceManager.sourceSelected(Selection) signal"""
        self._source = selection
        self._updateImages()

    def updateImageSample(self):
        """Call on SourceManager.sourceSelected(Selection) and SourceManager.timelineBuilt() signals"""
        self._updateImages()
        images = self._source.images
        # By SourceManager design, self._source cannot be None, but images may be an
        # empty dict when the selection is empty.
        if len(images) > 0:
            # A source with at least one image is selected: get the first one if dated.
            imageKey = next(iter(images))
            image = images[imageKey]
            if image.isLoaded:
                self._imageSample = images[imageKey]
            else:
                # Images are not yet dated: create our own image sample.
                self._imageSample = self._makeDefaultImageSample()
        else:
            # No source or an empty source is selected: create our own image sample.
            self._imageSample = self._makeDefaultImageSample()
        logger.debug(f"Image sample is now: {self._imageSample.name} "
                     f"in {self._imageSample.path} "
                     f"with date {self._imageSample.datetime}")
        self._updatePreview(imageOnly=False)
        self._checkSession()

    def selectDestination(self, destination: Path) -> None:
        self.destination = destination
        Config.fotocopSettings.lastDestination = destination
        self._imageMoverConnection.send((ImageMover.Command.SET_DEST, destination.as_posix()))
        self.destinationSelected.emit(destination)

    def setNamingTemplate(self, kind: "TemplateType", key: str):
        if kind == TemplateType.IMAGE:
            self._setImageNamingTemplate(key)
            self._updatePreview(imageOnly=True)
        else:
            assert kind == TemplateType.DESTINATION
            self._setDestinationNamingTemplate(key)
            self._updatePreview(imageOnly=False)

    def setExtension(self, extensionKind: Case):
        template = self.imageNamingTemplate
        template.extension = extensionKind
        Config.fotocopSettings.lastNamingExtension = extensionKind.name
        self._imageMoverConnection.send((ImageMover.Command.SET_IMG_TPL, template))
        self.imageNamingExtensionSelected.emit(extensionKind)
        self._updatePreview(imageOnly=False)

    def download(self) -> None:
        images = self._source.images
        downloadTime = datetime.now()
        for image in images.values():
            if image.isSelected:
                name = self._renameImage(image, downloadTime)
                path = self._makeDestinationFolder(image, downloadTime) / name
                print(f"Moving to: {path.as_posix()}")

    def close(self) -> None:
        # Organize a kindly shutdown when quitting the application

        # Stop and join the images' mover process ant its listener thread
        logger.info("Request images mover to stop...")
        self._imageMoverConnection.send((ImageMover.Command.STOP, 0))
        self._imageMover.join(timeout=0.25)
        if self._imageMover.is_alive():
            self._imageMover.terminate()
        self._imageMoverConnection.close()
        self._imagesMoverListener.join()

    def _setImageNamingTemplate(self, key: str):
        template = self.getNamingTemplateByKey(TemplateType.IMAGE, key)
        # Keep previously selected extension unchanged
        template.extension = self.imageNamingTemplate.extension
        self.imageNamingTemplate = template
        Config.fotocopSettings.lastImageNamingTemplate = key
        self._imageMoverConnection.send((ImageMover.Command.SET_IMG_TPL, template))
        self.imageNamingTemplateSelected.emit(key)
        self._checkSession()

    def _setDestinationNamingTemplate(self, key: str):
        template = self.getNamingTemplateByKey(TemplateType.DESTINATION, key)
        self.destinationNamingTemplate = template
        Config.fotocopSettings.lastDestinationNamingTemplate = key
        self._imageMoverConnection.send((ImageMover.Command.SET_DEST_TPL, template))
        self.destinationNamingTemplateSelected.emit(key)
        self._checkSession()

    def _updateImages(self) -> None:
        images = self._source.images
        # images = list(self._source.images.values())
        # images = self._source.images
        # selectedImages = [
        #     image
        #     for image in images.values()
        #     if image.isLoaded and image.isSelected
        # ]
        self._imageMoverConnection.send((ImageMover.Command.SET_IMAGES, images))
        # self._imageMoverConnection.send((ImageMover.Command.SET_IMAGES, selectedImages))

    def _updatePreview(self, imageOnly: bool = False) -> None:
        # Update image sample name and path.
        self._imageMoverConnection.send(
            (ImageMover.Command.GET_IMG_PREVIEW, self._imageSample)
        )

        if imageOnly:
            return

        # Update folders preview
        self._imageMoverConnection.send((ImageMover.Command.GET_FOLDERS_PREVIEW, 0))

    def _renameImage(self, image: "Image", downloadTime: datetime = datetime.now()) -> str:
        return self.imageNamingTemplate.format(image, self._sequences, downloadTime)

    def _makeDestinationFolder(self, image: "Image", downloadTime: datetime = datetime.now()) -> Path:
        return Path(
            self.destinationNamingTemplate.format(
                image, self._sequences, downloadTime, TemplateType.DESTINATION
            )
        )

    @staticmethod
    def _makeDefaultImageSample() -> "Image":
        imageSample = Image("IMG_0001.RAF", "L:/path/to/images")
        d = datetime.today()
        imageSample.datetime = Datation(
            str(d.year), str(d.month), str(d.day),
            str(d.hour), str(d.minute), str(d.second)
        )
        return imageSample

    def _checkSession(self):
        sessionRequired = self.imageNamingTemplate.sessionRequired or self.destinationNamingTemplate.sessionRequired
        self.sessionRequired.emit(sessionRequired)
        # if self.imageNamingTemplate.sessionRequired or self.destinationNamingTemplate.sessionRequired:
        #     source = self._source
        #     if source is not None and source.images:
        #         for image in source.images.values():
        #             if image.isSelected and not image.session:
        #                 print("Session required")
        #                 self.sessionRequired.emit()
        #                 break


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

        self._isDirty = False

    def __str__(self) -> str:
        return f"Today: {self._downloadsToday}, Stored: {self._storedNumber}," \
               f" Session: {self.sessionNumber}, Letters: {self.sequenceLetter}"

    @property
    def downloadsToday(self) -> 'DownloadsToday':
        if self._downloadsToday is None:
            self._downloadsToday, self._storedNumber = self.load()
        return self._downloadsToday

    @downloadsToday.setter
    def downloadsToday(self, value: int):
        self._downloadsToday.set(value)
        self._isDirty = True

    @property
    def storedNumber(self) -> int:
        if self._storedNumber is None:
            self._downloadsToday, self._storedNumber = self.load()
        return self._storedNumber

    @storedNumber.setter
    def storedNumber(self, value: int):
        self._storedNumber = value
        self._isDirty = True

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

        if not self._isDirty:
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
        else:
            logger.info("Downloader sequences correctly saved.")
            self._isDirty = False

    def increment(self):
        self.storedNumber += 1
        self.sessionNumber += 1
        self.downloadsToday.increment()
        self._isDirty = True

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


# if __name__ == '__main__':
#     seq = Sequences()
#     print(seq)
#     seq.increment()
#     print(seq)
#     seq.downloadsToday = 10
#     seq.storedNumber = 10
#     seq.sessionNumber = 10
#     print(seq)
#     seq.increment()
#     print(seq)
