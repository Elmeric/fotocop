import logging
from typing import Tuple, List, Optional
from pathlib import Path
from enum import Enum, auto

from fotocop.util.threadutil import StoppableThread
from fotocop.util.workerutil import BackgroundWorker, Message
from fotocop.models.sqlpersistence import DownloadedDB, FileDownloaded

logger = logging.getLogger(__name__)


class ScanHandler(StoppableThread):
    def __init__(self, path: str, subDirs: bool, conn, db: DownloadedDB, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "StoppableScanHandler"
        self._path = path
        self._subDirs = subDirs
        self._conn = conn
        self._downloadedDb = db

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
        try:
            for f in walker:
                if self.stopped():
                    logger.info(f"Stop scanning images for {self.path}")
                    stopped = True
                    imagesBatch = list()
                    break
                if self._isImage(f):
                    previouslyDownloaded = self._isAlreadyDownloaded(f)
                    if previouslyDownloaded is not None:
                        downloadPath, downloadTime = previouslyDownloaded
                    else:
                        downloadPath, downloadTime = (None, None)
                    imagesBatch.append(
                        (f.name, f.as_posix(), downloadPath, downloadTime)
                    )
                    imagesCount += 1
                    logger.debug(f"Found image: {imagesCount} - {f.name}")
                    if imagesCount % ImageScanner.BATCH_SIZE == 0:
                        batchesCount += 1
                        logger.debug(f"Sending images: batch#{batchesCount}")
                        self._publishImagesBatch(batchesCount, imagesBatch)
                        imagesBatch = list()
        except OSError as e:
            logger.error(f"Cannot scan images in {self.path}: {e}")
        finally:
            if imagesBatch:
                batchesCount += 1
                logger.debug(f"Sending remaining images: batch#{batchesCount}")
                self._publishImagesBatch(batchesCount, imagesBatch)
            if not stopped:
                logger.info(f"{imagesCount} images found and sent in {batchesCount} batches")
            self._publishScanComplete(imagesCount, stopped)

    @staticmethod
    def _isImage(path: Path) -> bool:
        return path.suffix.lower() in (".jpg", ".raf", ".nef", ".dng")

    def _isAlreadyDownloaded(self, imagePath: Path) -> Optional[FileDownloaded]:
        name = imagePath.name
        stat = imagePath.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        return self._downloadedDb.fileIsPreviouslyDownloaded(name, size, mtime)

    def _publishImagesBatch(self, batch: int, images: List[Tuple[str, str, str, float]]):
        data = Message("images", (batch, images))
        try:
            self._conn.send(data)
            logger.debug(f"Images sent: batch#{batch}")
        except (OSError, EOFError, BrokenPipeError):
            pass

    def _publishScanComplete(self, imagesCount: int, stopped: bool):
        data = Message("ScanComplete", (imagesCount, stopped))
        try:
            self._conn.send(data)
            logger.info(f"{imagesCount} images found ({'stopped' if stopped else ''})")
        except (OSError, EOFError, BrokenPipeError):
            pass


class ImageScanner(BackgroundWorker):

    BATCH_SIZE = 500

    class Command(Enum):
        STOP = auto()   # Stop ImageScanner process
        SCAN = auto()   # Start scanning images
        ABORT = auto()  # Abort current scanning

    def __init__(self, conn) -> None:
        """
        Create a ImageScanner process instance and save the connection 'conn' to
        the main process.
        """
        super().__init__(conn, "ImageScanner")

        self._scanHandler = None

        self._downloadedDb = DownloadedDB()

    def _handleCommand(self):
        """Poll the ImageScanner connection for task message.

        A task message is a tuple (action, args) where action is a local Command enum
        and args is itself a tuple of params (empty tuple if the command has no params).
        """
        # Check for command on the process connection
        conn = self._conn
        if conn.poll():
            action, args = conn.recv()
            if action == self.Command.STOP:
                # Stop the 'main' loop
                logger.info("Stopping image scanner...")
                self._stopScanning()
                self._exitProcess.set()
            elif action == self.Command.ABORT:
                # Stop scanning images
                self._stopScanning()
            elif action == self.Command.SCAN:
                # Scan images
                path, subDirs = args
                logger.debug(f"Start a new scan handler")
                self._scanHandler = ScanHandler(path, subDirs, conn, self._downloadedDb)
                self._scanHandler.start()
            else:
                logger.warning(f"Unknown command {action} ignored")

    def _stopScanning(self):
        scanHandler = self._scanHandler
        if scanHandler and scanHandler.is_alive():
            path = scanHandler.path
            logger.info(f"Stopping {path} scan handler...")
            scanHandler.stop()
            scanHandler.join(timeout=0.5)
            if scanHandler.is_alive():
                logger.warning(f"Cannot join scan handler for {path}")
            else:
                logger.info(f"{path} scan handler stopped")
