import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

__all__ = ["SessionEditor"]


class SessionEditor(QtWidgets.QDialog):
    """Very simple dialog window that allows user entry of a session name.
    """

    def __init__(self, imagesCount: int, parent=None) -> None:
        super().__init__(parent)

        self.setModal(True)

        title = "Enter Session - Fotocop"
        directive = "Enter a Session"
        details = (
            f"The Session will be applied to {imagesCount} images that does not yet "
            f"have a Session."
        )
        hint = (
            "<b>Hint:</b> To assign Sessions before the download begins, select "
            "images and apply a Session to them via the Thumbnails view's tool bar."
        )
        details = f"{details}<br><br><i>{hint}</i>"

        instructionLbl = QtWidgets.QLabel(f"<b>{directive}</b><br><br>{details}<br>")
        instructionLbl.setWordWrap(True)

        self.nameEdit = QtWidgets.QLineEdit()
        metrics = QtGui.QFontMetrics(QtGui.QFont())
        self.nameEdit.setMinimumWidth(metrics.width(title))
        # Accept space separated word of latin accented letter plus &',_-
        # First character shall be a latin capital letter or _
        # refer to https://www.ascii-code.com/ and https://regex101.com/library/g6gJyf
        validator = QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression(r"^[A-ZÀ-ÖØ-Þ_][0-9A-Za-zÀ-ÖØ-öø-ÿ &',_-]*$")
        )
        self.nameEdit.setValidator(validator)

        buttonBox = QtWidgets.QDialogButtonBox()
        buttonBox.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.saveButton = buttonBox.addButton(QtWidgets.QDialogButtonBox.Save)
        self.saveButton.setEnabled(False)

        flayout = QtWidgets.QFormLayout()
        flayout.addRow("Session:", self.nameEdit)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(instructionLbl)
        layout.addLayout(flayout)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

        self.nameEdit.textEdited.connect(self._nameEdited)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)

        self.setWindowTitle(title)

    @property
    def session(self) -> str:
        return self.nameEdit.text()

    @QtCore.pyqtSlot(str)
    def _nameEdited(self, name: str):
        self.saveButton.setEnabled(len(name) > 0)
