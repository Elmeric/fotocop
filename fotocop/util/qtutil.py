"""A set of useful Qt5 utilities.

It provides:
    - a tool to layout two widgets horizontally or vertically.
    - a tool to create a QAction.
    - a tool to move a dialog at a given position, ensurint it remains visible.
      in the main window boundaries.
    - a tool to set the background color of a dialog.
    - a tool to retrieve the application main window.
    - A DcfsStyle class to override some default settings of the application
      style.
    - A list of checkable items with 'check all' and 'check none' buttons.
    - A QLineEdit that fit its content while minimizing its size.
    - A dialog to select file or directory path.
    - A dialog to rename any domain object.
    - A plain text editor with auto-completion.
    - A standard QStyledItemDelegate that hides focus decoration.
    - A QSyntaxHighlighter that highlight all occurrences of a string pattern.
    - A stack of toolbars where only one toolbar is visible at a time.
    - A basic textual filter input widget.
"""
from typing import Dict, Callable, Optional, Union, List, Any, Tuple
from enum import Enum, auto
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import Counter


import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import datatypes as dt


def autoLayoutWithLabel(
        label: QtWidgets.QWidget,
        widget: QtWidgets.QWidget,
        orientation: Optional[str] = 'V') -> QtWidgets.QLayout:
    """Layout two widgets horizontally or vertically (default).

    Current usage: the first widget is a QLabel that titles the second.

    Args:
        label: the 'widget' title (generally a QLabel).
        widget: any QWidget to be labelled by the 'label'.
        orientation: 'label' and 'widget' are layout vertically id equal to 'V'
            (the default), horizontally otherwise.

    Returns:
        the created QVBoxLayout or QHBoxLayout.
    """
    layout = QtWidgets.QVBoxLayout() if orientation == 'V' else QtWidgets.QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setAlignment(QtCore.Qt.AlignLeft)
    layout.addWidget(label)
    layout.addWidget(widget)
    layout.addStretch()
    return layout


def createAction(
        parent: QtCore.QObject,
        text: str,
        name: Optional[str] = None,
        slot: Optional[Callable] = None,
        shortcut: Optional[Union[str, QtGui.QKeySequence.StandardKey]] = None,
        icon: Optional[Union[str, QtGui.QIcon]] = None,
        tip: Optional[str] = None,
        checkable: Optional[bool] = False,
        signal: Optional[str] = "triggered") -> QtWidgets.QAction:
    """A convenient function to create a QAction.

    Args:
        parent: parent object of the QAction to be created (mandatory).
        text: text of the QaAction (mandatory).
        name: optional objectName of the QAction.
        slot: optional slot to connect on the QAction signal.
        shortcut:optional shortcut of the QAction.
        icon: optional icon of the QAction (maybe a file name or a QIcon).
        tip: optional tool tip ans status tip of the QAction.
        checkable: make the QAction checkable if True (False by default).
        signal: the QAction signal to be cnnected with 'slot' ('triggered' by
            default).

    Returns:
        The created QAction
    """
    action = QtWidgets.QAction(text, parent)
    if name is not None:
        action.setObjectName(name)
    if icon is not None:
        action.setIcon(QtGui.QIcon(icon))
    if shortcut is not None:
        action.setShortcut(shortcut)
    if tip is not None:
        action.setToolTip(tip)
        action.setStatusTip(tip)
    if slot is not None:
        getattr(action, signal).connect(slot)
    if checkable:
        action.setCheckable(True)
    return action


def movetAtPos(
        form: QtWidgets.QDialog,
        pos: QtCore.QPoint,
        parent: Optional[QtWidgets.QWidget] = None):
    """A convenient function to move a dialog at a given position.

    It ensures that the dialog remains in the parent boundaries.

    Args:
        form: the dialog to be be moved.
        pos: the position to be set as the form upper left corner.
        parent: optional parent widget (the application main window if not set).
    """
    if not parent:
        parent = getMainWindow()
    # Ensure the form is correctly resized before to set its position.
    form.adjustSize()
    dw = form.width()
    dh = form.height()
    pw = parent.frameGeometry().width()
    ph = parent.frameGeometry().height()
    px = parent.frameGeometry().x() + min(pos.x(), max(0, pw - dw))
    py = parent.frameGeometry().y() + min(pos.y(), max(0, ph - dh))
    form.move(px, py)


def setDialogBackgroundColor(dialog: QtWidgets.QDialog, color: str):
    """A convenient function to set the background color of a dialog.

    Args:
        dialog: the dialog to be colored.
        color: the color to apply to the dialog background.
    """
    p = dialog.palette()
    p.setColor(QtGui.QPalette.Window, QtGui.QColor(color))
    dialog.setAutoFillBackground(True)
    dialog.setPalette(p)


def getMainWindow() -> QtWidgets.QMainWindow:
    """A convenient function to retrieve the application main window.

    The application main window is defined as the first QMainWindow object
    retrieved from its top level widgets.

    Returns:
        The application main window.

    Raises:
        ValueError if no QMainWindow object exists in the application top level
            widgets list.
    """
    widgets = QtWidgets.qApp.topLevelWidgets()
    for w in widgets:
        if isinstance(w, QtWidgets.QMainWindow):
            return w
    raise ValueError('No Main Window found!')


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


class MyAppStyle(QtWidgets.QProxyStyle):
    """A QProxyStyle specialization to adjust some default style settings.

    Increase the default small icon size with 4 pixels.
    Adjust the the size of the view item decoration (apply to QTreeView and
    QTableView).
    """
    def pixelMetric(self, metric, option=None, widget=None) -> int:
        size = super().pixelMetric(metric, option, widget)
        if metric == QtWidgets.QStyle.PM_SmallIconSize:
            size = size + 4
        return size

    def subElementRect(self, element, option, widget) -> QtCore.QRect:
        rect = super().subElementRect(element, option, widget)
        if element == QtWidgets.QStyle.SE_ItemViewItemDecoration:
            dh = (rect.height() - 16) / 2
            if dh >= 0:
                rect.setRect(rect.x(), rect.y() + dh, rect.width(), 16)
        return rect


