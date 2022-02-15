"""A set of useful Qt5 utilities.

It provides:
    - A customized status bar.
    - A QProgressBar that show background task progress.
    - A descriptor that wraps a Qt Signal.
    - A customized splash screen.
    - A QLineEdit that fit its content while minimizing its size.
    - A dialog to select file or directory path.
    - A plain text editor with auto-completion.
    - A tool to layout two widgets horizontally or vertically.
    - A tool to create a QAction.
    - A tool to retrieve the application main window.
    - A tool to reconnect a Qt signal to another slot.
    - A DcfsStyle class to override some default settings of the application
      style.
    - A standard QStyledItemDelegate that hides focus decoration.
    - A QSyntaxHighlighter that highlight all occurrences of a string pattern.
    - A basic textual filter input widget.
"""
from typing import Callable, Optional, Union


import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from .statusbar import StatusBar
from .backgroundprogressbar import BackgroundProgressBar
from .signaladpater import QtSignalAdapter
from .splash import SplashScreen
from .fittedlineedit import FittedLineEdit
from .pathselector import PathSelector, DirectorySelector, FileSelector
from .autocompletetextedit import AutoCompleteTextEdit
from .collapsiblewidget import CollapsibleWidget
from .framewidget import QFramedWidget
from .panelview import QPanelView


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
        tip: optional tool tip and status tip of the QAction.
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


def reconnect(signal, newSlot=None, oldSlot=None):
    try:
        if oldSlot is not None:
            while True:
                signal.disconnect(oldSlot)
        else:
            signal.disconnect()
    except TypeError:
        pass
    if newSlot is not None:
        signal.connect(newSlot)


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
    Adjust the size of the view item decoration (apply to QTreeView and
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
