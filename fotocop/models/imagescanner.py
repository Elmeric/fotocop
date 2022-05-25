import logging
from typing import Optional
from pathlib import Path
from enum import Enum, auto

from fotocop.util.threadutil import StoppableThread
from fotocop.util.workerutil import BackgroundWorker
from fotocop.models.sqlpersistence import DownloadedDB, FileDownloaded

logger = logging.getLogger(__name__)


class ScanHandler(StoppableThread):
    def __init__(self, path: str, subDirs: bool, worker: "ImageScanner", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "StoppableScanHandler"
        self._path = path
        self._subDirs = subDirs
        self._worker = worker

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
                        self._worker.publishData("images", batchesCount, imagesBatch)
                        imagesBatch = list()
        except OSError as e:
            logger.error(f"Cannot scan images in {self.path}: {e}")
        finally:
            if imagesBatch:
                batchesCount += 1
                logger.debug(f"Sending remaining images: batch#{batchesCount}")
                self._worker.publishData("images", batchesCount, imagesBatch)
            if not stopped:
                logger.info(f"{imagesCount} images found and sent in {batchesCount} batches")
            self._worker.publishData("ScanComplete", imagesCount, stopped)

    @staticmethod
    def _isImage(path: Path) -> bool:
        return path.suffix.lower() in (".jpg", ".raf", ".nef", ".dng")

    def _isAlreadyDownloaded(self, imagePath: Path) -> Optional[FileDownloaded]:
        name = imagePath.name
        stat = imagePath.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        return self._worker.downloadedDb.fileIsPreviouslyDownloaded(name, size, mtime)


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

        self.registerAction(self.Command.SCAN, self._scanImages)
        self.registerAction(self.Command.ABORT, self._stopScanning)
        self.registerAction(self.Command.STOP, self._stop)

        self._scanHandler = None

        self.downloadedDb = DownloadedDB()

    def _scanImages(self, path: str, subDirs: bool) -> None:
        # Scan images
        logger.debug(f"Start a new scan handler")
        self._scanHandler = ScanHandler(path, subDirs, self)
        self._scanHandler.start()

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

    def _stop(self):
        self._stopScanning()
        super()._stop()
