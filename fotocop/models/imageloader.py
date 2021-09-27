import logging
import time
from typing import Tuple, List
from pathlib import Path
from multiprocessing import Process, Event
from enum import Enum, auto

from fotocop.util.logutil import LogConfig, configureRootLogger

logger = logging.getLogger(__name__)


class ImageLoader(Process):

    BATCH_SIZE = 3

    class Command(Enum):
        STOP = auto()
        SCAN = auto()

    def __init__(self, conn):
        """
        Create a ImageLoader process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__()

        self.name = "ImageLoader"

        logConfig = LogConfig()
        self.logQueue = logConfig.logQueue
        self.logLevel = logConfig.logLevel

        self.conn = conn
        self.exitProcess = Event()
        # self.exifTool = None

    def run(self):
        """ImageLoader 'main loop'
        """

        # Start the exiftool process
        # self.exifTool = exiftool.ExifTool()
        # self.exifTool.start()

        configureRootLogger(self.logQueue, self.logLevel)

        self.exitProcess.clear()

        logger.info("Image loader started")
        while True:
            self.handleCommand()
            if self.exitProcess.wait(timeout=0.01):
                break

        self.conn.close()
        logger.info("Image loader stopped")
        # self.exifTool.terminate()

    def handleCommand(self):
        """Poll the ImageLoader connection for task message.

        A task message is a tuple (action, arg)
        """
        # Check for command on the process connection
        if self.conn.poll():
            action, arg = self.conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping image loader...")
                self.exitProcess.set()
            elif action == self.Command.SCAN:
                # Scan images
                path, subDirs = arg
                logger.info(f"Scanning {path}{' and its subfolders' if subDirs else ''} for images...")
                self.scanImages(Path(path), subDirs)
            else:
                logger.warning(f"Unknown command {action.name} ignored")

    def scanImages(self, path: Path, subDirs: bool):
        walker = path.rglob("*") if subDirs else path.glob("*")
        imagesCount = 0
        batchesCount = 0
        imagesBatch = list()
        for f in walker:
            if self._isImage(f):
                imagesBatch.append((f.name, f.as_posix()))
                imagesCount += 1
                logger.debug(f"Found image: {imagesCount} - {f.name}")
                if imagesCount % ImageLoader.BATCH_SIZE == 0:
                    batchesCount += 1
                    logger.debug(f"Sending images: batch#{batchesCount}")
                    self.publishImagesBatch(batchesCount, imagesBatch)
                    imagesBatch = list()
        if imagesBatch:
            batchesCount += 1
            logger.debug(f"Sending remaining images: batch#{batchesCount}")
            self.publishImagesBatch(batchesCount, imagesBatch)
        logger.info(f"{imagesCount} images found and sent in {batchesCount} batches")

    @staticmethod
    def _isImage(path: Path) -> bool:
        return path.suffix.lower() in (".jpg", ".raf", ".nef", ".dng")

    def publishImagesBatch(self, batch: int, images: List[Tuple[str, str]]):
        data = (f"images#{batch}", images)
        try:
            self.conn.send(data)
            logger.debug(f"Images sent: batch#{batch}")
        except (OSError, EOFError, BrokenPipeError):
            pass