class CheckListWidget(QtWidgets.QWidget):
    """A list of checkable items with 'check all' / 'check none' buttons.

    Args:
        checkList: an optional mapping of checkable items to displayed. Each
            item is the string key and its checked / unchecked state is defined
            by the boolean value.
        label: an optional title for the check list.
        parent: an optional parent for the check list.
        *args, **kwargs: Any other positional and keyword argument are passed to
            the parent QWidget.

    Class attributes:
        stateChanged: A Qt signal emitted when the set of checked items changed.

    Attributes:
        listWidget: the list of checkable items.
        selectButton: the 'check all' button.
        unselectButton: the 'check none' button.
    """

    stateChanged = QtCore.pyqtSignal()

    def __init__(
            self,
            checkList: Dict[str, bool] = None,
            label: str = '',
            parent=None,
            *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.listWidget = QtWidgets.QListWidget()
        self.listWidget.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Minimum
        )
        self.listWidget.itemChanged.connect(
            lambda _item: self.stateChanged.emit()
        )

        if checkList:
            self.setCheckList(checkList)

        self.selectButton = QtWidgets.QPushButton('Select All')
        self.unselectButton = QtWidgets.QPushButton('Unselect All')
        self.selectButton.clicked.connect(self.select)
        self.unselectButton.clicked.connect(self.unselect)

        leftLayout = QtWidgets.QVBoxLayout()
        leftLayout.addWidget(QtWidgets.QLabel(label))
        leftLayout.addWidget(self.listWidget)
        rightLayout = QtWidgets.QVBoxLayout()
        rightLayout.addWidget(self.selectButton)
        rightLayout.addWidget(self.unselectButton)
        layout = QtWidgets.QHBoxLayout()
        layout.addLayout(leftLayout)
        layout.addLayout(rightLayout)
        layout.addStretch()
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    def setCheckList(self, checkList: Dict[str, bool]):
        """Set the check list state as defined by its mapping argument.

        Args:
            checkList: a mapping defining the items of the check list and their
            checked / unchecked state.
        """
        self.blockSignals(True)     # Avoid infinite recursion.
        self.clear()
        for string, checked in checkList.items():
            item = QtWidgets.QListWidgetItem(string, self.listWidget)
            check = (QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
            item.setCheckState(check)
        self.blockSignals(False)

    def getCheckList(self) -> Dict[str, bool]:
        """get the current state of the check list.

        Returns:
            A mapping of items in the check list with their checked / unckecked
                state.
        """
        checkList = dict()
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            checkList[item.text()] = True if item.checkState() == QtCore.Qt.Checked else False
        return checkList

    def clear(self):
        """Removes all items in the check list."""
        self.listWidget.clear()

    @QtCore.pyqtSlot()
    def select(self):
        """Select all items in the checked list."""
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            item.setCheckState(QtCore.Qt.Checked)
        self.stateChanged.emit()

    @QtCore.pyqtSlot()
    def unselect(self):
        """Deselect all items in the checked list."""
        for i in range(self.listWidget.count()):
            item = self.listWidget.item(i)
            item.setCheckState(QtCore.Qt.Unchecked)
        self.stateChanged.emit()


class FittedLineEdit(QtWidgets.QLineEdit):
    """A QLineEdit that fit its content while minimizing its size.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum,
            QtWidgets.QSizePolicy.Minimum
        )

    def sizeHint(self) -> QtCore.QSize:
        """Override the parent sizeHint getter to fit its text content.

        Returns:
            A width size hint corresponding to the text content and font.
            A minimum 100 size is set to ensure readibility as well as an extra
            15 pixels.

        """
        size = QtCore.QSize()
        fm = self.fontMetrics()
        width = fm.boundingRect(self.text()).width() + 15
        size.setWidth(max(100, width))
        return size

    def resizeEvent(self, event: QtGui.QResizeEvent):
        """Override the parent resizeEvent handler to udpate the widget geometry.

        Args:
            event: the widget resize event.
        """
        self.updateGeometry()
        super().resizeEvent(event)


class ClickableLineEdit(QtWidgets.QLineEdit):
    clicked = QtCore.pyqtSignal() # signal when the text entry is left clicked

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
        else:
            super().mousePressEvent(event)


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


class RenameDialog(QtWidgets.QDialog):
    """A dialog to rename any domain object.

    Args:
        name: the object name to change.
        pattern: a regular expression to validate the object name.
        parent: an optional parent for the dialog.

    Attributes:
        nameLineEdit: the object name editor.
        buttonBox: the 'OK' / 'CANCEL' buttons'.

    Properties:
        newName: the new object name.
        isValid: True if a valid new name is entered.
    """
    def __init__(self,
                 name: str,
                 pattern: str,
                 parent=None):
        super().__init__(parent)

        # Prevent resizing the view (its size is handle by the window content).
        self.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.MSWindowsFixedSizeDialogHint |
            QtCore.Qt.FramelessWindowHint
        )

        setDialogBackgroundColor(self, dt.BACKGROUND_COLOR)

        self.nameLineEdit = QtWidgets.QLineEdit()
        rx = QtCore.QRegularExpression(pattern)
        validator = QtGui.QRegularExpressionValidator(rx)
        self.nameLineEdit.setValidator(validator)
        self.nameLineEdit.textEdited.connect(self.checkName)

        self.buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self
        )
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        editGridLayout = QtWidgets.QGridLayout()
        editGridLayout.addWidget(self.nameLineEdit, 0, 1)
        editGridLayout.addWidget(self.buttonBox, 1, 1)

        self.setLayout(editGridLayout)

        self.nameLineEdit.setText(name)
        self.nameLineEdit.setFocus()

    @property
    def newName(self) -> str:
        return self.nameLineEdit.text()

    @property
    def isValid(self) -> bool:
        return self.nameLineEdit.text() != ''

    @QtCore.pyqtSlot(str)
    def checkName(self, text: str):
        """Ensure a upper case name is entered.

        Args:
            text: the current entered name.
        """
        pos = self.nameLineEdit.cursorPosition()
        self.nameLineEdit.setText(text.upper())
        self.nameLineEdit.setCursorPosition(pos)
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(self.isValid)


class AutoCompleteTextEdit(QtWidgets.QPlainTextEdit):
    """A plain text editor with auto-completion.

    From https://doc.qt.io/qt-5/qtwidgets-tools-customcompleter-example.html.
    Available completion words are displayed in a popup window.
    The completion popup is called by CTRL-SPACE or when the first 3
    characters of a completion word are entered.
    Auto-completion is not case-sensitive.

    Args:
        parent: an optional parent for the editor.

    Properties (in Qt5 properties style):
        completer: a QCompleter for text auto-completion.
        validator: A QRegularExpressionValidator for text validation.
    """
    def __init__(self, parent=None):
        self._completer = None
        self._validator = None
        super().__init__(parent)

    def setCompleter(self, completer: QtWidgets.QCompleter):
        """The completer property setter.

        If a completer exists, it's activated signal is disconnected before it
        is replaced by the new one.
        Passing a None completer suppress auto-completion.

        Args:
            completer: a QCompleter for text auto-completion.
        """
        if self._completer:
            self._completer.activated.disconnect(self)                  # noqa

        self._completer = completer

        if not self._completer:
            return

        self._completer.setWidget(self)
        self._completer.setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        self._completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self._completer.activated.connect(self.insertCompletion)        # noqa

    def completer(self) -> Optional[QtWidgets.QCompleter]:
        """Getter for the completer property.

        Returns:
            the current completer, None is no completer is set.
        """
        return self._completer

    @QtCore.pyqtSlot(str)
    def insertCompletion(self, completion: str):
        """Insert the selected completion in the text editor document.

        Only the extra characters of the selected completion word are inserted
        to complete the already entered ones, as retrieved by the
        completionPrefix getter.

        Args:
            completion: the selected completion word in the completion popup.
        """
        if self._completer.widget() != self:
            return

        tc = self.textCursor()
        extra = len(completion) - len(self._completer.completionPrefix())
        tc.movePosition(QtGui.QTextCursor.Left)
        tc.movePosition(QtGui.QTextCursor.EndOfWord)
        tc.insertText(completion[-extra:])

    def _textUnderCursor(self) -> str:
        """A convenient function to retrieve the word under the cursor."""
        tc = self.textCursor()
        tc.select(QtGui.QTextCursor.WordUnderCursor)
        return tc.selectedText()

    def focusInEvent(self, e: QtGui.QFocusEvent):
        """Re-implementation of Focus event handler (focus received).

        Ensure that the completer is correcltly associated to the text editor
        when it reveives the keyboard focus.
        The base class handler is then called with the passed event.

        Args:
            e: the focus event.
        """
        if self._completer:
            self._completer.setWidget(self)

        super(AutoCompleteTextEdit, self).focusInEvent(e)

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        """Trap the CTRL-SPACE key to prompt the completion list menu.

        Args:
            e: the key event.
        """
        # The following keys are forwarded by the completer to the widget.
        if self._completer and self._completer.popup().isVisible():
            if e.key() in (QtCore.Qt.Key_Enter,
                           QtCore.Qt.Key_Return,
                           QtCore.Qt.Key_Escape,
                           QtCore.Qt.Key_Tab,
                           QtCore.Qt.Key_Backtab):
                # Let the completer do default behavior.
                e.ignore()
                return

        # True if the CTRL-SPACE prompt is pressed.
        isShortcut = (e.modifiers() & QtCore.Qt.ControlModifier         # noqa
                      and e.key() == QtCore.Qt.Key_Space)
        # Do not process the shortcut when we have a completer.
        if not self._completer or not isShortcut:
            super(AutoCompleteTextEdit, self).keyPressEvent(e)

        # CTRL or SHIFT keys without SPACE are not trapped.
        ctrlOrShift = (e.modifiers() & QtCore.Qt.ControlModifier        # noqa
                       or e.modifiers() & QtCore.Qt.ShiftModifier)      # noqa
        if not self._completer or (ctrlOrShift and e.text() == ''):
            return

        eow = "~!@#$%^&*()_+{}|:\"<>?,./;'[]\\-="   # End of Word
        hasModifier = e.modifiers() != QtCore.Qt.NoModifier and not ctrlOrShift
        completionPrefix = self._textUnderCursor()

        if (
                not isShortcut
                and (
                        hasModifier
                        or e.text() == ''
                        or len(completionPrefix) < 3
                        or e.text()[-1:] in eow
                )):
            self._completer.popup().hide()
            return

        if completionPrefix != self._completer.completionPrefix():
            self._completer.setCompletionPrefix(completionPrefix)
            self._completer.popup().setCurrentIndex(
                self._completer.completionModel().index(0, 0)
            )

        # Popup the completer.
        cr = self.cursorRect()
        cr.setWidth(self._completer.popup().sizeHintForColumn(0)
                    + self._completer.popup().verticalScrollBar().sizeHint().width())
        self._completer.complete(cr)

    def validator(self) -> Optional[QtCore.QRegularExpression]:
        """Getter for the validator property.

        Returns:
            the current validator regular expression, None is no validator is set.
        """
        if self._validator:
            return self._validator.regularExpression()

    def setValidator(self, regexp: QtCore.QRegularExpression):
        """The validator property setter.

        Args:
            regexp: a QRegularExpression for text validation.
        """
        self._validator = QtGui.QRegularExpressionValidator(regexp)

    def isValid(self) -> bool:
        """Check the text editor content validity.

        Valid if not blank and acceptable by the validator if any.

        Returns:
            True if the entered text is valid.
        """
        text = self.toPlainText().strip()
        state = QtGui.QValidator.Acceptable
        if self._validator:
            state, _, _ = self._validator.validate(text, 0)
        return text != '' and state == QtGui.QValidator.Acceptable

    def setHeight(self, nRows: int):
        """Set the height of the text editor to a fixed rows count.

        Args:
            nRows: the visible rows count.
        """
        doc = self.document()
        fm = QtGui.QFontMetrics(doc.defaultFont())
        margins = self.contentsMargins()
        height = (
                fm.lineSpacing() * nRows
                + (doc.documentMargin() + self.frameWidth()) * 2
                + margins.top()
                + margins.bottom()
        )
        self.setFixedHeight(height)

    def setPlainText(self, text: str):
        """Set the text editor text and keep its char format.

        Re-implement the base class method as it loses the current char format.

        Args:
            text: the string to display in the text editor
        """
        fmt = self.currentCharFormat()
        super().setPlainText(text)
        # fmt.setFontCapitalization(QtGui.QFont.AllUppercase)
        self.setCurrentCharFormat(fmt)

    def forceUpperCase(self):
        """Force the text editor content to upper case."""
        with QtCore.QSignalBlocker(self.document()):
            cursor = self.textCursor()
            self.selectAll()
            fmt = self.currentCharFormat()
            fmt.setFontCapitalization(QtGui.QFont.AllUppercase)
            self.setCurrentCharFormat(fmt)
            cursor.clearSelection()
            self.setTextCursor(cursor)


class NoFocusDelegate(QtWidgets.QStyledItemDelegate):
    """A standard QStyledItemDelegate that hides focus decoration.

    From https://stackoverflow.com/questions/9795791/removing-dotted-border-without-setting-nofocus-in-windows-pyqt.

    Args:
        parent: an optional parent for the delegate.
    """
    def __init__(self, parent):
        super().__init__(parent)

    def paint(self, QPainter, QStyleOptionViewItem, QModelIndex):
        if QStyleOptionViewItem.state & QtWidgets.QStyle.State_HasFocus:
            QStyleOptionViewItem.state = \
                QStyleOptionViewItem.state ^ QtWidgets.QStyle.State_HasFocus
        super().paint(QPainter, QStyleOptionViewItem, QModelIndex)


class PatternHighlighter(QtGui.QSyntaxHighlighter):
    """A QSyntaxHighlighter that highlight all occurrences of a string pattern.

    From https://doc.qt.io/qt-5/qtwidgets-richtext-syntaxhighlighter-example.html.

    Args:
        pattern: the regular expression defining the highlight pattern.
        parent: an optional parent for the delegate.

    Attributes:
        keywordsFormat: a bold / darkMagenta QTextCharFormat to highlight
            matching text

    Properties (in Qt5 properties style):
        pattern: a QRegularExpression for text highlighting.
    """
    def __init__(self, pattern: QtCore.QRegularExpression, parent):
        super().__init__(parent)
        self._pattern = pattern
        self.keywordsFormat = QtGui.QTextCharFormat()
        self.keywordsFormat.setFontWeight(QtGui.QFont.Bold)
        self.keywordsFormat.setForeground(QtCore.Qt.darkMagenta)

    def pattern(self) -> QtCore.QRegularExpression:
        """Getter for the pattern property.

        Returns:
            the current pattern regular expression.
        """
        return self._pattern

    def setPattern(self, pattern: QtCore.QRegularExpression):
        """The pattern property setter.

        Args:
            pattern: a QRegularExpression for text highlighting.
        """
        self._pattern = pattern

    def highlightBlock(self, text):
        """Highlight all text blocks that match the pattern.

        The highlightBlock() method is called automatically whenever it is
        necessary by the rich text engine, i.e. when there are text blocks that
        have changed.

        Args:
            text: the string where to find pattern to highlight.
        """
        i = self._pattern.globalMatch(text)
        while i.hasNext():
            match = i.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.keywordsFormat)


class DcfsMimeData(QtCore.QMimeData):
    """A QMimeData specialization for DCFS Adapters and Flows.

    DcfsMimeData format is 'application/x-dcfsadapter' for adapters and
    'application/x-dcfsflow' for flows.
    A DcfsMimeData holds no data for itself (it cannot be used across
    applications). Its data are held by the _dcfsData private attribute.
    Its _dcfsDataKind private attribute indicates what kind of adapter or flow
    is held.
    DcfsMimeData provides convenience functions to access the data with the
    same interface style has the base QMimeData class: has<Data>(), set<Data>()
    and <Data>(), where <Data> is either Adapter or Flow.

    Class attributes:
        pasted: A Qt signal emitted when the Mime data are pasted, allowing to
            correctly finalize any pending cut action.

    Properties:
        action: the ClipboardAction applied to the Mime data instance (COPY or
        MOVE). COPY by default.
    """

    pasted = QtCore.pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._action = dt.ClipboardAction.COPY
        self._dcfsData = None
        self._dcfsDataKind = None

    @property
    def action(self) -> dt.ClipboardAction:
        return self._action

    @action.setter
    def action(self, value: dt.ClipboardAction):
        self._action = value

    def setAdapter(self, adapter, kind: dt.ProjectItemKind):
        """Sets the Adapter stored in the MIME data object.

        Args:
            adapter: the adapter object to store.
            kind: the kind of adapter to store
        """
        self._dcfsData = adapter
        self._dcfsDataKind = kind
        super().setData('application/x-dcfsadapter', QtCore.QByteArray())

    def hasAdapter(self) -> bool:
        """Check if an adapter is stored the MIME data object.

        Returns:
            True if an adapter is stored the MIME data object
        """
        return self.hasFormat('application/x-dcfsadapter')

    def adapter(self):
        """Get the adapter stored in the MIME data object if any, None otherwise.
        """
        if not self.hasFormat('application/x-dcfsadapter'):
            return None
        return self._dcfsDataKind, self._dcfsData

    def setFlow(self, flow, kind: dt.DcfsDataKind):
        """Sets the flow stored in the MIME data object.

        Args:
            flow: the flow object to store.
            kind: the kind of flow to store
        """
        self._dcfsData = flow
        self._dcfsDataKind = kind
        super().setData('application/x-dcfsflow', QtCore.QByteArray())

    def hasFlow(self) -> bool:
        """Check if a flow is stored the MIME data object.

        Returns:
            True if a flow is stored the MIME data object
        """
        return self.hasFormat('application/x-dcfsflow')

    def flow(self):
        """Get the flow stored in the MIME data object if any, None otherwise.
        """
        if not self.hasFormat('application/x-dcfsflow'):
            return None
        return self._dcfsDataKind, self._dcfsData

    def updateOnDelete(self, **kwargs):
        """A slot called when an adapter or flow is deleted.

        Clear the clipboard if its content is the deleted object.

        Args:
            **kwargs: either 'adapter' or 'flow' keyword argument.
        """
        if self.hasFormat('application/x-dcfsadapter'):
            adapter = kwargs['adapter']
            kind, a = self.adapter()
            if kind in (
                dt.ProjectItemKind.DOMAIN_ADAPTER,
                dt.ProjectItemKind.ADAPTER_VARIANT,
                dt.ProjectItemKind.SPECIFIC_ADAPTER
            ) and a.name == adapter.name:
                QtWidgets.qApp.clipboard().clear()
        elif self.hasFormat('application/x-dcfsflow'):
            flow = kwargs['flow']
            kind, f = self.flow()
            if kind in (
                dt.DcfsDataKind.PRC,
                dt.DcfsDataKind.DTH
            ) and f.name == flow.name:
                QtWidgets.qApp.clipboard().clear()


class StackedToolbar(QtWidgets.QWidget):
    """A stack of toolbars where only one toolbar is visible at a time.

    Its interface is analog to the QStackedWidget interface but dedicated to
    QToolBar. Individual toolbars are not identified by an index but by a string
    key.
    Toolbars in the stack cannot be floatable.

    Args:
        title: an optional title for the toolbars stack ('Stack tools' by default).
        parent: an optional parent for the toolbars stack.

    Class attributes:
        currentChanged: This signal is emitted whenever the current toolbar
            changes. The parameter holds the key of the new current toolbar, or
            an empty string if there isn't a new one (for example, if there are
            no toolbars in the stack).
            Notifier signal for property currentKey.

    Properties:
        count: This property holds the number of toolbars contained in the
            stack. 0 by default.
            Access functions: count()
        currentKey: This property holds the key of the toolbar that is visible.
            The current key is the empty string if there is no current toolbar.
            By default, this property contains an empty string because the stack
            is initially empty.
            Access functions: currentKey(), currentKey(key: str)
            Notifier signal: currentChanged(key: str)
    """

    currentChanged = QtCore.pyqtSignal(str)

    def __init__(self, title: str = '', parent=None):
        super().__init__(parent)

        self.parent = parent
        title = title if title else 'Stack tools'
        toolbar = QtWidgets.QToolBar(title, parent)
        toolbar.setIconSize(QtCore.QSize(40, 40))
        toolbar.setObjectName('StackTools')
        toolbar.setFloatable(False)
        toolbar.setVisible(False)
        self._toolbar = toolbar
        self._stack = dict()
        self._keyFromId = dict()
        self._current = ''
        self.currentChanged.emit('')

    def count(self) -> int:
        """Getter of the count property"""
        return len(self._stack)

    def keyOf(self, tb: QtWidgets.QToolBar) -> str:
        """Look for the key of a given toolbar.

        Args:
            tb: the toolbar to look for its key.

        Returns:
            The key of the given toolbar, or an empty string if the given
            toolbar is not in the stack.
        """
        return self._keyFromId.get(id(tb), '')

    def toolbar(self, key: str = '') -> QtWidgets.QToolBar:
        """Look for the toolbar with a given key.

        Args:
            key: Optional key to look for.

        Returns:
            The toolbar with the given key, or None if there is no such toolbar.
            If no key is given, returns the toolbars stack itself.
        """
        if not key:
            return self._toolbar
        return self._stack.get(key, None)

    def currentKey(self) -> str:
        """Getter of the currentKey property"""
        return self._current

    def setCurrentKey(self, key: str):
        """Setter of the currentKey property"""
        self._current = key
        self._toolbar.setVisible(False)
        self._toolbar.clear()
        if key and key in self._stack:
            for action in self._stack[key].actions():
                if action.isSeparator():
                    self._toolbar.addSeparator()
                else:
                    self._toolbar.addAction(action)
            self._toolbar.setVisible(True)
        self.currentChanged.emit(key)

    def currentToolbar(self) -> Optional[QtWidgets.QToolBar]:
        """Get the current toolbar in the stack.

        Returns:
            The current toolbar, or None if there are no child toolbars.
        """
        if self._current:
            return self._stack[self._current]
        return None

    def setCurrentToolbar(self, tb: Optional[QtWidgets.QToolBar]):
        """Sets the current toolbar to be the specified toolbar.

        The new current toolbar must already be contained in the stack.
        If the specified toolbar is None, the current toolbar is cleared and
        there is no current toolbar.

        Args:
            tb:
        """
        current = self._keyFromId[id(tb)] if tb else ''
        self._current = current
        self._toolbar.setVisible(False)
        self._toolbar.clear()
        if tb:
            for action in tb.actions():
                if action.isSeparator():
                    self._toolbar.addSeparator()
                else:
                    self._toolbar.addAction(action)
            self._toolbar.setVisible(True)
        self.currentChanged.emit(current)

    def setEnabled(self, enable: bool):
        """Enable/Disable all actions of all toolbars in the stack.

        Args:
            enable: True to enable the actions / toolbars.
        """
        for tb in self._stack.values():
            for action in tb.actions():
                action.setEnabled(enable)

    def addToolbar(self, key: str, tb: QtWidgets.QToolBar) -> bool:
        """Add the given toolbar to the stack withe the given key.

        If the key/toolbar exists in the stack, nothing happens.
        If the stack is empty before this function is called, the toolbar
        becomes the current one.

        Args:
            key: the toolbar key to add.
            tb: the toolbar to add with that key.

        Returns:
            False if:
                - the given toolbar is not a QToolBar instance
                - the given key exists in the stack but with another toolbar
                - the given toolbar exists in the stack but with another key
            True otherwise.
        """
        if not isinstance(tb, QtWidgets.QToolBar):
            return False

        if key in self._stack:
            return self._stack[key] is tb

        if id(tb) in self._keyFromId:
            return self._keyFromId[id(tb)] == key

        self._stack[key] = tb
        self._keyFromId[id(tb)] = key
        tb.setVisible(False)

        if self.count() == 1:
            self.setCurrentKey(key)

        return True

    def removeToolbar(self, tb: QtWidgets.QToolBar):
        """Removes the given toolbar from the stack.

        The toolbar is not deleted but simply removed from the stack, causing
        it to be hidden.
        If it exists, the previous toolbar in the stack becomes the current one.

        Args:
            tb: the toolbar to be removed from the stack.

        Raises:
            ValueError if the given toolbar is not in the stack.
        """
        index = list(self._keyFromId).index(id(tb))
        key = self._keyFromId[id(tb)]
        del self._stack[key]
        del self._keyFromId[id(tb)]

        if self.count() > 0:
            self.setCurrentKey(list(self._keyFromId)[index - 1])


class TextFilterWidget(QtWidgets.QWidget):
    """A basic textual filter input widget.

    Allow to enter the text to filter on, set the filter on/off and toggle
    a match case option.

    Args:
        filterIcon: the icon of the filter on/off button.
        matchCaseIcon: the icon of the match case button.
        parent: an optional parent for the widget.

    Class attributes:
        toggled: This signal is emitted whenever the filter on/off button is
            toggled. The parameter is True when the filter is on.
        matchCaseToggled: This signal is emitted whenever the match case button
            is toggled. The parameter is True when the match case option is on.
        filterTextEdited: This signal is emitted whenever the text filter
            changes. The parameter is the new text to filter.

    Attributes:
        textFilterBtn: the filter on/off button.
        filterText: the text filter line edit widget.
    """

    toggled = QtCore.pyqtSignal(bool)
    matchCaseToggled = QtCore.pyqtSignal(bool)
    filterTextEdited = QtCore.pyqtSignal(str)

    def __init__(self, filterIcon: QtGui.QIcon, matchCaseIcon: QtGui.QIcon, parent=None):
        super().__init__(parent)

        self.textFilterBtn = QtWidgets.QToolButton()
        self.textFilterBtn.setIconSize(QtCore.QSize(24, 24))
        self.textFilterBtn.setIcon(filterIcon)
        self.textFilterBtn.setCheckable(True)
        self.textFilterBtn.setToolTip('Filter flows on text content')
        self.textFilterBtn.setStatusTip('Filter flows on text content')
        self.textFilterBtn.toggled.connect(self.toggled)                # noqa

        self.matchCaseBtn = QtWidgets.QToolButton()
        self.matchCaseBtn.setIconSize(QtCore.QSize(24, 24))
        self.matchCaseBtn.setIcon(matchCaseIcon)
        self.matchCaseBtn.setCheckable(True)
        self.matchCaseBtn.setToolTip('Match case')
        self.matchCaseBtn.toggled.connect(self.toggleMatcCase)             # noqa

        self.filterText = QtWidgets.QLineEdit()
        self.filterText.setPlaceholderText('')
        self.filterText.setClearButtonEnabled(True)
        self.filterText.textChanged.connect(self.filterTextEdited)           # noqa
        self.filterText.returnPressed.connect(self.triggerTextFilter)        # noqa

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.textFilterBtn)
        layout.addWidget(self.matchCaseBtn)
        layout.addWidget(self.filterText)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    @QtCore.pyqtSlot(bool)
    def toggleMatcCase(self, checked: bool):
        """This slot is called when the match case option is toggled.

        Args:
            checked: the state of the match case option (True if on).
        """
        tip = 'Match case' if checked else ''
        self.filterText.setPlaceholderText(tip)
        self.matchCaseToggled.emit(checked)

    @QtCore.pyqtSlot()
    def triggerTextFilter(self):
        """Called on a Return pressed event to toggle the filter on/off. """
        checked = not self.textFilterBtn.isChecked()
        self.textFilterBtn.setChecked(checked)

    def clear(self):
        self.textFilterBtn.setChecked(False)
        self.matchCaseBtn.setChecked(False)
        self.filterText.setText('')


class ZoomController(QtWidgets.QWidget):

    valueChanged = QtCore.pyqtSignal(int)
    fitSelected = QtCore.pyqtSignal()

    def __init__(
            self,
            zoomOutIcon: QtGui.QIcon, zoomInIcon: QtGui.QIcon,
            zoomFitIcon: QtGui.QIcon, zoom100Icon: QtGui.QIcon,
            zoomMin: int = 5, zoomMax: int = 200, zoomStep: int = 10,
            parent=None):
        super().__init__(parent)

        self.zoomStep = zoomStep

        zoomLbl = QtWidgets.QLineEdit()
        zoomLbl.setReadOnly(True)
        zoomLbl.setAlignment(QtCore.Qt.AlignRight)
        zoomLbl.setFrame(False)
        palette = zoomLbl.palette()
        palette.setColor(QtGui.QPalette.Base, QtCore.Qt.transparent)
        zoomLbl.setPalette(palette)
        zoomLbl.setFixedWidth(50)

        self.zoomSlider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.zoomSlider.setRange(zoomMin, zoomMax)

        iconSize = QtCore.QSize(29, 29)
        zoomToExtent = QtWidgets.QPushButton(zoomFitIcon, '')
        zoomToExtent.setIconSize(iconSize)
        zoomToExtent.setToolTip('Zoom to extent')
        zoomToExtent.setFlat(True)
        zoom100 = QtWidgets.QPushButton(zoom100Icon, '')
        zoom100.setIconSize(iconSize)
        zoom100.setToolTip('Zoom to actual size')
        zoom100.setFlat(True)
        iconSize = QtCore.QSize(20, 20)
        zoomOut = QtWidgets.QPushButton(zoomOutIcon, '')
        zoomOut.setIconSize(iconSize)
        zoomOut.setToolTip('Zoom out')
        zoomOut.setFlat(True)
        zoomIn = QtWidgets.QPushButton(zoomInIcon, '')
        zoomIn.setIconSize(iconSize)
        zoomIn.setToolTip('Zoom in')
        zoomIn.setFlat(True)

        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(zoomLbl)
        layout.addWidget(zoomToExtent)
        layout.addWidget(zoomOut)
        layout.addWidget(self.zoomSlider)
        layout.addWidget(zoomIn)
        layout.addWidget(zoom100)
        layout.addStretch()

        self.setLayout(layout)

        self.zoomSlider.valueChanged.connect(
            lambda z: zoomLbl.setText(f'{z:>3} %')
        )
        self.zoomSlider.valueChanged.connect(
            lambda z: self.valueChanged.emit(z)
        )
        zoomToExtent.clicked.connect(
            lambda: self.fitSelected.emit()
        )
        zoomOut.clicked.connect(
            lambda: self.zoomSlider.setValue(self.zoomSlider.value() - self.zoomStep))

        zoomIn.clicked.connect(
            lambda: self.zoomSlider.setValue(self.zoomSlider.value() + self.zoomStep)
        )
        zoom100.clicked.connect(
            lambda: self.setValue(100)
        )

    def value(self) -> int:
        return self.zoomSlider.value()

    def setValue(self, value: int):
        self.zoomSlider.setValue(value)


class HistoryBrowser(QtWidgets.QWidget):

    itemActivated = QtCore.pyqtSignal(str)
    itemReloaded = QtCore.pyqtSignal(str)

    def __init__(
            self,
            backIcon: QtGui.QIcon, forwardIcon: QtGui.QIcon,
            reloadIcon: QtGui.QIcon,
            activeIcon: QtGui.QIcon,
            inactiveBackIcon: QtGui.QIcon, inactiveFwdIcon: QtGui.QIcon,
            itemKind: str = 'item',
            history=None,
            parent=None):
        super().__init__(parent)

        self._itemKind = itemKind
        self._history = []
        self._currentIndex = -1

        self._activeIcon = activeIcon
        self._inactiveBackIcon = inactiveBackIcon
        self._inactiveFwdIcon = inactiveFwdIcon

        iconSize = QtCore.QSize(32, 32)
        self.backBtn = QtWidgets.QToolButton()
        self.backBtn.setToolTip(f'Go back one {self._itemKind}')
        self.backBtn.setIconSize(iconSize)
        self.backBtn.setPopupMode(QtWidgets.QToolButton.DelayedPopup)
        self.backBtn.setAutoRaise(True)
        self.backBtn.setIcon(backIcon)
        self.backBtn.setMenu(QtWidgets.QMenu('Back', self))
        self.backBtn.clicked.connect(self.goBack)

        self.fwdBtn = QtWidgets.QToolButton()
        self.fwdBtn.setToolTip(f'Go forward one {self._itemKind}')
        self.fwdBtn.setIconSize(iconSize)
        self.fwdBtn.setPopupMode(QtWidgets.QToolButton.DelayedPopup)
        self.fwdBtn.setAutoRaise(True)
        self.fwdBtn.setIcon(forwardIcon)
        self.fwdBtn.setMenu(QtWidgets.QMenu('Forward', self))
        self.fwdBtn.clicked.connect(self.goForward)

        self.reloadBtn = QtWidgets.QPushButton(reloadIcon, '')
        self.reloadBtn.setToolTip(f'Reload current {self._itemKind}')
        self.reloadBtn.setIconSize(iconSize)
        self.reloadBtn.setFlat(True)
        self.reloadBtn.clicked.connect(self.reload)

        historyFrame = QtWidgets.QFrame(self)
        historyFrame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        historyFrame.setFrameShadow(QtWidgets.QFrame.Plain)

        historyLayout = QtWidgets.QHBoxLayout()
        historyLayout.setSpacing(0)
        historyLayout.setContentsMargins(0, 0, 0, 0)
        historyLayout.addWidget(self.backBtn)
        historyLayout.addWidget(self.fwdBtn)
        historyLayout.addWidget(self.reloadBtn)
        historyFrame.setLayout(historyLayout)

        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(historyFrame)

        self.setLayout(layout)

        if not history:
            history = []
        self.addItems(history)

    def addItem(self, item: str):
        if item not in self._history:
            self._history.append(item)
            self._currentIndex = len(self._history) - 1

            backAction = QtWidgets.QAction(item, self)
            backAction.triggered.connect(
                lambda _, idx=self._currentIndex: self.showItem(index=idx)
            )
            fwdAction = QtWidgets.QAction(item, self)
            fwdAction.triggered.connect(
                lambda _, idx=self._currentIndex: self.showItem(index=idx)
            )
            self.backBtn.menu().addAction(backAction)
            self.fwdBtn.menu().addAction(fwdAction)
            self._updateMenus()
        else:
            self._currentIndex = self._history.index(item)
            self._updateMenus()

    def addItems(self, items: List[str]):
        for item in items:
            self.addItem(item)

    def setCurrentItem(self, item: str):
        if item not in self._history:
            self._currentIndex = len(self._history) - 1
        else:
            self._currentIndex = self._history.index(item)
        self._updateMenus()

    def clear(self):
        self._history = []
        self._currentIndex = -1
        self.backBtn.menu().clear()
        self.fwdBtn.menu().clear()

    @QtCore.pyqtSlot()
    def goBack(self):
        if self._currentIndex > 0:
            self._currentIndex -= 1
            self.itemActivated.emit(self._history[self._currentIndex])
            self._updateMenus()

    @QtCore.pyqtSlot()
    def goForward(self):
        if self._currentIndex < len(self._history) - 1:
            self._currentIndex += 1
            self.itemActivated.emit(self._history[self._currentIndex])
            self._updateMenus()

    @QtCore.pyqtSlot()
    def reload(self):
        self.itemReloaded.emit(self._history[self._currentIndex])

    @QtCore.pyqtSlot(int)
    def showItem(self, index: int):
        self._currentIndex = index
        self.itemActivated.emit(self._history[index])
        self._updateMenus()

    def _updateMenus(self):
        self.backBtn.setEnabled(self._currentIndex > 0)
        self.fwdBtn.setEnabled(self._currentIndex < len(self._history) - 1)

        # Backward menu
        for i, a in enumerate(self.backBtn.menu().actions()):
            if i < self._currentIndex:
                a.setVisible(True)
                a.setIcon(self._inactiveBackIcon)
            elif i > self._currentIndex:
                a.setVisible(False)
            else:
                a.setVisible(True)
                a.setIcon(self._activeIcon)

        # Forward menu
        for i, a in enumerate(self.fwdBtn.menu().actions()):
            if i < self._currentIndex:
                a.setVisible(False)
            elif i > self._currentIndex:
                a.setVisible(True)
                a.setIcon(self._inactiveFwdIcon)
            else:
                a.setVisible(True)
                a.setIcon(self._activeIcon)


class SplashScreen(QtWidgets.QSplashScreen):
    def __init__(self, pixmap: QtGui.QPixmap, version: str, flags) -> None:
        super().__init__(pixmap, flags)
        self._version = version
        self._progress = 0
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
        painter.restore()

    def setProgress(self, value: int) -> None:
        """Update the splash screen progress bar

        Args:
             value: percent done, between 0 and 100
        """
        self._progress = value
        # time.sleep(0.2)
        self.repaint()


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


class TimelineView(QtWidgets.QWidget):

    barColor = QtGui.QColor(127, 0, 127)

    def __init__(self, timeline: Optional[Counter] = None, parent = None):
        super().__init__(parent)

        self._timeline = timeline
        if timeline is None:
            self._start = date.today() - timedelta(days=30)
            self._end = date.today()
            self._minY = self._maxY = 0
        else:
            self.setTimeline(timeline)
        self._margin = 8

        self.setWindowTitle("Timeline")
        self.resize(600, 200)

    def setTimeline(self, timeline: Counter):
        self._timeline = timeline
        self._start = list(timeline.keys())[0]
        self._end = list(timeline.keys())[-1]
        self._x, self._y = zip(*timeline.most_common())
        self._minY = min(*self._y)
        self._maxY = max(*self._y)
        self.update()

    def getStart(self) -> date:
        return self._start

    def getEnd(self) -> date:
        return self._end

    def paintEvent(self, event):
        width = self.width()
        height = self.height()
        margin = self._margin
        barWidth = 20
        start = self._start
        end = self._end
        points = zip(self._x, self._y)
        scaleX = width / ((end - start) / timedelta(days=1))
        scaleY = (height - 2*margin) / self._maxY

        background = QtGui.QBrush(QtGui.QColor(127, 127, 127))
        foreground = QtGui.QBrush(self.barColor)
        # foreground = QtGui.QPen(self.barColor)
        # textPen = QtGui.QPen(option.palette.color(QtGui.QPalette.Text))
        # highlightedPen = QtGui.QPen(option.palette.color(QtGui.QPalette.HighlightedText))

        # https://stackoverflow.com/questions/4413570/use-window-viewport-to-flip-qpainter-y-axis
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.translate(0, height)
        painter.scale(1, -1)

        bgRect = QtCore.QRect(0, 0, width, height)
        painter.fillRect(bgRect, background)
        painter.setPen(self.barColor)
        timelineRect = QtCore.QRectF(
            margin, margin,
            width - 2*margin, height - 2*margin
        )
        painter.drawRect(timelineRect)
        painter.setBrush(foreground)
        painter.setPen(QtCore.Qt.NoPen)

        i = 0
        for x, y in points:
            pointRect = QtCore.QRect(
                margin + i*(margin + barWidth),
                # ((x - start) / timedelta(days=1)) * scaleX,
                margin,
                20,
                y * scaleY,
            )
            i += 1
            painter.fillRect(pointRect, self.barColor)


if __name__ == '__main__':

    import sys

    app = QtWidgets.QApplication(sys.argv)
    tl = Counter(
        {
            date(2021, 2, 14): 5,
            date(2021, 3, 20): 90,
            date(2021, 4, 16): 16,
        }
    )
    timeline = TimelineView(tl)
    timeline.show()
    sys.exit(app.exec_())
