import logging
import json
from typing import TYPE_CHECKING, Tuple, Optional, List, Dict
from enum import Enum, auto
from datetime import datetime, date
from dataclasses import dataclass

from fotocop.util.threadutil import StoppableThread
from fotocop.util.workerutil import BackgroundWorker
from fotocop.util.pathutil import Path
from fotocop.models import settings as Config
from fotocop.models.naming import TemplateType, NamingTemplate

if TYPE_CHECKING:
    from fotocop.models.sources import ImageKey, Image, ImageProperty

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
            self.count = 1
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
            self._isDirty = True
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
        else:
            logger.info("Downloader sequences correctly saved.")
            self._isDirty = False

    def increment(self, incSessionNb: bool, incStoredNb: bool) -> None:
        if incStoredNb:
            self.storedNumber += 1
        if incSessionNb:
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


class DownloadHandler(StoppableThread):
    def __init__(
            self,
            selectedImages: List["Image"],
            worker: "ImageMover",
            *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.name = "StoppableDownloadHandler"
        self._selectedImages = selectedImages
        self._selectedImagesCount = len(selectedImages)
        self._worker = worker

    def run(self) -> None:
        logger.info(f"Downloading {self._selectedImagesCount} images...")
        self._downloadImages()

    def _downloadImages(self):
        selectedImages = self._selectedImages
        selectedImagesCount = self._selectedImagesCount
        self._worker.publishData("selected_images_count", selectedImagesCount)

        folder = self._worker.destination
        downloadTime = datetime.now()
        incrementSessionNb = (
            self._worker.imageNamingTemplate.useSessionNumber
            or self._worker.destinationNamingTemplate.useSessionNumber
        )
        incrementStoredNb = (
            self._worker.imageNamingTemplate.useStoredNumber
            or self._worker.destinationNamingTemplate.useStoredNumber
        )
        count = 0
        stopped = False
        downloadedImagesInfo = list()
        for image in selectedImages:
            if self.stopped():
                logger.info(
                    f"Stop downloading images, {len(selectedImages) - count} images remaining."
                )
                stopped = True
                break
            count += 1
            name = self._renameImage(image, downloadTime)
            path = self._makeDestinationFolder(image, downloadTime)
            absPath = folder / path
            uniqueName = self._ensureNameUnicity(name, absPath)
            absName = absPath / uniqueName
            try:
                absPath.mkdir(parents=True, exist_ok=True)
                Path(image.path).copy(absName)   # noqa
            except OSError as e:
                logger.warning(f"Cannot copy {image.name} to {absName.as_posix()}: {e}")
            else:
                self._worker.sequences.increment(incrementSessionNb, incrementStoredNb)
                downloadedImagesInfo.append((image.path, downloadTime, absName))
            self._worker.publishData("downloaded_images_count", count)

        if not stopped:
            logger.info(f"{count} images downloaded.")
            self._worker.publishData(
                "download_completed",
                f"Download completed! {count} images downloaded.",
                downloadedImagesInfo
            )
        else:
            self._worker.publishData(
                "download_cancelled",
                f"Download cancelled! {count} / {selectedImagesCount} images downloaded.",
                downloadedImagesInfo
            )

    def _renameImage(self, image: "Image", downloadTime: datetime = datetime.now()) -> str:
        return self._worker.imageNamingTemplate.format(
            image, self._worker.sequences, downloadTime
        )

    def _makeDestinationFolder(self, image: "Image", downloadTime: datetime = datetime.now()) -> Path:
        return Path(
            self._worker.destinationNamingTemplate.format(
                image, self._worker.sequences, downloadTime, TemplateType.DESTINATION
            )
        )

    @staticmethod
    def _ensureNameUnicity(name: str, path: Path) -> str:
        i = 0
        rootName = Path(name).stem
        suffix = Path(name).suffix
        while (path / name).exists():
            i += 1
            name = f'{rootName}-{i}{suffix}'
        return name


class ImageMover(BackgroundWorker):
    ATTR_MAP = {
        "DATETIME": "datetime",
        "IS_SELECTED": "isSelected",
        "SESSION": "session",
    }

    class Command(Enum):
        STOP = auto()
        SET_DEST = auto()
        SET_IMG_TPL = auto()
        SET_DEST_TPL = auto()
        CLEAR_IMAGES = auto()
        ADD_IMAGES = auto()
        UPDATE_IMAGES_INFO = auto()
        GET_IMG_PREVIEW = auto()
        GET_FOLDERS_PREVIEW = auto()
        DOWNLOAD = auto()
        CANCEL = auto()
        SAVE_SEQ = auto()

    def __init__(self, conn):
        """
        Create a ImageMover process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__(conn, "ImagesMover")

        self.registerAction(self.Command.SET_DEST, self._setDestination)
        self.registerAction(self.Command.SET_IMG_TPL, self._setImageNamingTemplate)
        self.registerAction(self.Command.SET_DEST_TPL, self._setDestinationNamingTemplate)
        self.registerAction(self.Command.CLEAR_IMAGES, self._clearImages)
        self.registerAction(self.Command.ADD_IMAGES, self._addImages)
        self.registerAction(self.Command.UPDATE_IMAGES_INFO, self._updateImagesInfo)
        self.registerAction(self.Command.GET_IMG_PREVIEW, self._publishImagePreview)
        self.registerAction(self.Command.GET_FOLDERS_PREVIEW, self._publishFolderPreview)
        self.registerAction(self.Command.DOWNLOAD, self._download)
        self.registerAction(self.Command.CANCEL, self._stopDownloading)
        self.registerAction(self.Command.SAVE_SEQ, self._saveSequences)
        self.registerAction(self.Command.STOP, self._stop)

        self.sequences = Sequences()

        self.destination: Optional[Path] = None
        self.imageNamingTemplate: Optional[NamingTemplate] = None
        self.destinationNamingTemplate: Optional[NamingTemplate] = None
        self._images: Dict["ImageKey", "Image"] = dict()

        self._downloadHandler = None

    def _setDestination(self, path: str) -> None:
        # Update the ImageMover context with the destination path
        logger.debug(f"Update context, Destination is {path}...")
        self.destination = Path(path)

    def _setImageNamingTemplate(self, template: NamingTemplate) -> None:
        # Update the ImageMover context with the selected images naming template
        logger.debug(f"Update context, Images naming template is {template.name}...")
        self.imageNamingTemplate = template

    def _setDestinationNamingTemplate(self, template: NamingTemplate) -> None:
        # Update the ImageMover context with the selected destination naming template
        logger.debug(f"Update context, Destination naming template is {template.name}...")
        self.destinationNamingTemplate = template

    def _clearImages(self) -> None:
        # Clear images in the ImageMover context.
        logger.debug(f"Clear images in context...")
        self._images = dict()

    def _addImages(self, images: Dict["ImageKey", "Image"]) -> None:
        # Update the ImageMover context with the images in the selected source.
        logger.debug(f"Update context, adding {len(images)} images...")
        self._images.update(images)

    def _updateImagesInfo(
            self,
            imageKeys: List["ImageKey"],
            pty: "ImageProperty",
            value
    ) -> None:
        # Update images info to the passed value for passed image keys and info kind.
        logger.debug(f"Update images info {pty} for {len(imageKeys)} images...")
        try:
            attr = ImageMover.ATTR_MAP[pty.name]
        except KeyError:
            logger.warning(f"Cannot update images info: {pty.name} is unknown")

        else:
            for imageKey in imageKeys:
                try:
                    image = self._images[imageKey]
                except KeyError:
                    logger.warning(f"Cannot update image info: {imageKey} is not found")
                else:
                    setattr(image, attr, value)

    def _publishImagePreview(self, image: "Image") -> None:
        # Reply with preview of the given image sample according to the current context
        logger.debug("Compute and publish image sample preview...")
        imageTemplate = self.imageNamingTemplate
        destinationTemplate = self.destinationNamingTemplate
        if image is not None and imageTemplate is not None and destinationTemplate is not None:
            sequences = self.sequences
            sampleName = self.imageNamingTemplate.format(image, sequences, datetime.now())
            samplePath = self.destinationNamingTemplate.format(
                image, sequences, datetime.now(), TemplateType.DESTINATION
            )
            self.publishData("image_preview", sampleName, samplePath)

    def _publishFolderPreview(self) -> None:
        # Reply with preview of the "where to download folders" according to the
        # current context
        logger.debug("Compute and publish folders preview...")
        previewFolders = set()
        seen = list()
        for image in self._images.values():
            if image.isLoaded and image.isSelected:
                path = Path(
                    self.destinationNamingTemplate.format(
                        image, self.sequences, datetime.now(), TemplateType.DESTINATION
                    )
                )
                folder = self.destination
                absPath = folder / path
                if absPath in seen:
                    continue
                seen.append(absPath)
                previewFolders.add(absPath.as_posix())
        self.publishData("folder_preview", previewFolders)

    def _download(self) -> None:
        # Rename and download the selected image.
        logger.info("Rename and download the selected images...")
        selectedImages = [image for image in self._images.values() if image.isSelected]
        logger.debug(f"Start a new download handler")
        self._downloadHandler = DownloadHandler(selectedImages, self)
        self._downloadHandler.start()

    def _stopDownloading(self) -> None:
        # Cancel the current download.
        logger.info("Download cancelled...")
        downloadHandler = self._downloadHandler
        if downloadHandler and downloadHandler.is_alive():
            logger.info("Stopping download handler...")
            downloadHandler.stop()
            downloadHandler.join(timeout=2)
            if downloadHandler.is_alive():
                logger.warning("Cannot join download handler")
            else:
                logger.info("Download handler stopped")

    def _saveSequences(self) -> None:
        # Save the Sequences state to persistent file.
        logger.debug(f"Save the Sequences state to persistent file...")
        self.sequences.save()

    def _stop(self) -> None:
        self._stopDownloading()
        super()._stop()
