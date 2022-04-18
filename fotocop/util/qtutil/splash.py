from typing import Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil

__all__ = ["SplashScreen"]


class SplashScreen(QtWidgets.QSplashScreen):
    def __init__(self, iconPath: str, version: str, flags) -> None:
        # Use QIcon to render, so we get the high DPI version automatically
        size = QtCore.QSize(600, 400)
        pixmap = QtUtil.scaledIcon(iconPath, size).pixmap(size)
        super().__init__(pixmap, flags)
        self._version = version
        self._progress = 0
        self._message = None
        try:
            self._imageWidth = pixmap.width() / pixmap.devicePixelRatioF()
        except AttributeError:
            self._imageWidth = pixmap.width() / pixmap.devicePixelRatio()

        self._progressBarPen = QtGui.QPen(
            QtGui.QBrush(QtGui.QColor(QtCore.Qt.green)), 5.0
        )

    def drawContents(self, painter: QtGui.QPainter):
        painter.save()
        painter.setPen(QtGui.QColor(QtCore.Qt.black))
        painter.drawText(12, 60, self._version)
        if self._progress:
            painter.setPen(self._progressBarPen)
            x = int(self._progress / 100 * self._imageWidth)
            painter.drawLine(0, 360, x, 360)
        if self._message:
            painter.setPen(QtGui.QColor(QtCore.Qt.black))
            painter.drawText(12, 385, self._message)
        painter.restore()

    def setProgress(self, value: int, msg: str = None) -> None:
        """Update the splash screen progress bar

        Args:
             value: percent done, between 0 and 100
             msg: optional message to display
        """
        self._progress = value
        self._message = msg
        self.repaint()
