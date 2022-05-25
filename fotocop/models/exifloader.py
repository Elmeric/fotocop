import logging
import base64
from typing import TYPE_CHECKING
from enum import Enum, auto

from fotocop.util import exiftool
from fotocop.util.workerutil import BackgroundWorker

if TYPE_CHECKING:
    from fotocop.models.sources import ImageKey
logger = logging.getLogger(__name__)


class ExifLoader(BackgroundWorker):

    class Command(Enum):
        STOP = auto()
        LOAD_THUMB = auto()
        LOAD_DATE = auto()
        LOAD_ALL = auto()

    def __init__(self, conn):
        """
        Create a ExifLoader process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__(conn, "ExifLoader")

        self.registerAction(self.Command.LOAD_THUMB, self._loadThumbnail)
        self.registerAction(self.Command.LOAD_DATE, self._loadDatetime)
        self.registerAction(self.Command.LOAD_ALL, self._loadExif)
        self.registerAction(self.Command.STOP, self._stop)

        self.exifTool = None

    def _preRun(self) -> None:
        # Start the exiftool process
        logger.info("Starting ExifTool...")
        self.exifTool = exiftool.ExifTool()
        self.exifTool.start()

    def _postRun(self) -> None:
        logger.info("Stopping ExifTool...")
        self.exifTool.terminate()

    def _loadExif(self, imageKey: "ImageKey"):
        logger.debug(f"Loading date and thumbnail from exif for {imageKey}...")
        exif = self.exifTool.get_tags(
            [
                "EXIF:ThumbnailImage",
                "EXIF:ThumbnailTIFF",
                "EXIF:ImageWidth",
                "EXIF:ImageHeight",
                "EXIF:ExifImageWidth",
                "EXIF:ExifImageHeight",
                "EXIF:Orientation",
                "EXIF:DateTimeOriginal",
            ],
            imageKey,
        )
        dateTime = None
        try:
            dateTime = exif["EXIF:DateTimeOriginal"]
        except KeyError:
            pass
        if dateTime:  # "YYYY:MM:DD HH:MM:SS"
            date, time_ = dateTime.split(" ", 1)
            year, month, day = date.split(":")
            hour, minute, second = time_.split(":")
            dateTime = (year, month, day, hour, minute, second)  # noqa
        else:
            dateTime = ('1970', '01', '01', '00', '00', '00')
        self.publishData("datetime", imageKey, dateTime)

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

        thumbData = (b"", aspectRatio, orientation)
        if imgstring:
            imgstring = imgstring[7:]
            imgdata = base64.b64decode(imgstring)
            thumbData = (imgdata, aspectRatio, orientation)

        self.publishData("thumbnail", imageKey, thumbData)

    def _loadThumbnail(self, imageKey: "ImageKey"):
        logger.debug(f"Loading thumbnail from exif for {imageKey}...")
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
            imageKey,
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

        thumbData = (b"", 0, 0)
        if imgstring:
            imgstring = imgstring[7:]
            imgdata = base64.b64decode(imgstring)
            thumbData = (imgdata, aspectRatio, orientation)

        self.publishData("thumbnail", imageKey, thumbData)

    def _loadDatetime(self, imageKey: "ImageKey"):
        logger.debug(f"Loading date time from exif for {imageKey}...")
        dateTime = self.exifTool.get_tag("EXIF:DateTimeOriginal", imageKey)
        if dateTime:  # "YYYY:MM:DD HH:MM:SS"
            date, time_ = dateTime.split(" ", 1)
            year, month, day = date.split(":")
            hour, minute, second = time_.split(":")
            dateTime = (year, month, day, hour, minute, second)  # noqa
        else:
            dateTime = ('1970', '01', '01', '00', '00', '00')
        self.publishData("datetime", imageKey, dateTime)
