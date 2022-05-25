import logging
import multiprocessing as mp
from dataclasses import dataclass
from typing import TYPE_CHECKING, Tuple, Callable, Dict

from fotocop.util.logutil import LogConfig, configureRootLogger

if TYPE_CHECKING:
    from multiprocessing.connection import Connection
    from enum import Enum

logger = logging.getLogger(__name__)

__all__ = ["BackgroundWorker"]


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

        self._actions: Dict["Enum", Callable] = dict()

    def registerAction(self, action: "Enum", func: Callable) -> None:
        if action not in self._actions:
            self._actions[action] = func

    def run(self) -> None:
        """ExifLoader 'main loop'
        """
        configureRootLogger(self.logQueue, self.logLevel)

        self._preRun()

        self._exitProcess.clear()

        logger.info(f"{self.name} started")
        while True:
            conn = self._conn
            if conn.poll():
                action, args = conn.recv()
                try:
                    self._actions[action](*args)
                except KeyError:
                    logger.warning(f"Unknown command {action} ignored")
            if self._exitProcess.wait(timeout=0.01):
                break

        self._conn.close()
        self._postRun()
        logger.info(f"{self.name} stopped")

    def publishData(self, content: str, *data) -> None:
        msg = Message(content, data)
        try:
            self._conn.send(msg)
            logger.debug(f"Data published: {msg}")
        except (OSError, EOFError, BrokenPipeError):
            pass

    def _preRun(self, *args, **kwargs) -> None:
        pass

    def _postRun(self, *args, **kwargs) -> None:
        pass

    def _stop(self):
        # Stop the 'main' loop
        logger.info(f"Stopping {self.name}...")
        self._exitProcess.set()
