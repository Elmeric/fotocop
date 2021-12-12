from typing import Callable
from enum import Enum, auto
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from .fittedlineedit import FittedLineEdit

__all__ = ["PathSelector", "DirectorySelector", "FileSelector"]


class _PathType(Enum):
    DIR = auto()
    FILE = auto()


class PathSelector(QtWidgets.QWidget):
    # TODO: Add auto completion with a QtWidgets.QCompleter
    """A dialog to select file or directory path.

    The PathSelector is composed of:
        A QLabel: role of the path to select.
        A FittedLineEdit a QLineEdit that fit its content to enter a path.
        A QPushButton: to call a standard QFileDialog.
        A 'not found' QLabel: hidden except to warn for a non existing entered path.
    When its 'shallExist' attribute is set, the PathSelector ensures that an
    existing path is selected, either by text input or through a standard
    QFileDialog. Invalid text input are rejected (display of a not found
    label and text entry blinking).
    The selected path is emitted in a standard posix format.

    Args:
        label: title of the path selector.
        placeHolder: placeholder text as long as the line edit is empty.
        selectIcon: icon of the QPushButton that call the standard QFileDialog.
        tip: a tip text on the QPushButton and on the status bar.
        directoryGetter: a callable that return the base directory where to
            select the path.
        shallExist: the entered file or directory shall exist.
        defaultPath: if not empty, replaced an empty path entry.
        parent: the parent QWidget.
        *args, **kwargs: Any other positional and keyword argument are passed to
            the parent QWidget along with the parent argument.

    Class Attributes:
        pathSelected: this Qt Signal is emitted with the path entry as argument
            on dialog validation.
            On textual input, an empty path is emitted if nothing is entered.
            On QFileDialog selection, the signal is emiited only if the dialog
                is accepted.

    Attributes:
        tip (str): the QPushButtontip text, also used as the QFileDialog caption.
        directoryGetter: a callable that return the base directory where to
            select the path.
        shallExist (bool): the entered file or directory shall exist.
        defaultPath (str): if not empty, replaced an empty path entry.
        parent (QtMainView): parent window of the project view.
        _blinkingTimer (QtCore.QTimer): to support blinking on input error.
        _blinkingCount (int): blinking stop when 0 is reached (start at 4 by default).
        _blinkingPath (str): the current path input text to support blinking
            on input error.
        _previousPath (str): keep the previous path selector text to support
            blinking on input error.
        _pathLineEdit (FittedLineEdit): the path input text widget.
        _notFoundLabel (QtWidgets.QLabel): this label is shown on input error.
    """

    pathSelected = QtCore.pyqtSignal(str)

    def __init__(
            self,
            *args,
            label: str = 'Select path:',
            placeHolder: str = 'Enter a path',
            selectIcon: QtGui.QIcon = None,
            tip: str = 'Select a path',
            directoryGetter: Callable[[], str] = lambda: '',
            shallExist: bool = True,
            defaultPath: str = '',
            parent=None,
            **kwargs):
        self.tip = tip
        self.directoryGetter = directoryGetter
        self.shallExist = shallExist
        self.defaultPath = defaultPath
        self.parent = parent
        self._pathType = _PathType.DIR
        super().__init__(parent, *args, **kwargs)

        self._blinkingTimer = QtCore.QTimer(self)
        self._blinkingTimer.timeout.connect(self._blink)
        self._blinkingCount = 4
        self._blinkingPath = ''
        self._previousPath = ''

        label = QtWidgets.QLabel(label)
        self._pathLineEdit = FittedLineEdit()
        self._pathLineEdit.setPlaceholderText(placeHolder)
        self._pathLineEdit.editingFinished.connect(self.onPathInput)
        if selectIcon:
            self._pathSelectButton = QtWidgets.QPushButton(selectIcon, '')
            self._pathSelectButton.setMaximumWidth(30)
        else:
            self._pathSelectButton = QtWidgets.QPushButton('Select')
        self._pathSelectButton.setToolTip(tip)
        self._pathSelectButton.setStatusTip(tip)
        self._pathSelectButton.clicked.connect(self.openPathSelector)
        self._notFoundLabel = QtWidgets.QLabel(' Not found ! ')
        self._notFoundLabel.setStyleSheet(
            f'QLabel{{color:rgba{255, 25, 25, 255};}}'
        )
        self._notFoundLabel.hide()

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(label)
        layout.addWidget(self._pathLineEdit)
        layout.addWidget(self._notFoundLabel)
        layout.addWidget(self._pathSelectButton)
        layout.addStretch()
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    @QtCore.pyqtSlot()
    def onPathInput(self):
        """Handle text input in the path selector QLineEdit on focus loss.

        Empty entry with no defaultPath set is emitted as it.
        If the entered path does not exist, the entry is rejected with a
        Not found label error and blinking of the input area.
        Otherwise, the entered path is emitted, in standard posix format.
        """
        # Qt5 bug work around (editingFinished emitted twice).
        # Refer to https://bugreports.qt.io/browse/QTBUG-40
        obj = self.sender()
        if not obj.isModified():                                        # noqa
            # Ignore second signal
            return
        obj.setModified(False)                                          # noqa

        enteredPath = self._pathLineEdit.text()

        if not enteredPath and self.defaultPath:
            # Replace an empty selection by the default path if defined.
            enteredPath = self.defaultPath
            self._pathLineEdit.setText(enteredPath)

        if not enteredPath:
            # Empty selection is emitted as it when no default path is set.
            self.pathSelected.emit(enteredPath)
            return

        path = Path(enteredPath)

        if self.shallExist:
            # path is make absolute, relatively to the base directory returned by
            # by the directoryGetter callback to check its existence.
            if not path.is_absolute():
                absolutePath = self.directoryGetter() / path
            else:
                absolutePath = path
            if (
                    (
                            self._pathType is _PathType.DIR
                            and Path(absolutePath).is_dir()
                    )
                    or
                    (
                            self._pathType is _PathType.FILE
                            and Path(absolutePath).is_file()
                    )
                ):                                                      # noqa
                # Stop blinking and emit the entered path in posix standard
                self._blinkingTimer.stop()
                self._notFoundLabel.hide()
                self._blinkingPath = ''
                self._blinkingCount = 4
                self.pathSelected.emit(path.as_posix())
            else:
                # Show error label and start blinking
                self._notFoundLabel.show()
                self._blinkingPath = enteredPath
                self._blinkingCount = 4
                self._blinkingTimer.start(200)
        else:
            # Emit the entered path in posix standard with no existence check.
            self.pathSelected.emit(path.as_posix())

    @QtCore.pyqtSlot()
    def openPathSelector(self):
        """Open a standard QFileDialog and emit the selected path.

        If dialog is rejected (Cancel button), nothing is emitted.
        """
        path = QtWidgets.QFileDialog.getExistingDirectory(
            parent=self,
            caption=self.tip,
            directory=self.directoryGetter()
        )
        if path:
            self.pathSelected.emit(Path(path).as_posix())

    def _blink(self):
        """Convenient method to manage blinking of the path selector QLineEdit.

        Called by the _blinkingTimer timeout signal.
        """
        if self._blinkingCount > 0:
            if self._pathLineEdit.text() == self._blinkingPath:
                self._pathLineEdit.setText(self._previousPath)
            else:
                self._pathLineEdit.setText(self._blinkingPath)
            self._blinkingCount -= 1
        else:
            self._pathLineEdit.setText(self._previousPath)
            self._notFoundLabel.hide()
            self._blinkingPath = ''
            self._blinkingCount = 4
            self._blinkingTimer.stop()
            self._pathLineEdit.updateGeometry()

    def clear(self):
        """Clear the path selector text.

        Update the widget geometry to fit its new text content.
        """
        self._previousPath = ''
        self._pathLineEdit.clear()
        self._pathLineEdit.updateGeometry()

    def setText(self, text: str):
        """Update the path selector text.

        Keep the text to
        Update the widget geometry to fit its new text content.

        Args:
            text: the text to display
        """
        self._previousPath = text
        self._pathLineEdit.setText(text)
        self._pathLineEdit.updateGeometry()

    def text(self) -> str:
        """Retuns the path selector text.

        Returns:
            The path selector text.
        """
        return self._pathLineEdit.text()

    def setFocus(self):
        """Give focus to the select button of the path selector."""
        self._pathSelectButton.setFocus()

    def rejectPath(self, rejectedPath: str):
        """Reset the path selector text when rejected by the associated model.

        Update the widget geometry to fit its new text content.

        Args:
            rejectedPath: the rejected path value to restore.
        """
        self._previousPath = rejectedPath
        self._pathLineEdit.setText(rejectedPath)
        self._pathLineEdit.setFocus()
        self._pathLineEdit.updateGeometry()


