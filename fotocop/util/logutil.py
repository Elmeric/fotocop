import logging
import logging.handlers
import multiprocessing as mp
import time
from queue import Empty
from pathlib import Path
from typing import Union

from fotocop.util.basicpatterns import Singleton


class _LogServer(mp.Process):
    def __init__(
            self,
            logQueue: mp.Queue,
            logFile: Path,
            logLevel: Union[int, str] = logging.INFO,
            logOnConsole: bool = True
    ):
        super().__init__()

        self.name = "LogServer"
        self.logQueue = logQueue
        self.logFile = logFile
        self.logLevel = logLevel
        self.logOnConsolde = logOnConsole

    def configure(self):
        logging_format = '%(processName)-15s%(levelname)s: %(message)s'
        logging_date_format = '%Y-%m-%d %H:%M:%S'
        # file_logging_format = '%(asctime)s.%(msecs)03d %(levelname)-8s %(processName)-15s %(name)s %(filename)s %(lineno)d: %(message)s'
        file_logging_format = '%(asctime)s.%(msecs)03d %(levelname)-8s %(processName)-15s %(message)s'

        root = logging.getLogger()
        filehandler = logging.FileHandler(self.logFile, mode='w')
        filehandler.setLevel(self.logLevel)
        filehandler.setFormatter(logging.Formatter(file_logging_format, logging_date_format))
        # filehandler.setFormatter(logging.Formatter(file_logging_format))
        root.addHandler(filehandler)

        if self.logOnConsolde:
            consolehandler = logging.StreamHandler()
            consolehandler.set_name('console')
            consolehandler.setFormatter(logging.Formatter(logging_format))
            consolehandler.setLevel(logging.INFO)
            root.addHandler(consolehandler)

        root.setLevel(logging.DEBUG)

    def run(self):
        self.configure()
        while True:
            try:
                try:
                    record = self.logQueue.get(block=True, timeout=0.01)
                except Empty:
                    continue
                if record is None:  # We send this as a sentinel to tell the listener to quit.
                    break
                logger = logging.getLogger(record.name)
                logger.handle(record)
            except Exception:
                import sys, traceback
                print('Whoops! Problem:', file=sys.stderr)
                traceback.print_exc(file=sys.stderr)


class LogConfig(metaclass=Singleton):
    def __init__(
            self,
            logFile: Path = None,
            logLevel: Union[int, str] = logging.INFO,
            logOnConsole: bool = True
    ):
        self.logFile = logFile or '.'
        self.logLevel = logLevel
        self.logOnConsole = logOnConsole

        logging.captureWarnings(True)

        self.logQueue = mp.Queue(maxsize=-1)
        self.logServer = _LogServer(
            self.logQueue,
            self.logFile,
            self.logLevel,
            self.logOnConsole,
        )

    def initLogging(self):
        self.logServer.start()
        configureRootLogger(self.logQueue, self.logLevel)

    def stopLogging(self):
        self.logQueue.put_nowait(None)
        self.logServer.join()


def configureRootLogger(logQueue: mp.Queue, logLevel: Union[int, str]):
    handler = logging.handlers.QueueHandler(logQueue)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logLevel)
