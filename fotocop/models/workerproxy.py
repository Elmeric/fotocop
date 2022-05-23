import logging
import multiprocessing as mp

from fotocop.util.bgdtask import Task, Notifier
from fotocop.util.basicpatterns import ObjectFactory
from fotocop.models import imagescanner as scanner
from fotocop.models import exifloader as exifier
from fotocop.models import imagesmover as mover

logger = logging.getLogger(__name__)

workerFactory = ObjectFactory()

workerFactory.register_builder("ImageScanner", scanner.ImageScanner)
workerFactory.register_builder("ExifLoader", exifier.ExifLoader)
workerFactory.register_builder("ImageMover", mover.ImageMover)


class WorkerProxy:
    def __init__(self, name: str) -> None:
        self.name = name

        # Start the background process and establish a Pipe connection with it
        logger.info(f"Starting {name}...")
        workerConnection, child_conn1 = mp.Pipe()
        self._workerConnection = workerConnection
        self._worker = workerFactory.create(name, child_conn1)
        self._worker.start()
        child_conn1.close()

        # Start a thread listening to the background process messages
        self._msgNotifier = Notifier(workerConnection, name)

    def subscribe(self, *args, **kwargs):
        self._msgNotifier.subscribe(*args, **kwargs)

    def stop(self) -> None:
        # Stop and join the background process ant its listener thread
        logger.info(f"Request {self.name} to stop...")
        Task(self._worker.Command.STOP).execute(self._workerConnection)
        self._worker.join(timeout=0.25)
        if self._worker.is_alive():
            self._worker.terminate()
        self._workerConnection.close()
        self._msgNotifier.stop()


class ImageScanner(WorkerProxy):
    def scan(self, path: str, includeSubDirs: bool) -> None:
        Task(scanner.ImageScanner.Command.SCAN, path, includeSubDirs).execute(self._workerConnection)

    def abort(self) -> None:
        Task(scanner.ImageScanner.Command.ABORT).execute(self._workerConnection)


class ExifLoader(WorkerProxy):
    def loadAll(self, imageKey) -> None:
        Task(exifier.ExifLoader.Command.LOAD_ALL, imageKey).execute(self._workerConnection)

    def loadDatetime(self, imageKey) -> None:
        Task(exifier.ExifLoader.Command.LOAD_DATE, imageKey).execute(self._workerConnection)

    def loadThumbnail(self, imageKey) -> None:
        Task(exifier.ExifLoader.Command.LOAD_THUMB, imageKey).execute(self._workerConnection)


class ImageMover(WorkerProxy):
    def clearImages(self) -> None:
        Task(mover.ImageMover.Command.CLEAR_IMAGES).execute(self._workerConnection)

    def getFoldersPreview(self) -> None:
        Task(mover.ImageMover.Command.GET_FOLDERS_PREVIEW).execute(self._workerConnection)

    def getImageSamplePreview(self, image) -> None:
        Task(mover.ImageMover.Command.GET_IMG_PREVIEW, image).execute(self._workerConnection)

    def addImages(self, images) -> None:
        Task(mover.ImageMover.Command.ADD_IMAGES, images).execute(self._workerConnection)

    def updateImagesInfo(self, imageKeys, pty, value) -> None:
        Task(mover.ImageMover.Command.UPDATE_IMAGES_INFO, imageKeys, pty, value).execute(self._workerConnection)

    def setDestination(self, destination: str) -> None:
        Task(mover.ImageMover.Command.SET_DEST, destination).execute(self._workerConnection)

    def setImageTemplate(self, template) -> None:
        Task(mover.ImageMover.Command.SET_IMG_TPL, template).execute(self._workerConnection)

    def setDestinationTemplate(self, template) -> None:
        Task(mover.ImageMover.Command.SET_DEST_TPL, template).execute(self._workerConnection)

    def startDownload(self) -> None:
        Task(mover.ImageMover.Command.DOWNLOAD).execute(self._workerConnection)

    def cancelDownload(self) -> None:
        Task(mover.ImageMover.Command.CANCEL).execute(self._workerConnection)

    def saveSequences(self) -> None:
        Task(mover.ImageMover.Command.SAVE_SEQ).execute(self._workerConnection)
