import logging
import json
from typing import Tuple, Optional, List, Dict
from multiprocessing import Process, Event
from enum import Enum, auto
from pathlib import Path
from datetime import datetime, date
from dataclasses import dataclass


from fotocop.util.logutil import LogConfig, configureRootLogger
from fotocop.models import settings as Config
from fotocop.models.naming import TemplateType, NamingTemplate
from fotocop.models.sources import Image

logger = logging.getLogger(__name__)


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


class ImageMover(Process):

    class Command(Enum):
        STOP = auto()
        SET_DEST = auto()
        SET_IMG_TPL = auto()
        SET_DEST_TPL = auto()
        SET_IMAGES = auto()
        GET_IMG_PREVIEW = auto()
        GET_FOLDERS_PREVIEW = auto()
        DOWNLOAD = auto()

    def __init__(self, conn):
        """
        Create a ImageMover process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__()

        self.name = "ImagesMover"

        logConfig = LogConfig()
        self._logQueue = logConfig.logQueue
        self._logLevel = logConfig.logLevel

        self._conn = conn
        self._exitProcess = Event()

        self._sequences = Sequences()

        self._destination: Optional[Path] = None
        self._imageNamingTemplate: Optional[NamingTemplate] = None
        self._destinationNamingTemplate: Optional[NamingTemplate] = None
        self._images: List[Image] = list()

    def run(self):
        """ImagesMover 'main loop'
        """
        configureRootLogger(self._logQueue, self._logLevel)

        self._exitProcess.clear()

        logger.info("Images mover started")
        while True:
            self.handleCommand()
            if self._exitProcess.wait(timeout=0.01):
                break

        self._conn.close()
        logger.info("Images mover stopped")

    def handleCommand(self):
        """Poll the ImageMover connection for task message.

        A task message is a tuple (action, arg).
        """
        # Check for command on the process connection
        if self._conn.poll():
            action, args = self._conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping images mover...")
                self._exitProcess.set()
            elif action == self.Command.SET_DEST:
                # Update the ImageMover context with the destination path
                logger.debug(f"Update context, Destination is {args}...")
                self._setDestination(args)
            elif action == self.Command.SET_IMG_TPL:
                # Update the ImageMover context with the selected images naming template
                logger.debug(f"Update context, Images naming template is {args.name}...")
                self._setNamingTemplate(TemplateType.IMAGE, args)
            elif action == self.Command.SET_DEST_TPL:
                # Update the ImageMover context with the selected destination naming template
                logger.debug(f"Update context, Destination naming template is {args.name}...")
                self._setNamingTemplate(TemplateType.DESTINATION, args)
            elif action == self.Command.SET_IMAGES:
                # Update the ImageMover context with the selected images to download
                logger.debug(f"Update context, {len(args)} images to download...")
                self._setImages(args)
            elif action == self.Command.GET_IMG_PREVIEW:
                # Reply with preview of the given image sample according to the current context
                # if args is not None:
                logger.debug(f"Compute and publish image sample preview...")
                self._publishImagePreview(args)
            elif action == self.Command.GET_FOLDERS_PREVIEW:
                # Reply with preview of the "where to download folders" according to the
                # current context
                logger.debug(f"Compute and publish folders preview...")
                self._publishFolderPreview()
            else:
                logger.warning(f"Unknown command {action.name} ignored")

    def _setDestination(self, path: str) -> None:
        self._destination = Path(path)

    def _setNamingTemplate(self, kind: TemplateType, template: NamingTemplate) -> None:
        print(template.name, template.asText())
        if kind == TemplateType.IMAGE:
            self._imageNamingTemplate = template
        else:
            assert kind == TemplateType.DESTINATION
            self._destinationNamingTemplate = template

    def _setImages(self, images: Dict[str, Image]) -> None:
        selectedImages = [
            image
            for image in images.values()
            if image.isLoaded and image.isSelected
        ]
        self._images = selectedImages
        print(f"Received {len(images)} images, only {len(selectedImages)} are loaded and selected")
        # for i in self._images:
        #     print(i.path)
        # self._images = images

    def _publishImagePreview(self, image: "Image") -> None:
        imageTemplate = self._imageNamingTemplate
        destinationTemplate = self._destinationNamingTemplate
        if imageTemplate is not None and destinationTemplate is not None:
            sequences = self._sequences
            sampleName = self._imageNamingTemplate.format(image, sequences, datetime.now())
            samplePath = self._destinationNamingTemplate.format(
                image, sequences, datetime.now(), TemplateType.DESTINATION
            )
            self._publishData("image_preview", sampleName, samplePath)

    def _publishFolderPreview(self) -> None:
        previewFolders = set()
        seen = list()
        for image in self._images:
            path = Path(
                self._destinationNamingTemplate.format(
                    image, self._sequences, datetime.now(), TemplateType.DESTINATION
                )
            )
            folder = self._destination
            absPath = folder / path
            if absPath in seen:
                continue
            seen.append(absPath)
            previewFolders.add(absPath.as_posix())
        self._publishData("folder_preview", previewFolders)

    def _publishData(self, content: str, *data) -> None:
        msg = (content, *data)
        try:
            self._conn.send(msg)
            logger.debug(f"Data published: {data}")
        except (OSError, EOFError, BrokenPipeError):
            pass
