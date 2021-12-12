from typing import Any

import PyQt5.QtCore as QtCore

__all__ = ["QtSignalAdapter"]


class QtSignalAdapter:
    def __init__(self, *argsType: Any, name: str = None):
        super().__init__()

        self.signalName = name

        self.argsType = argsType

    def __set_name__(self, owner, name):
        self.name = name

        if self.signalName is None:
            self.signalName = name

        QtSignal = type(
            "QtSignal",
            (QtCore.QObject,),
            {
                f"{self.name}": QtCore.pyqtSignal(*self.argsType, name=self.signalName),
            },
        )
        self.qtSignal = QtSignal()

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(self.qtSignal, self.name)
