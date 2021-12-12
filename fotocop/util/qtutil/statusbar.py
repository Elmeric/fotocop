import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets

__all__ = ["StatusBar"]


class StatusBar(QtWidgets.QStatusBar):

    DEFAULT_COLOR = (0, 0, 0, 0)
    DEFAULT_MSG_STYLE = f"""
        QStatusBar{{
        border-top:2px solid darkgray;
        padding-left:8px;
        background:rgba{DEFAULT_COLOR};
        color:black;
        font-weight:bold;}}
    """
    WARNING_COLOR = (255, 153, 153, 255)
    WARNING_MSG_STYLE = f"""
        QStatusBar{{
        border-top :2px solid darkgray;
        padding-left:8px;
        background:rgba{WARNING_COLOR};
        color:black;
        font-weight:bold;}}
    """
    DEFAULT_MSG_DELAY = 2000  # 2 s
    WARNING_MSG_DELAY = 5000  # 5 s

    def __init__(self, parent: QtWidgets.QWidget = None):
        super().__init__(parent)

        self.setSizeGripEnabled(False)
        self.setStyleSheet(self.DEFAULT_MSG_STYLE)
        self.messageChanged.connect(self.onMessageStatusChanged)

    @QtCore.pyqtSlot(str)
    def onMessageStatusChanged(self, msg: str):
        """Reset the status bar to the default style.

        If there are no arguments (the message is being removed), change the
        status message bar to its default style.

        Args:
            msg: the new temporary status message. Empty string when the
                message has been removed.
        """
        if not msg:
            self.setStyleSheet(self.DEFAULT_MSG_STYLE)

    def displayMessage(self, msg: str, isWarning: bool = False, delay: int = None):
        """Convenient function to display a status message.

        Display a temporary message in the status bar with the right style.

        Args:
            msg: the message string to display.
            isWarning: True when the message is a warning
                (displayed in WARNING_MSG_STYLE for a longer default time).
            delay: the time to keep the message displayed
                (default is 5s for an information and 2s for a warning).

        """
        if isWarning:
            self.setStyleSheet(self.WARNING_MSG_STYLE)
        else:
            self.setStyleSheet(self.DEFAULT_MSG_STYLE)
        if not delay:
            delay = self.WARNING_MSG_DELAY if isWarning else self.DEFAULT_MSG_DELAY
        self.showMessage(msg, delay)
