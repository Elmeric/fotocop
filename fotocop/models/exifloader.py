import logging
import base64
from typing import Tuple
from multiprocessing import Process, Event
from enum import Enum, auto

from fotocop.util import exiftool
from fotocop.util.logutil import LogConfig, configureRootLogger

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
        logger.info("Exif loader stopped")
        logger.info("Stopping ExifTool...")
        self.exifTool.terminate()

    def handleCommand(self):
        """Poll the ExifLoader connection for task message.

        A task message is a tuple (action, arg)
        """
        # Check for command on the process connection
        if self.conn.poll():
            action, image = self.conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping exif loader...")
                self.exitProcess.set()
            elif action == self.Command.LOAD_ALL:
                # Load date/time and thumbnail
                name, path = image
                logger.debug(f"Loading date and thumbnail from exif for {name}...")
                self.loadExif(image)
            elif action == self.Command.LOAD_THUMB:
                # Load thumbnail
                name, path = image
                logger.debug(f"Loading thumbnail from exif for {name}...")
                self.loadThumbnail(image)
            elif action == self.Command.LOAD_DATE:
                # Load date/time
                name, path = image
                logger.debug(f"Loading date time from exif for {name}...")
                self.loadDatetime(image)
            else:
                logger.warning(f"Unknown command {action.name} ignored")

    def loadExif(self, image: Tuple[str, str]):
        name, path = image
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
            path,
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
        self.publishDateTime(dateTime, path)

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

        thumbData = (None, 0, 0)
        if imgstring:
            imgstring = imgstring[7:]
            imgdata = base64.b64decode(imgstring)
            thumbData = (imgdata, aspectRatio, orientation)

        self.publishThumbnail(thumbData, path)

    def loadThumbnail(self, image: Tuple[str, str]):
        name, path = image
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

        thumbData = (None, 0, 0)
        if imgstring:
            imgstring = imgstring[7:]
            imgdata = base64.b64decode(imgstring)
            thumbData = (imgdata, aspectRatio, orientation)

        self.publishThumbnail(thumbData, path)

    def loadDatetime(self, image: Tuple[str, str]):
        name, path = image
        dateTime = self.exifTool.get_tag("EXIF:DateTimeOriginal", path)
        if dateTime:  # "YYYY:MM:DD HH:MM:SS"
            date, time_ = dateTime.split(" ", 1)
            year, month, day = date.split(":")
            hour, minute, second = time_.split(":")
            dateTime = (year, month, day, hour, minute, second)  # noqa
        else:
            dateTime = ('1970', '01', '01', '00', '00', '00')
        self.publishDateTime(dateTime, path)

    def publishDateTime(self, datetime: tuple, imageKey: str):
        data = (f"datetime", datetime, imageKey)
        try:
            self.conn.send(data)
            logger.debug(f"Date time sent for image: {imageKey}")
        except (OSError, EOFError, BrokenPipeError):
            pass

    def publishThumbnail(self, thumbnail: tuple, imageKey: str):
        data = (f"thumbnail", thumbnail, imageKey)
        try:
            self.conn.send(data)
            logger.debug(f"Thumbnail sent for image: {imageKey}")
        except (OSError, EOFError, BrokenPipeError):
            pass
