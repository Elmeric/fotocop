import logging
import multiprocessing as mp
from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple

from fotocop.util.logutil import LogConfig, configureRootLogger

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

logger = logging.getLogger(__name__)

__all__ = ["Message", "BackgroundWorker"]


@dataclass
class Message:
    topic: str
    data: Tuple = tuple()


class BackgroundWorker(mp.Process):
    def __init__(self, conn: "Connection", name: str = None) -> None:
        super().__init__(name=name)

        logConfig = LogConfig()
        self.logQueue = logConfig.logQueue
        self.logLevel = logConfig.logLevel

        self._conn = conn
        self._exitProcess = mp.Event()

    def run(self) -> None:
        """ExifLoader 'main loop'
        """
        configureRootLogger(self.logQueue, self.logLevel)

        self._preRun()

        self._exitProcess.clear()

        logger.info(f"{self.name} started")
        while True:
            self._handleCommand()
            if self._exitProcess.wait(timeout=0.01):
                break

        self._conn.close()
        self._postRun()
        logger.info(f"{self.name} stopped")

    def _preRun(self, *args, **kwargs) -> None:
        pass

    def _postRun(self, *args, **kwargs) -> None:
        pass

    def _handleCommand(self, *args, **kwargs) -> None:
        pass