class DirectorySelector(PathSelector):
    """Specialization of the PathSelector with dedicated defaults label and tips.
    """
    def __init__(
            self,
            *args,
            label: str = 'Select directory:',
            placeHolder: str = 'Enter a directory path',
            tip: str = 'Select a directory path',
            **kwargs):
        super().__init__(
            *args,
            label=label,
            placeHolder=placeHolder,
            tip=tip,
            **kwargs)
        self._pathType = _PathType.DIR


class FileSelector(PathSelector):
    # TODO: check against the filter in the overridden onPathInput slot
    """Specialization of the PathSelector to select a file path.

    Add also dedicated default label and tips and a filter args to specify the file
    suffix that can be selected.

    Args:
        filter: specify the file suffix that is showed in the selection dialog.
        *args, **kwargs: Any other positional and keyword argument are passed to
            the parent QWidget along with the parent argument.
    """
    def __init__(
            self,
            *args,
            label: str = 'Select file:',
            placeHolder: str = 'Enter a file path',
            tip: str = 'Select a file path',
            filter: str = None,                                     # noqa
            **kwargs):
        self.filter = filter
        super().__init__(
            *args,
            label=label,
            placeHolder=placeHolder,
            tip=tip,
            **kwargs)
        self._pathType = _PathType.FILE

    @QtCore.pyqtSlot()
    def openPathSelector(self):
        """Open a standard QFileDialog and emit the selected path.

        If dialog is rejected (Cancel button), nothing is emitted.
        """
        if self.shallExist:
            dialog = QtWidgets.QFileDialog.getOpenFileName
        else:
            dialog = QtWidgets.QFileDialog.getSaveFileName
        path = dialog(
            parent=self,
            caption=self.tip,
            directory=self.directoryGetter(),
            filter=self.filter,
            options=QtWidgets.QFileDialog.DontConfirmOverwrite
        )[0]                                                        # noqa
        if path:
            self.pathSelected.emit(Path(path).as_posix())
