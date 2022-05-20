import logging
from typing import TYPE_CHECKING, Tuple, Optional, List, Dict, Iterable
from datetime import datetime
from pathlib import Path

from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Singleton, DelegatedAttribute
from fotocop.models import settings as Config
from fotocop.models.sources import Image, ImageProperty
from fotocop.models.naming import (Case, TemplateType, NamingTemplates)
from fotocop.models.workerproxy import ImageMover

if TYPE_CHECKING:
    from fotocop.models.sources import Source, ImageKey

logger = logging.getLogger(__name__)


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
        self._source: Optional["Source"] = None
        self._imageSample = None

        # Start the images' mover process and establish a Pipe connection with it
        self._imageMover = ImageMover(name="ImageMover")
        self._imageMover.subscribe("image_preview", self.receiveImageSamplePreview)
        self._imageMover.subscribe("folder_preview", self.receiveFolderPreview)
        self._imageMover.subscribe("selected_images_count", self.downloadStarted)
        self._imageMover.subscribe("downloaded_images_count", self.downloadStatus)
        self._imageMover.subscribe("download_completed", self.downloadComplete)
        self._imageMover.subscribe("download_cancelled", self.downloadCancelled)

    def setSourceSelection(self, source: "Source"):
        """Call on SourceManager.sourceSelected signal."""
        self._source = source
        self._imageSample = source.imageSample
        self._imageMover.clearImages()
        self._imageMover.getFoldersPreview()
        self._imageMover.getImageSamplePreview(self._imageSample)

    def addImages(self, images: Dict["ImageKey", "Image"]) -> None:
        self._imageMover.addImages(images)

    def updateImagesInfo(
            self,
            imageKeys: List["ImageKey"],
            pty: "ImageProperty",
            value
    ) -> None:
        """Call on SourceManager.imagesInfoChanged signal."""
        self._imageMover.updateImagesInfo(imageKeys, pty, value)
        if pty is ImageProperty.SESSION:
            self._imageMover.getImageSamplePreview(self._imageSample)
        if self._source is not None and self._source.timelineBuilt:
            self._imageMover.getFoldersPreview()

    def updateImageSample(self):
        """Call on SourceManager.imageSampleChanged signal."""
        self._imageSample = self._source.imageSample
        self._imageMover.getImageSamplePreview(self._imageSample)

    def selectDestination(self, destination: Path) -> None:
        self.destination = destination
        Config.fotocopSettings.lastDestination = destination
        self._imageMover.setDestination(destination.as_posix())
        self.destinationSelected.emit(destination)

    def setNamingTemplate(self, kind: "TemplateType", key: str):
        if kind == TemplateType.IMAGE:
            self._setImageNamingTemplate(key)
            self._imageMover.getImageSamplePreview(self._imageSample)
        else:
            assert kind == TemplateType.DESTINATION
            self._setDestinationNamingTemplate(key)
            self._imageMover.getFoldersPreview()

    def setExtension(self, extensionKind: Case):
        template = self.imageNamingTemplate
        template.extension = extensionKind
        Config.fotocopSettings.lastNamingExtension = extensionKind.name
        self._imageMover.setImageTemplate(template)
        self.imageNamingExtensionSelected.emit(extensionKind)
        self._imageMover.getImageSamplePreview(self._imageSample)

    def download(self) -> None:
        self._imageMover.startDownload()

    def cancelDownload(self) -> None:
        self._imageMover.cancelDownload()

    def markImagesAsPreviouslyDownloaded(
            self,
            downloadedImagesInfo: List[Tuple[str, datetime, Path]]
    ) -> None:
        self._source.markImagesAsPreviouslyDownloaded(downloadedImagesInfo)

    def saveSequences(self):
        self._imageMover.saveSequences()

    def receiveImageSamplePreview(self, name: str, path: str) -> None:
        logger.debug(f"Received image sample preview: {name}, {path}")
        self.imageSampleChanged.emit(name, Path(path).as_posix())

    def receiveFolderPreview(self, folders: Iterable[str]) -> None:
        logger.debug(f"Received folder preview: {folders}")
        self.folderPreviewChanged.emit(folders)

    def downloadStarted(self, count: int) -> None:
        logger.debug(f"{count} images to download")
        self.backgroundActionStarted.emit(f"Downloading {count} images...", count)

    def downloadStatus(self, count: int) -> None:
        self.backgroundActionProgressChanged.emit(count)

    def downloadComplete(self, msg: str, imagesInfo: List[Tuple[str, datetime, Path]]) -> None:
        self.markImagesAsPreviouslyDownloaded(imagesInfo)
        self.backgroundActionCompleted.emit(msg)

    def downloadCancelled(self, msg: str, imagesInfo: List[Tuple[str, datetime, Path]]) -> None:
        self.markImagesAsPreviouslyDownloaded(imagesInfo)
        self.backgroundActionCompleted.emit(msg)

    def close(self) -> None:
        # Organize a kindly shutdown when quitting the application

        # Stop and join the images' mover process ant its listener thread
        logger.info("Request images mover to stop...")
        self._imageMover.stop()

    def _setImageNamingTemplate(self, key: str):
        template = self.getNamingTemplateByKey(TemplateType.IMAGE, key)
        # Keep previously selected extension unchanged
        template.extension = self.imageNamingTemplate.extension
        self.imageNamingTemplate = template
        Config.fotocopSettings.lastImageNamingTemplate = key
        self._imageMover.setImageTemplate(template)
        self.imageNamingTemplateSelected.emit(key)
        self._checkRequiredInfos()

    def _setDestinationNamingTemplate(self, key: str):
        template = self.getNamingTemplateByKey(TemplateType.DESTINATION, key)
        self.destinationNamingTemplate = template
        Config.fotocopSettings.lastDestinationNamingTemplate = key
        self._imageMover.setDestinationTemplate(template)
        self.destinationNamingTemplateSelected.emit(key)
        self._checkRequiredInfos()

    def _checkRequiredInfos(self):
        sessionRequired = self.imageNamingTemplate.sessionRequired or self.destinationNamingTemplate.sessionRequired
        self.sessionRequired.emit(sessionRequired)
        datetimeRequired = self.imageNamingTemplate.datetimeRequired or self.destinationNamingTemplate.datetimeRequired
        self.datetimeRequired.emit(datetimeRequired)
