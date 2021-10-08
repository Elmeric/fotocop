import logging
import time
from typing import Tuple, List
from pathlib import Path
from multiprocessing import Process, Event
from threading import  Thread, current_thread
from enum import Enum, auto

from fotocop.util.logutil import LogConfig, configureRootLogger

logger = logging.getLogger(__name__)


class StoppableThread(Thread):
    """Thread class with a stop() method. The thread itself has to check
    regularly for the stopped() condition."""
    # https://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread

    def __init__(self,  *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._stop_event = Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


class ImageScanner(Process):

    BATCH_SIZE = 10

    class Command(Enum):
        STOP = auto()   # Stop ImageScanner process
        SCAN = auto()   # Start scanning images
        ABORT = auto()  # Abort current scanning

    def __init__(self, conn, scanInProgress: Event):
        """
        Create a ImageScanner process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__()

        self.name = "ImageScanner"

        logConfig = LogConfig()
        self.logQueue = logConfig.logQueue
        self.logLevel = logConfig.logLevel

        self.conn = conn
        self.scanInProgress = scanInProgress
        self.exitProcess = Event()

    def run(self):
        """ImageScanner 'main loop'
        """

        configureRootLogger(self.logQueue, self.logLevel)

        self.exitProcess.clear()
        self.scanInProgress.clear()

        # abortHandler = Thread(target=self.scanAbortHandler, args=(self.abortScanning,))
        # abortHandler.start()

        logger.info("Image scanner started")
        while True:
            self.handleCommand()
            if self.exitProcess.wait(timeout=0.01):
                break

        # abortHandler.join()
        self.conn.close()
        logger.info("Image scanner stopped")

    def handleCommand(self):
        """Poll the ImageScanner connection for task message.

        A task message is a tuple (action, arg)
        """
        # Check for command on the process connection
        if self.conn.poll():
            action, arg = self.conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping image scanner...")
                self.exitProcess.set()
            elif action == self.Command.ABORT:
                # Abort images scanning
                logger.info(f"Stop scanning thread {self.scanHandler.name}")
                self.scanHandler.stop()
                self.scanHandler.join(timeout=0.5)
                if self.scanHandler.is_alive():
                    logger.info(f"Cannot join scanning thread {self.scanHandler.name}")
                else:
                    logger.info(f"Join scanning thread {self.scanHandler.name}")
            elif action == self.Command.SCAN:
                # Scan images
                self.scanInProgress.set()
                path, subDirs = arg
                logger.info(f"Scanning {path}{' and its subfolders' if subDirs else ''} for images...")
                self.scanHandler = StoppableThread(target=self.scanImages, name=path, args=(path, subDirs,))
                self.scanHandler.start()
            else:
                logger.warning(f"Unknown command {action.name} ignored")

    def scanImages(self, path: str, subDirs: bool):
        path = Path(path)
        walker = path.rglob("*") if subDirs else path.glob("*")
        imagesCount = 0
        batchesCount = 0
        imagesBatch = list()
        stopped = False
        for f in walker:
            if self.scanHandler.stopped():
                logger.info(f"Stop scanning images for {self.scanHandler.name}")
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
                    self.publishImagesBatch(batchesCount, imagesBatch)
                    imagesBatch = list()
        if imagesBatch:
            batchesCount += 1
            logger.debug(f"Sending remaining images: batch#{batchesCount}")
            self.publishImagesBatch(batchesCount, imagesBatch)
        if not stopped:
            logger.info(f"{imagesCount} images found and sent in {batchesCount} batches")
            self.scanInProgress.clear()

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
