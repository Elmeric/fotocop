import logging
from typing import Tuple, List
from pathlib import Path
from multiprocessing import Process, Event

from fotocop.util.logutil import configureRootLogger

logger = logging.getLogger(__name__)


class ImageLoader(Process):

    BATCH_SIZE = 3

    def __init__(self, conn, logConfig):
        """
        Create a ImageLoader process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__()

        self.name = "ImageLoader"

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
            if action == 'stop':
                # Stop the 'main' loop
                logger.info("Stopping image loader...")
                self.exitProcess.set()
            elif action == 'load':
                # Load images
                path, subDirs = arg
                logger.info(f"Scanning {path}{' and its subfolders' if subDirs else ''} for images...")
                self.loadImages(Path(path), subDirs)
            else:
                logger.warning(f"Unknown command {action} ignored")

    def loadImages(self, path: Path, subDirs: bool):
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
                    self.publishData(batchesCount, imagesBatch)
                    imagesBatch = list()
        if imagesBatch:
            batchesCount += 1
            logger.debug(f"Sending remaining images: batch#{batchesCount}")
            self.publishData(batchesCount, imagesBatch)
        logger.info(f"{imagesCount} images found and sent in {batchesCount} batches")

    @staticmethod
    def _isImage(path: Path) -> bool:
        return path.suffix.lower() in (".jpg", ".raf", ".nef", ".dng")

    def publishData(self, batch: int, images: List[Tuple[str, str]]):
        data = (f"images#{batch}", images)
        try:
            self.conn.send(data)
            logger.debug(f"Images sent: batch#{batch}")
        except (OSError, EOFError, BrokenPipeError):
            pass
