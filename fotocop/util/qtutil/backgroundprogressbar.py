import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

__all__ = ["BackgroundProgressBar"]


class BackgroundProgressBar(QtWidgets.QWidget):

    progressValueChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.hidingTimer = QtCore.QTimer(parent=self)
        self.hidingTimer.setSingleShot(True)
        self.hidingTimer.timeout.connect(self.hide)

        self.msgLbl = QtWidgets.QLabel()
        self.msgLbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        f = QtGui.QFont()
        f.setBold(True)
        self.msgLbl.setFont(f)

        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setMaximumWidth(150)
        self.progressBar.setFixedHeight(15)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 2, 0, 2)
        layout.addWidget(self.msgLbl)
        layout.addWidget(self.progressBar)

        self.setLayout(layout)

        self._minProgressStep = 5

        self.__previousProgress = 0

    def setMinProgressStep(self, value: int):
        self._minProgressStep = int(value)

    def minProgressStep(self) -> int:
        return self._minProgressStep

    def show(self):
        self.progressBar.show()
        super().show()

    def showActionProgress(self, msg: str, maxValue: int = 100):
        if self.hidingTimer.isActive():
            self.hidingTimer.stop()
        self.msgLbl.setText(msg)
        self.progressBar.setRange(0, maxValue)
        self.__previousProgress = 0
        self.show()

    def hideActionProgress(self, msg: str):
        self.msgLbl.setText(msg + "  ")
        self.progressBar.hide()
        self.progressBar.reset()
        self.__previousProgress = 0
        self.hidingTimer.start(5000)    # hide widget after 5s

    def setActionProgressValue(self, value: int):
        minvalue = self.progressBar.minimum()
        maxvalue = self.progressBar.maximum()
        if minvalue == maxvalue:
            return
        progress = int(((value - minvalue) / (maxvalue - minvalue)) * 100)
        if progress - self.__previousProgress >= self._minProgressStep:
            self.__previousProgress = progress
            self.progressBar.setValue(value)
            self.progressValueChanged.emit(progress)
