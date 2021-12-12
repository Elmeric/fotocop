from typing import Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

__all__ = ["SplashScreen"]


def standardFontSize(shrinkOnOdd: bool = True) -> int:
    h = QtGui.QFontMetrics(QtGui.QFont()).height()
    if h % 2 == 1:
        if shrinkOnOdd:
            h -= 1
        else:
            h += 1
    return h


def scaledIcon(path: str, size: Optional[QtCore.QSize] = None) -> QtGui.QIcon:
    """Create a QIcon that scales well.

    Args:
        path: path to the icon file.
        size: target size for the icon.

    Returns:
        The scaled icon
    """
    i = QtGui.QIcon()
    if size is None:
        s = standardFontSize()
        size = QtCore.QSize(s, s)
    i.addFile(path, size)
    return i


class SplashScreen(QtWidgets.QSplashScreen):
    def __init__(self, iconPath: str, version: str, flags) -> None:
        # Use QIcon to render, so we get the high DPI version automatically
        size = QtCore.QSize(600, 400)
        pixmap = scaledIcon(iconPath, size).pixmap(size)
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
