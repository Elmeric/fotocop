import logging
import threading
import multiprocessing as mp
from typing import TYPE_CHECKING, Dict, List, Callable

if TYPE_CHECKING:
    from enum import Enum
    from multiprocessing.connection import Connection
    from fotocop.util.workerutil import Message

logger = logging.getLogger(__name__)


class Task:
    def __init__(self, command: "Enum", *args) -> None:
        self._command = command
        self._params = args

    def execute(self, receiver: "Connection") -> None:
        receiver.send((self._command, self._params))


class Notifier:
    _subscribers: Dict[str, List[Callable]]
    _conn: "Connection"

    def __init__(self, conn: "Connection", name: str) -> None:
        self._conn = conn
        self._alive = mp.Event()
        self._lock = threading.Lock()
        self._subscribers = dict()

        self._reader = threading.Thread(
            target=self._receiveThread,
            args=(conn,),
            name=f"{name}Listener"
        )
        self._reader.start()

    def stop(self, timeout: float = None) -> None:
        self._alive.clear()
        self._reader.join(timeout)

    def subscribe(self, topic: str, callback: Callable) -> None:
        if callback not in self._subscribers.get(topic, []):
            self._subscribers.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic: str, callback: Callable) -> None:
        if callback in self._subscribers.get(topic, []):
            self._subscribers[topic].remove(callback)

    def _receiveThread(self, conn: "Connection") -> None:
        self._alive.set()
        while self._alive.is_set():
            try:
                if self._conn.poll(timeout=0.01):
                    msg = self._conn.recv()
                    # msg: Message = self._conn.recv()
                    with self._lock:
                        self._notify(msg)

            except (OSError, EOFError, BrokenPipeError):
                self._alive.clear()

    def _notify(self, msg: "Message") -> None:
        for callback in self._subscribers.get(msg.topic, []):
            callback(*msg.data)
