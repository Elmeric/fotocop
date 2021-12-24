from typing import TYPE_CHECKING, List, Dict
from datetime import datetime

from fotocop.util import qtutil as QtUtil
from fotocop.models.sources import SourceManager, Image, Datation
from fotocop.models.naming import (
    NamingTemplates,
    ImageNameGenerator,
    DestinationNameGenerator,
)

if TYPE_CHECKING:
    from fotocop.models.sources import Selection
    from fotocop.models.naming import NamingTemplate


class Downloader:

    imageSampleChanged = QtUtil.QtSignalAdapter(Image)

    def __init__(self):
        self.source = None
        self.namingTemplates = NamingTemplates()
        self.imageNamingTemplate = self.namingTemplates.builtinImageNamingTemplates[
            NamingTemplates.defaultImageNamingTemplate
        ]
        self.destinationNamingTemplate = None
        self.imageNameGenerator = ImageNameGenerator(self.imageNamingTemplate)
        self.destinationNameGenerator = None
        self.imageSample = Image("IMG_0001.RAF", "L:/path/to/images")
        self.imageSample.datetime = Datation("2021", "12", "23", "21", "5", "30")
        self.images = {self.imageSample.name: self.imageSample}
        self.imageSampleChanged.emit(self.imageSample)

    def setImageNamingTemplate(self, key: str):
        template = self.namingTemplates.getImageNamingTemplate(key)
        self.imageNamingTemplate = template
        self.imageNameGenerator = ImageNameGenerator(template)
        self.updateImageSample()

    def setExtension(self, extensionKind: str):
        self.imageNamingTemplate.extension = extensionKind
        self.updateImageSample()

    def setDestinationNamingTemplate(self, template: "NamingTemplate"):
        self.destinationNamingTemplate = template
        self.destinationNameGenerator = DestinationNameGenerator(template)

    def renameImage(self, image: "Image") -> str:
        return self.imageNameGenerator.generate(image, seq=1)

    def download(self, images: List["Image"]):
        seq = 0
        for image in images:
            if image.isSelected:
                seq += 1
                name = self.imageNameGenerator.generate(image, seq)
                path = self.destinationNameGenerator.generate(image, seq) / name
                print(f"{path.as_posix()}")

    def setSourceSelection(self, selection: "Selection"):
        self.source = selection
        images = selection.images
        if len(images) > 0:
            imageKey = next(iter(images))
            self.imageSample = images[imageKey]
            self.images = images
        else:
            self.imageSample = Image("IMG_0001.RAF", "L:/path/to/images")
            d = datetime.today()
            self.imageSample.datetime = Datation(
                str(d.year), str(d.month), str(d.day),
                str(d.hour), str(d.minute), str(d.second)
            )
            self.images = {self.imageSample.name: self.imageSample}
        self.imageSampleChanged.emit(self.imageSample)

    def updateImageSample(self):
        images = self.source.images
        if images:
            imageKey = next(iter(images))
            self.imageSample = images[imageKey]
            self.images = images
            self.imageSampleChanged.emit(self.imageSample)
