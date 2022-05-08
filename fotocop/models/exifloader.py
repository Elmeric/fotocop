import logging
import base64
from typing import TYPE_CHECKING, Tuple
from multiprocessing import Process, Event
from enum import Enum, auto

from fotocop.util import exiftool
from fotocop.util.logutil import LogConfig, configureRootLogger

if TYPE_CHECKING:
    from fotocop.models.sources import ImageKey
logger = logging.getLogger(__name__)


class ExifLoader(Process):

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
        super().__init__()

        self.name = "ExifLoader"

        logConfig = LogConfig()
        self.logQueue = logConfig.logQueue
        self.logLevel = logConfig.logLevel

        self.conn = conn
        self.exitProcess = Event()
        self.exifTool = None

    def run(self):
        """ExifLoader 'main loop'
        """
        configureRootLogger(self.logQueue, self.logLevel)

        # Start the exiftool process
        logger.info("Starting ExifTool...")
        self.exifTool = exiftool.ExifTool()
        self.exifTool.start()

        self.exitProcess.clear()

        logger.info("Exif loader started")
        while True:
            self.handleCommand()
            if self.exitProcess.wait(timeout=0.01):
                break

        self.conn.close()
        logger.info("Stopping ExifTool...")
        self.exifTool.terminate()
        logger.info("Exif loader stopped")

    def handleCommand(self):
        """Poll the ExifLoader connection for task message.

        A task message is a tuple (action, arg)
        """
        # Check for command on the process connection
        if self.conn.poll():
            action, imageKey = self.conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping exif loader...")
                self.exitProcess.set()
            elif action == self.Command.LOAD_ALL:
                # Load date/time and thumbnail
                logger.debug(f"Loading date and thumbnail from exif for {imageKey}...")
                self.loadExif(imageKey)
            elif action == self.Command.LOAD_THUMB:
                # Load thumbnail
                logger.debug(f"Loading thumbnail from exif for {imageKey}...")
                self.loadThumbnail(imageKey)
            elif action == self.Command.LOAD_DATE:
                # Load date/time
                logger.debug(f"Loading date time from exif for {imageKey}...")
                self.loadDatetime(imageKey)
            else:
                logger.warning(f"Unknown command {action.name} ignored")

    def loadExif(self, imageKey: "ImageKey"):
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
        self.publishDateTime(dateTime, imageKey)

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

        self.publishThumbnail(thumbData, imageKey)

    def loadThumbnail(self, imageKey: "ImageKey"):
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

        self.publishThumbnail(thumbData, imageKey)

    def loadDatetime(self, imageKey: "ImageKey"):
        dateTime = self.exifTool.get_tag("EXIF:DateTimeOriginal", imageKey)
        if dateTime:  # "YYYY:MM:DD HH:MM:SS"
            date, time_ = dateTime.split(" ", 1)
            year, month, day = date.split(":")
            hour, minute, second = time_.split(":")
            dateTime = (year, month, day, hour, minute, second)  # noqa
        else:
            dateTime = ('1970', '01', '01', '00', '00', '00')
        self.publishDateTime(dateTime, imageKey)

    def publishDateTime(
            self,
            datetime: Tuple[str, str, str, str, str, str],
            imageKey: "ImageKey"
    ):
        data = (f"datetime", datetime, imageKey)
        try:
            self.conn.send(data)
            logger.debug(f"Date time sent for image: {imageKey}")
        except (OSError, EOFError, BrokenPipeError):
            pass

    def publishThumbnail(self, thumbnail: tuple, imageKey: "ImageKey"):
        data = (f"thumbnail", thumbnail, imageKey)
        try:
            self.conn.send(data)
            logger.debug(f"Thumbnail sent for image: {imageKey}")
        except (OSError, EOFError, BrokenPipeError):
            pass
