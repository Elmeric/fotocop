import logging
import threading
import multiprocessing as mp
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

logger = logging.getLogger(__name__)

__all__ = ["StoppableThread", "ConnectionListener"]


class StoppableThread(threading.Thread):
    """Thread class with a stop() method.

    The thread itself has to check regularly for the stopped() condition.

    From https://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


# class ConnectionListener(threading.Thread):
#     def __init__(self, conn: "Connection", name: str = None) -> None:
#         super().__init__(name=name)
#         self._conn = conn
#         self._alive = mp.Event()
#
#     def run(self):
#         self._alive.set()
#         while self._alive.is_set():
#             try:
#                 if self._conn.poll(timeout=0.01):
#                     msg = self._conn.recv()
#                     self.handleMessage(msg)
#
#             except (OSError, EOFError, BrokenPipeError):
#                 self._alive.clear()
#
#     def handleMessage(self, msg: Any) -> None:
#         raise NotImplementedError
#
#     def join(self, timeout=None):
#         self._alive.clear()
#         super().join(timeout)


# class ImageScannerListener(ConnectionListener):
#     def __init__(self, conn):
#         super().__init__(conn, name="ImageScannerListener")
#
#     def handleMessage(self, msg: Any) -> None:
#         header, data = msg
#         content, batch = header.split("#")
#
#         if content == "images":
#
#             if batch == "ScanComplete":
#                 # All images received for current source
#                 SourceManager().scanComplete(*data)
#             else:
#                 # New images batch received for current source
#                 SourceManager().source.receiveImages(batch, data)
#
#         else:
#             logger.warning(f"Received unknown content: {content}")


# class ExifLoaderListener(ConnectionListener):
#     def __init__(self, conn):
#         super().__init__(conn, name="ExifLoaderListener")
#
#     def handleMessage(self, msg: Any) -> None:
#         content, data, imageKey = msg
#         sourceManager = SourceManager()
#
#         if content == "datetime":
#             sourceManager.source.receiveDatetime(imageKey, data)
#
#         elif content == "thumbnail":
#             sourceManager.source.receiveThumbnail(imageKey, data)
#
#         else:
#             logger.warning(f"Received unknown content: {content}")


# class ImageMoverListener(ConnectionListener):
#     def __init__(self, conn):
#         super().__init__(conn, name="ImageMoverListener")
#
#     def handleMessage(self, msg: Any) -> None:
#         content, *data = msg
#         downloader = Downloader()
#
#         if content == "image_preview":
#             sampleName, samplePath = data
#             logger.debug(
#                 f"Received image sample preview: {sampleName}, {samplePath}"
#             )
#             downloader.imageSampleChanged.emit(
#                 sampleName,
#                 Path(samplePath).as_posix()
#             )
#
#         elif content == "folder_preview":
#             previewFolders, *_ = data
#             logger.debug(
#                 f"Received folder preview: {previewFolders}"
#             )
#             downloader.folderPreviewChanged.emit(previewFolders)
#
#         elif content == "selected_images_count":
#             selectedImagesCount, *_ = data
#             logger.debug(
#                 f"{selectedImagesCount} images to download"
#             )
#             downloader.backgroundActionStarted.emit(
#                 f"Downloading {selectedImagesCount} images...", selectedImagesCount
#             )
#
#         elif content == "downloaded_images_count":
#             downloadedImagesCount, *_ = data
#             downloader.backgroundActionProgressChanged.emit(
#                 downloadedImagesCount
#             )
#
#         elif content == "download_completed":
#             downloadedImagesCount, downloadedImagesInfo = data
#             downloader.markImagesAsPreviouslyDownloaded(downloadedImagesInfo)
#             downloader.backgroundActionCompleted.emit(downloadedImagesCount)
#
#         elif content == "download_cancelled":
#             downloadedImagesCount, downloadedImagesInfo = data
#             downloader.markImagesAsPreviouslyDownloaded(downloadedImagesInfo)
#             downloader.backgroundActionCompleted.emit(downloadedImagesCount)
#
#         else:
#             logger.warning(f"Received unknown content: {content}")
