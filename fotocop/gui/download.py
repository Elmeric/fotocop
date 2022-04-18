import math
from typing import TYPE_CHECKING

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

if TYPE_CHECKING:
    from fotocop.models.downloader import Downloader


class DownloadButton(QtWidgets.QPushButton):
    """Button used to initiate downloads.
    """

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)

        self.sessionRequired = False
        self.datetimeRequired = False

        self.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Maximum)

        fontHeight = QtGui.QFontMetrics(QtWidgets.QApplication.font()).height()
        padding = math.ceil(fontHeight * 1.25)
        height = fontHeight // 2 * 4
        radius = height // 2

        palette = QtGui.QGuiApplication.palette()
        primaryColor = palette.highlight().color()
        borderColor = primaryColor.darker(105)
        hoverColor = primaryColor.darker(106)
        hoverBorderColor = hoverColor.darker(105)
        primaryTextColor = palette.highlightedText().color()

        disabledColor = palette.window().color().darker(120)
        disabledBorderColor = disabledColor.darker(105)
        disabledTextColor = primaryTextColor

        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {primaryColor.name()};
                outline: none;
                padding-left: {padding:d}px;
                padding-right: {padding:d}px;
                border-radius: {radius:d}px;
                border: 1px solid {borderColor.name()};
                height: {height:d}px;
                color: {primaryTextColor.name()};
                font-weight: bold;
                font-size: {fontHeight:d}px
            }}
            QPushButton:hover {{
                background-color: {hoverColor.name()};
                border: 1px solid {hoverBorderColor.name()};
            }}
            QPushButton:disabled {{
                background-color: {disabledColor.name()};
                color: {disabledTextColor.name()};
                border: 1px solid {disabledBorderColor.name()};
            }}
            """
        )

    @QtCore.pyqtSlot(bool)
    def requestSession(self, sessionRequired: bool) -> None:
        self.sessionRequired = sessionRequired

    @QtCore.pyqtSlot(bool)
    def requestDatetime(self, datetimeRequired: bool) -> None:
        self.datetimeRequired = datetimeRequired


class DownloadProgress(QtWidgets.QProgressDialog):
    def __init__(self, downloader: "Downloader", parent) -> None:
        super().__init__(parent)

        self._downloader = downloader
        self._cancelled = False

        self.setLabelText("Downloading images...")
        self.cancelBtn = QtWidgets.QPushButton(" Stop download ")
        self.setCancelButton(self.cancelBtn)
        self.setMinimumDuration(0)
        self.setWindowTitle("Fotocop - Download images")
        self.setMinimumWidth(400)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setAutoReset(False)
        self.reset()
        self.canceled.connect(self.cancel)

    @QtCore.pyqtSlot(str, int)
    def reinit(self, msg: str, maxCount: int) -> None:
        self._cancelled = False
        self.cancelBtn.setEnabled(True)
        self.setLabelText(f"<b>{msg}</b>")
        self.setRange(0, maxCount)
        self.setValue(0)

    @QtCore.pyqtSlot(int)
    def updateProgress(self, progress: int) -> None:
        self.setValue(progress)

    @QtCore.pyqtSlot(str)
    def terminate(self, msg: str) -> None:
        self.setLabelText(f"<b>{msg}</b>")
        self.cancelBtn.setEnabled(False)
        QtCore.QTimer.singleShot(2000, self.reset)

    @QtCore.pyqtSlot()
    def cancel(self) -> None:
        if not self._cancelled:
            self._cancelled = True
            self.cancelBtn.setEnabled(False)
            self._downloader.cancelDownload()
        self.open()

    @QtCore.pyqtSlot(str)
    def onCancel(self, msg: str) -> None:
        self.setLabelText(f"<b>{msg}</b>")
        QtCore.QTimer.singleShot(3000, self.reset)
