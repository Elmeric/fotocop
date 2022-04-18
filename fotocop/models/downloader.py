import logging
from typing import TYPE_CHECKING, Tuple, Optional, List
from datetime import datetime
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

                    elif content == "selected_images_count":
                        selectedImagesCount, *_ = data
                        logger.debug(
                            f"{selectedImagesCount} images to download"
                        )
                        downloader.backgroundActionStarted.emit(
                            f"Downloading {selectedImagesCount} images...", selectedImagesCount
                        )

                    elif content == "downloaded_images_count":
                        downloadedImagesCount, *_ = data
                        downloader.backgroundActionProgressChanged.emit(
                            downloadedImagesCount
                        )

                    elif content == "download_completed":
                        downloadedImagesCount, downloadedImagesInfo = data
                        downloader.markImagesAsPreviouslyDownloaded(downloadedImagesInfo)
                        downloader.backgroundActionCompleted.emit(downloadedImagesCount)

                    elif content == "download_cancelled":
                        downloadedImagesCount, downloadedImagesInfo = data
                        downloader.markImagesAsPreviouslyDownloaded(downloadedImagesInfo)
                        downloader.backgroundActionCompleted.emit(downloadedImagesCount)

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
    datetimeRequired = QtUtil.QtSignalAdapter(bool)
    folderPreviewChanged = QtUtil.QtSignalAdapter(set)
    backgroundActionStarted = QtUtil.QtSignalAdapter(str, int)  # msg, max value
    backgroundActionProgressChanged = QtUtil.QtSignalAdapter(int)  # progress value
    backgroundActionCompleted = QtUtil.QtSignalAdapter(str)  # msg
    backgroundActionCancelled = QtUtil.QtSignalAdapter(str)  # msg

    listBuiltinNamingTemplates = DelegatedAttribute("_namingTemplates", "listBuiltins")
    listCustomNamingTemplates = DelegatedAttribute("_namingTemplates", "listCustoms")
    getNamingTemplateByKey = DelegatedAttribute("_namingTemplates", "getByKey")
    getDefaultNamingTemplate = DelegatedAttribute("_namingTemplates", "getDefault")
    addCustomNamingTemplate = DelegatedAttribute("_namingTemplates", "add")
    deleteCustomNamingTemplate = DelegatedAttribute("_namingTemplates", "delete")
    changeCustomNamingTemplate = DelegatedAttribute("_namingTemplates", "change")
    saveCustomNamingTemplates = DelegatedAttribute("_namingTemplates", "save")

    def __init__(self):
        self.destination: Optional[Path] = None
        namingTemplates = NamingTemplates()

        self.imageNamingTemplate = namingTemplates.getDefault(TemplateType.IMAGE)
        self.destinationNamingTemplate = namingTemplates.getDefault(TemplateType.DESTINATION)

        self._namingTemplates = namingTemplates
        self._source: Optional["Selection"] = None
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
        source = self._source
        if source is None:
            return

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
        self._imageMoverConnection.send((ImageMover.Command.DOWNLOAD, 0))

    def cancelDownload(self) -> None:
        self._imageMoverConnection.send((ImageMover.Command.CANCEL, 0))

    def markImagesAsPreviouslyDownloaded(
            self,
            downloadedImagesInfo: List[Tuple[str, datetime, Path]]
    ) -> None:
        self._source.markImagesAsPreviouslyDownloaded(downloadedImagesInfo)

    def saveSequences(self):
        self._imageMoverConnection.send((ImageMover.Command.SAVE_SEQ, 0))

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
        self._checkRequiredInfos()

    def _setDestinationNamingTemplate(self, key: str):
        template = self.getNamingTemplateByKey(TemplateType.DESTINATION, key)
        self.destinationNamingTemplate = template
        Config.fotocopSettings.lastDestinationNamingTemplate = key
        self._imageMoverConnection.send((ImageMover.Command.SET_DEST_TPL, template))
        self.destinationNamingTemplateSelected.emit(key)
        self._checkRequiredInfos()

    def _updateImages(self) -> None:
        source = self._source
        if source is None:
            return

        self._imageMoverConnection.send(
            (ImageMover.Command.SET_IMAGES, self._source.images)
        )

    def _updatePreview(self, imageOnly: bool = False) -> None:
        # Update image sample name and path.
        self._imageMoverConnection.send(
            (ImageMover.Command.GET_IMG_PREVIEW, self._imageSample)
        )

        if imageOnly:
            return

        # Update folders preview
        self._imageMoverConnection.send((ImageMover.Command.GET_FOLDERS_PREVIEW, 0))

    @staticmethod
    def _makeDefaultImageSample() -> "Image":
        imageSample = Image("IMG_0001.RAF", "L:/path/to/images")
        d = datetime.today()
        imageSample.datetime = Datation(
            str(d.year), str(d.month), str(d.day),
            str(d.hour), str(d.minute), str(d.second)
        )
        return imageSample

    def _checkRequiredInfos(self):
        sessionRequired = self.imageNamingTemplate.sessionRequired or self.destinationNamingTemplate.sessionRequired
        self.sessionRequired.emit(sessionRequired)
        datetimeRequired = self.imageNamingTemplate.datetimeRequired or self.destinationNamingTemplate.datetimeRequired
        self.datetimeRequired.emit(datetimeRequired)
