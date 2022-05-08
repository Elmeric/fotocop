import threading
import multiprocessing as mp
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from multiprocessing.connection import Connection

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


class ConnectionListener(threading.Thread):
    def __init__(self, conn: "Connection", name: str = None) -> None:
        super().__init__(name=name)
        # self.name = "ImageScannerListener"
        self._conn = conn
        self._alive = mp.Event()

    def run(self):
        self._alive.set()
        while self._alive.is_set():
            try:
                if self._conn.poll(timeout=0.01):
                    msg = self._conn.recv()
                    self.handleMessage(msg)

            except (OSError, EOFError, BrokenPipeError):
                self._alive.clear()

    def handleMessage(self, msg: Any) -> None:
        raise NotImplementedError

    def join(self, timeout=None):
        self._alive.clear()
        super().join(timeout)
