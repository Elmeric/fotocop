import logging
from typing import Tuple, List
from pathlib import Path
from multiprocessing import Process, Event
from enum import Enum, auto

from fotocop.util.logutil import LogConfig, configureRootLogger
from fotocop.util.threadutil import StoppableThread

logger = logging.getLogger(__name__)


class ScanHandler(StoppableThread):
    def __init__(self, path: str, subDirs: bool, conn, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "StoppableScanHandler"
        self._path = path
        self._subDirs = subDirs
        self._conn = conn

    @property
    def path(self) -> str:
        return f"{self._path}{' and its subfolders' if self._subDirs else ''}"

    def run(self) -> None:
        logger.info(f"Scanning images for {self.path}...")
        self._scanImages()

    def _scanImages(self):
        path = Path(self._path)
        walker = path.rglob("*") if self._subDirs else path.glob("*")
        imagesCount = 0
        batchesCount = 0
        imagesBatch = list()
        stopped = False
        for f in walker:
            if self.stopped():
                logger.info(f"Stop scanning images for {self.path}")
                stopped = True
                imagesBatch = list()
                break
            if self._isImage(f):
                imagesBatch.append((f.name, f.as_posix()))
                imagesCount += 1
                logger.debug(f"Found image: {imagesCount} - {f.name}")
                if imagesCount % ImageScanner.BATCH_SIZE == 0:
                    batchesCount += 1
                    logger.debug(f"Sending images: batch#{batchesCount}")
                    self._publishImagesBatch(batchesCount, imagesBatch)
                    imagesBatch = list()
        if imagesBatch:
            batchesCount += 1
            logger.debug(f"Sending remaining images: batch#{batchesCount}")
            self._publishImagesBatch(batchesCount, imagesBatch)
        if not stopped:
            logger.info(f"{imagesCount} images found and sent in {batchesCount} batches")

    @staticmethod
    def _isImage(path: Path) -> bool:
        return path.suffix.lower() in (".jpg", ".raf", ".nef", ".dng")

    def _publishImagesBatch(self, batch: int, images: List[Tuple[str, str]]):
        data = (f"images#{batch}", images)
        try:
            self._conn.send(data)
            logger.debug(f"Images sent: batch#{batch}")
        except (OSError, EOFError, BrokenPipeError):
            pass


class ImageScanner(Process):

    BATCH_SIZE = 10

    class Command(Enum):
        STOP = auto()   # Stop ImageScanner process
        SCAN = auto()   # Start scanning images
        ABORT = auto()  # Abort current scanning

    def __init__(self, conn):
        """
        Create a ImageScanner process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__()

        self.name = "ImageScanner"

        logConfig = LogConfig()
        self._logQueue = logConfig.logQueue
        self._logLevel = logConfig.logLevel

        self._conn = conn
        self._exitProcess = Event()

        self._scanHandler = None

    def run(self):
        """ImageScanner 'main loop'
        """

        configureRootLogger(self._logQueue, self._logLevel)

        self._exitProcess.clear()

        logger.info("Image scanner started")
        while True:
            self._handleCommand()
            if self._exitProcess.wait(timeout=0.01):
                break

        self._conn.close()
        logger.info("Image scanner stopped")

    def _handleCommand(self):
        """Poll the ImageScanner connection for task message.

        A task message is a tuple (action, arg)
        """
        # Check for command on the process connection
        conn = self._conn
        if conn.poll():
            action, arg = conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping image scanner...")
                self._exitProcess.set()
            elif action == self.Command.SCAN:
                # Scan images
                self._stopScanning()
                path, subDirs = arg
                logger.debug(f"Start a new scan handler")
                self._scanHandler = ScanHandler(path, subDirs, conn)
                self._scanHandler.start()
            else:
                logger.warning(f"Unknown command {action.name} ignored")

    def _stopScanning(self):
        scanHandler = self._scanHandler
        if scanHandler and scanHandler.is_alive():
            path = scanHandler.path
            logger.debug(f"Stop scan handler for {path}")
            scanHandler.stop()
            scanHandler.join(timeout=0.5)
            if scanHandler.is_alive():
                logger.warning(f"Cannot join scan handler for {path}")
            else:
                logger.debug(f"Join scan handler for {path}")
