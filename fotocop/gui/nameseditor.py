import re
import webbrowser
from typing import TYPE_CHECKING, Optional, Tuple, List, Dict, NamedTuple
from enum import  Enum, auto
from copy import deepcopy

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Visitor
from fotocop.models.naming import TOKEN_FAMILIES, TOKEN_GENUS, TOKENS_ROOT_NODE, Token

if TYPE_CHECKING:
    from fotocop.models.naming import NamingTemplate, TokenNode, TokenTree, TokenFamily, TokenGenus
    from fotocop.models.downloader import Downloader

NEW_TEMPLATE = "Save New Custom Preset..."
DELETE_ALL_TEMPLATES = "Remove All Custom Presets..."

TOKEN_COLORS = {
    "Date time": "#49c222",
    "Filename": "#279ac2",
    "Sequences": "#9e2cc2",
    "Session": "#c24116",
}


class CursorPosition(Enum):
    IN = auto()
    BETWEEN = auto()


class TokenFootprint(NamedTuple):
    token: Token
    index: int
    start: int
    end: int


class CursorNeighborhood(NamedTuple):
    position: CursorPosition
    leftToken: TokenFootprint
    rightToken: TokenFootprint


class EditorComboBox(QtWidgets.QComboBox):
    """Regular QComboBox that ignores the mouse wheel.

    Leave the wheel event to scroll its parent scrollable widget.
    """

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        event.ignore()


class PrefHighlighter(QtGui.QSyntaxHighlighter):
    """
    Highlight non-text preference values in the editor
    """

    blockHighlighted = QtCore.pyqtSignal()

    def __init__(self, pref_defn_strings: List[str],
                 pref_color: Dict[str, str],
                 document: QtGui.QTextDocument) -> None:
        super().__init__(document)

        # Where detected preference values start and end:
        # [(start, end), (start, end), ...]
        # self.boundaries = SortedList()

        pref_defns = ('<{}>'.format(pref) for pref in pref_defn_strings)
        self.highlightingRules = []
        for pref in pref_defns:
            format = QtGui.QTextCharFormat()
            format.setForeground(QtGui.QBrush(QtGui.QColor(pref_color[pref])))
            self.highlightingRules.append((pref, format))

    def find_all(self, text: str, pref_defn: str):
        """
        Find all occurrences of a preference definition in the text
        :param text: text to search
        :param pref_defn: the preference definition
        :return: yield the position in the document's text
        """
        if not len(pref_defn):
            return  # do not use raise StopIteration as it is Python 3.7 incompatible
        start = 0
        while True:
            start = text.find(pref_defn, start)
            if start == -1:
                return  # do not use raise StopIteration as it is Python 3.7 incompatible
            yield start
            start += len(pref_defn)

    def highlightBlock(self, text: str) -> None:

        # Recreate the preference value from scratch
        # self.boundaries = SortedList()

        for expression, format in self.highlightingRules:
            for index in self.find_all(text, expression):
                length = len(expression)
                self.setFormat(index, length, format)
                # self.boundaries.add((index, index + length - 1))

        self.blockHighlighted.emit()


class TemplateTextEdit(QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.highlighter = TokenHighlighter(self.document())

        self._editedTemplate: Optional["NamingTemplate"] = None
        self._selectedToken: Optional["Token"] = None
        self._heightMin = 0
        self._heightMax = 200

        self.document().documentLayout().documentSizeChanged.connect(self.wrapHeightToContents)

    @QtCore.pyqtSlot()
    def wrapHeightToContents(self):
        """
        Adjust the text area size to show contents without vertical scrollbar

        Derived from:
        http://stackoverflow.com/questions/11851020/a-qwidget-like-qtextedit-that-wraps-its-height-
        automatically-to-its-contents/11858803#11858803
        """
        docHeight = self.document().size().height() + 5
        if self._heightMin <= docHeight <= self._heightMax and docHeight > self.minimumHeight():
            self.setMinimumHeight(docHeight)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        super().mousePressEvent(event)

        if event.button() == QtCore.Qt.LeftButton:
            cursor = self.textCursor()
            position = cursor.position()
            print(position)
            cursorNeighborhood = self._tokenAtPos(position)
            print(cursorNeighborhood)
            if cursorNeighborhood.position == CursorPosition.IN:
                token, index, start, end = cursorNeighborhood.leftToken
                self._selectedToken = token
                if token.genusName != "Free text":
                    cursor.setPosition(start + 1)
                    cursor.setPosition(end - 1, QtGui.QTextCursor.KeepAnchor)
                    self.setTextCursor(cursor)
            else:
                assert cursorNeighborhood.position == CursorPosition.BETWEEN
                leftToken, leftIndex, _, _ = cursorNeighborhood.leftToken
                rightToken, rightIndex, _, _ = cursorNeighborhood.rightToken
                if leftToken == self._selectedToken:
                    token = leftToken
                    index = leftIndex
                elif rightToken == self._selectedToken:
                    token = rightToken
                    index = rightIndex
                else:
                    self._selectedToken = None
                    return
            if token.genusName != "Free text":
                menu = QtWidgets.QMenu()
                genus = token.parent
                actions = list()
                for child in genus.children:
                    action = QtWidgets.QAction(child.name)
                    action.setCheckable(True)
                    if child.name == token.name:
                        action.setChecked(True)
                    actions.append(action)
                menu.addActions(actions)
                menu.triggered.connect(lambda a, i=index: self._changeToken(a, i))
                pos = event.globalPos()
                pos.setY(pos.y() + 10)
                menu.exec(pos)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        super().mouseMoveEvent(event)

        cursor = self.cursorForPosition(event.pos())
        position = cursor.position()
        cursorNeighborhood = self._tokenAtPos(position)
        if cursorNeighborhood.position == CursorPosition.BETWEEN:
            self.viewport().setCursor(QtCore.Qt.IBeamCursor)
        else:
            token, _, _, _ = cursorNeighborhood.leftToken
            if token.genusName == "Free text":
                self.viewport().setCursor(QtCore.Qt.IBeamCursor)
            else:
                self.viewport().setCursor(QtCore.Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        pass

    def mouseDoubleClickEvent(self, e: QtGui.QMouseEvent):
        pass

    # def contextMenuEvent(self, event: QtGui.QContextMenuEvent):
    #     menu = QtWidgets.QMenu()
    #     menu.addAction("menu item 1")
    #     menu.addAction("menu item 2")
    #     menu.exec(event.globalPos())

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Automatically select tokens when navigating through the document.

        Suppress the return / enter key.

        Args:
            event: the key press event.
        """
        key = event.key()
        ctrl = event.modifiers() & QtCore.Qt.ControlModifier    # noqa

        if key in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return, QtCore.Qt.Key_Tab):
            return

        if key == QtCore.Qt.Key_Escape:
            super().keyPressEvent(event)
            return

        if ctrl and key in (
            QtCore.Qt.Key_A, QtCore.Qt.Key_C, QtCore.Qt.Key_V,
            QtCore.Qt.Key_Z, QtCore.Qt.Key_Y, QtCore.Qt.Key_X
        ):
            super().keyPressEvent(event)
            return

        cursor = self.textCursor()

        if cursor.hasSelection() and key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right):
            if key == QtCore.Qt.Key_Left:
                cursor.setPosition(cursor.selectionStart() - 1)
            else:
                cursor.setPosition(cursor.selectionEnd() + 1)
            self.setTextCursor(cursor)
            return

        if key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Backspace):
            position = cursor.position()
            cursorNeighborhood = self._tokenAtPos(position)
            if cursorNeighborhood.position == CursorPosition.IN:
                token, index, start, end = cursorNeighborhood.leftToken
                newPos = start
            else:
                assert cursorNeighborhood.position == CursorPosition.BETWEEN
                if key == QtCore.Qt.Key_Delete:
                    token, index, start, end = cursorNeighborhood.rightToken
                    newPos = position
                else:
                    assert key == QtCore.Qt.Key_Backspace
                    token, index, start, end = cursorNeighborhood.leftToken
                    newPos = position - len(token.asText())
            if token.name != "":
                backward = (key == QtCore.Qt.Key_Backspace)
                if token.genusName == "Free text" and len(token.name) > 1:
                    self._delCarInFreetext(index, position - start, backward)
                    cursor.setPosition(position - 1 if backward else position)
                    self.setTextCursor(cursor)
                else:
                    self._removeToken(index)
                    cursor.setPosition(newPos)
                    self.setTextCursor(cursor)
            return

        if bool(re.match(r'^[a-zA-Z0-9-_]$', event.text())):
            position = cursor.position()
            cursorNeighborhood = self._tokenAtPos(position)
            if cursorNeighborhood.position == CursorPosition.IN:
                token, index, start, end = cursorNeighborhood.leftToken
                if token.genusName != "Free text":
                    return
                else:
                    self._updateFreetext(event.text(), index, position - start)
                    cursor.setPosition(position + 1)
                    self.setTextCursor(cursor)
                    return
            else:
                assert cursorNeighborhood.position == CursorPosition.BETWEEN
                leftToken, leftIndex, leftStart, leftEnd = cursorNeighborhood.leftToken
                rightToken, rightIndex, rightStart, rightEnd = cursorNeighborhood.rightToken
                if leftToken.genusName == "Free text":
                    self._updateFreetext(event.text(), leftIndex, position - leftStart)
                    cursor.setPosition(position + 1)
                    self.setTextCursor(cursor)
                    return
                elif rightToken.genusName == "Free text":
                    self._updateFreetext(event.text(), rightIndex, position - rightStart)
                    cursor.setPosition(position + 1)
                    self.setTextCursor(cursor)
                    return
                else:
                    self._insertFreetext(event.text(), rightIndex)
                    cursor.setPosition(position + 1)
                    self.setTextCursor(cursor)
                    return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        key = event.key()
        cursor = self.textCursor()
        position = cursor.position()
        print(position)

        backward = key in (
            QtCore.Qt.Key_Left, QtCore.Qt.Key_Home,
            QtCore.Qt.Key_PageUp, QtCore.Qt.Key_Up
        )
        forward = key in (
            QtCore.Qt.Key_Right, QtCore.Qt.Key_End,
            QtCore.Qt.Key_PageDown, QtCore.Qt.Key_Down
        )
        if backward or forward:
            cursorNeighborhood = self._tokenAtPos(position)
            print(cursorNeighborhood)
            self._selectedToken = None
            if cursorNeighborhood.position == CursorPosition.IN:
                token, _, one, two = cursorNeighborhood.leftToken
                if token.genusName != "Free text":
                    if forward:
                        start = one + 1
                        end = two - 1
                    else:
                        start = two - 1
                        end = one + 1
                    self._selectedToken = token
                    cursor.setPosition(start)
                    cursor.setPosition(end, QtGui.QTextCursor.KeepAnchor)
                    self.setTextCursor(cursor)
                    return

        super().keyReleaseEvent(event)

    def _tokenAtPos(self, position: int) -> CursorNeighborhood:
        template = self._editedTemplate

        if template is None:
            return CursorNeighborhood(
                CursorPosition.BETWEEN,
                TokenFootprint(Token("", "Free text", None), -1, 0, 0),
                TokenFootprint(Token("", "Free text", None), -1, 0, 0)
            )

        previousFootprint = TokenFootprint(Token("", "Free text", None), -1, 0, 0)
        for index, boundary in enumerate(template.boundaries()):
            if position == boundary.start:
                # At start or between two tokens
                return CursorNeighborhood(
                    CursorPosition.BETWEEN,
                    previousFootprint,
                    TokenFootprint(template.template[index], index, position, boundary.end)
                )
            if boundary.start < position < boundary.end:
                # In a token
                footprint = TokenFootprint(template.template[index], index, boundary.start, boundary.end)
                return CursorNeighborhood(CursorPosition.IN, footprint, footprint)
            previousFootprint = TokenFootprint(template.template[index], index, boundary.start, boundary.end)
        # At end
        return CursorNeighborhood(
            CursorPosition.BETWEEN,
            previousFootprint,
            TokenFootprint(Token("", "Free text", None), len(template.template), position, position)
        )

    def setTemplate(self, template: "NamingTemplate"):
        print(template.boundaries())
        self._editedTemplate = deepcopy(template)
        self.setPlainText(template.asText())

    def _changeToken(self, action: QtWidgets.QAction, index: int):
        print(action.text(), index)
        token = TOKENS_ROOT_NODE.tokensByName[action.text()]
        print(token)
        tokens = list(self._editedTemplate.template)
        tokens[index] = token
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _removeToken(self, index: int):
        print(index)
        tokens = list(self._editedTemplate.template)
        del tokens[index]
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _updateFreetext(self, text: str, index: int, position: int):
        print(text, index, position)
        tokens = list(self._editedTemplate.template)

        if index < 0:
            # Add a new free text token at the beginning of the template.
            tokens.insert(0, Token(text, "Free text", None))

        elif index < len(tokens):
            # Update the text of the token.
            token = tokens[index]
            token.name = token.name[:position] + text + token.name[position:]

        else:
            # Add a new free text token at the end of the template.
            token = Token(text, "Free text", None)
            tokens.insert(len(tokens), Token(text, "Free text", None))

        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _delCarInFreetext(self, index: int, position: int, backward: bool):
        print(index, position, backward)
        tokens = list(self._editedTemplate.template)
        token = tokens[index]
        if backward:
            token.name = token.name[:position - 1] + token.name[position:]
        else:
            token.name = token.name[:position] + token.name[position + 1:]
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _insertFreetext(self, text: str, index: int):
        print(text, index)
        tokens = list(self._editedTemplate.template)
        tokens.insert(index, Token(text, "Free text", None))
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    @QtCore.pyqtSlot(Token)
    def insertToken(self, token: Token):
        print(token.genusName, token.name, token.formatSpec)
        tokens = list(self._editedTemplate.template)
        cursor = self.textCursor()
        position = cursor.position()
        cursorNeighborhood = self._tokenAtPos(position)
        _, index, start, end = cursorNeighborhood.rightToken
        insertPos = start
        if cursorNeighborhood.position == CursorPosition.IN:
            index = min(index + 1, len(tokens))
            insertPos = end
        tokens.insert(index, token)
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())
        cursor.setPosition(insertPos + len(token.asText()))
        self.setTextCursor(cursor)
        self.setFocus()


class HighlightingRule(NamedTuple):
    pattern: QtCore.QRegularExpression
    format: QtGui.QTextCharFormat


class TokenHighlighter(QtGui.QSyntaxHighlighter):
    """A QSyntaxHighlighter that highlight all occurrences of Token objects.

    From https://doc.qt.io/qt-5/qtwidgets-richtext-syntaxhighlighter-example.html.

    Args:
        document: the document to highlight.

    Attributes:
        highlightingRules: a list of HighlightingRule objects.
    """
    def __init__(self, document: QtGui.QTextDocument):
        super().__init__(document)

        self.highlightingRules = list()

        for family in TOKEN_FAMILIES:
            format_ = QtGui.QTextCharFormat()
            format_.setFontWeight(QtGui.QFont.Bold)
            format_.setForeground(QtGui.QColor(TOKEN_COLORS[family]))
            for genus in TOKEN_GENUS[family]:
                pattern = QtCore.QRegularExpression(fr"(\<{genus} \([a-zA-Z0-9 ]+\)\>)")
                rule = HighlightingRule(pattern, format_)
                self.highlightingRules.append(rule)

    def highlightBlock(self, text):
        """Highlight all text blocks that match one of the highlighting rules' pattern.

        The highlightBlock() method is called automatically whenever it is
        necessary by the rich text engine, i.e. when there are text blocks that
        have changed.

        Args:
            text: the string where to find pattern to highlight.
        """
        for rule in self.highlightingRules:
            i = rule.pattern.globalMatch(text)
            while i.hasNext():
                match = i.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), rule.format)


class NamingTemplateEditor(QtWidgets.QDialog):
    def __init__(self, fixedSize=True, parent=None):
        super().__init__(parent)

        # Prevent resizing the view when required.
        # if fixedSize:
        #     self.setWindowFlags(
        #         QtCore.Qt.Dialog |
        #         QtCore.Qt.MSWindowsFixedSizeDialogHint
        #     )

        self.setModal(True)

        self.buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel | QtWidgets.QDialogButtonBox.Help,
            QtCore.Qt.Horizontal, self
        )
        self.helpButton = self.buttonBox.button(QtWidgets.QDialogButtonBox.Help)
        self.helpButton.clicked.connect(self.helpButtonClicked)
        self.helpButton.setToolTip('Get help online...')

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def helpButtonClicked(self) -> None:
        location = '#rename'
        # location = '#subfoldergeneration'
        webbrowser.open_new_tab("http://www.damonlynch.net/rapid/documentation/{}".format(location))

    @property
    def record(self):
        return tuple()

    def reset(self):
        self.setEditMode(False)

    def setEditMode(self, editMode: bool):
        if editMode:
            self.setWindowTitle('Edit entry')
            self.addBtn.hide()
            self.prevBtn.show()
            self.nextBtn.show()
        else:
            self.setWindowTitle('Add entry')
            self.addBtn.show()
            self.prevBtn.hide()
            self.nextBtn.hide()

    def enableButtons(self, isValid: bool):
        self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(isValid)

    def setCompleterModel(self, _words):
        pass


class ImageNamingTemplateEditor(NamingTemplateEditor):
    def __init__(self, downloader: "Downloader", parent=None):
    # def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.downloader = downloader
        # self.downloader = parent.downloader

        self._templates = downloader.namingTemplates
        # self._templates: Optional["NamingTemplates"] = None
        # self._editedTemplate: Optional["NamingTemplate"] = None

        templateLbl = QtWidgets.QLabel('Preset:')
        self.templateCmb = QtWidgets.QComboBox()
        exampleLbl = QtWidgets.QLabel("Example:")
        self.example = QtWidgets.QLabel()
        self.templateTextEdit = TemplateTextEdit()
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        sizePolicy.setVerticalStretch(1)
        self.templateTextEdit.setSizePolicy(sizePolicy)

        glayout = QtWidgets.QGridLayout()
        glayout.addWidget(templateLbl, 0, 0)
        glayout.addWidget(self.templateCmb, 0, 1)
        glayout.addWidget(exampleLbl, 1, 0)
        glayout.addWidget(self.example, 1, 1)
        glayout.setColumnStretch(1, 1)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(glayout)
        layout.addSpacing(int(QtGui.QFontMetrics(QtGui.QFont()).height() / 2))
        layout.addWidget(self.templateTextEdit)
        # layout.addWidget(self.messageWidget)

        self.tokenSelectorList = TOKENS_ROOT_NODE.accept(TokenSelectorBuilder())
        layout.addWidget(self.tokenSelectorList)

        layout.addWidget(self.buttonBox)

        self.tokenSelectorList.tokenSelected.connect(self.templateTextEdit.insertToken)
        self.templateCmb.activated.connect(self._editTemplate)
        self.templateCmb.currentIndexChanged.connect(self._editTemplate)
        self.templateCmb.currentTextChanged.connect(self._updateExample)

        self.show()
        self.updateTemplates()

        # self.highlighter = QtUtil.PatternHighlighter(QtCore.QRegularExpression(r'(\<\w+\>)'), self.nameText.document())
        # self.setEditMode(False)
        # self.enableButtons(self.isValid)
        # self.nameText.setFocus()

    def updateTemplates(self):
    # def setTemplates(self, templates: "NamingTemplates", selectedName: str):
        # self._templates = templates
        templates = self._templates

        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()

            builtins = templates.listBuiltinImageNamingTemplates()
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.insertSeparator(len(builtins))

            customs = templates.listImageNamingTemplates()
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.addItem(NEW_TEMPLATE, NEW_TEMPLATE)
            self.templateCmb.addItem(DELETE_ALL_TEMPLATES, DELETE_ALL_TEMPLATES)

            self.templateCmb.setCurrentIndex(-1)

        self._setWidgetSizes()

    def _setWidgetSizes(self) -> None:
        """
        Resize widgets for enhanced visual layout
        """
        # Set the widths of the templates ComboBox to the width of the longest item text.
        width = max(
            QtGui.QFontMetrics(QtGui.QFont()).width(self.templateCmb.itemText(index))
            for index in range(self.templateCmb.count())
        )
        self.templateCmb.setMinimumWidth(width + 30)

        # Set the scroll area to be big enough to eliminate the horizontal scrollbar
        scrollbar_width = self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
        self.tokenSelectorList.setMinimumWidth(self.tokenSelectorList.widget().width() + scrollbar_width)

    def editTemplate(self, key: str):
        template = self._templates.getImageNamingTemplate(key)
        self.templateCmb.setCurrentText(template.name)

    @QtCore.pyqtSlot(int)
    def _editTemplate(self, index_: int):
        key = self.templateCmb.currentData()
        template = self._templates.getImageNamingTemplate(key)
        # self._editedTemplate = template
        self.templateTextEdit.setTemplate(template)

    @QtCore.pyqtSlot(str)
    def _updateExample(self, _text: str):
        templateKey = self.templateCmb.currentData()

        if templateKey == NEW_TEMPLATE:
            print(NEW_TEMPLATE)
        elif templateKey == DELETE_ALL_TEMPLATES:
            print(DELETE_ALL_TEMPLATES)
        else:
            self.downloader.setImageNamingTemplate(templateKey)
            name = self.downloader.renameImage(self.downloader.imageSample)
            self.example.setText(name)

    @property
    def templateName(self) -> str:
        return self.templateCmb.currentText()

    @property
    def record(self) -> Tuple[str, str]:
        return self.scope, self.name

    @property
    def isValid(self) -> bool:
        return self.nameText.isValid()

    @QtCore.pyqtSlot()
    def checkName(self):
        self.nameText.forceUpperCase()
        self.enableButtons(self.isValid)

    def setCompleterModel(self, words):
        self.completer.setModel(QtCore.QStringListModel(words))

    def editEntry(self, scope: str, name: str):
        self.scopeCmb.setCurrentText(scope)
        self.nameText.setPlainText(name)

        cursor = QtGui.QTextCursor(self.nameText.document())
        cursor.movePosition(QtGui.QTextCursor.End)
        self.nameText.setTextCursor(cursor)

        self.setEditMode(True)
        self.enableButtons(self.isValid)

    def reset(self):
        self.scopeCmb.setCurrentText(dt.DcfsDataScope.LOCAL.name)
        self.nameText.clear()
        self.setEditMode(False)
        self.enableButtons(self.isValid)


class TokenSelectorList(QtWidgets.QScrollArea):

    tokenSelected = QtCore.pyqtSignal(Token)   #

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWidgetResizable(True)
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding
        )
        sizePolicy.setVerticalStretch(10)
        self.setSizePolicy(sizePolicy)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        areaWidget = QtWidgets.QWidget()
        areaWidget.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
            )
        )
        areaWidget.setLayout(self.layout)

        self.setWidget(areaWidget)

    def addTokenGroup(self, tokenGroup: "TokenGroup"):
        self.layout.addWidget(tokenGroup)
        tokenGroup.tokenSelected.connect(self.tokenSelected)


class TokenGroup(QtWidgets.QGroupBox):

    tokenSelected = QtCore.pyqtSignal(Token)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)

        self.setTitle(title)
        self.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed
            )
        )
        self.setFlat(True)

        self.layout = QtWidgets.QVBoxLayout()

        self.setLayout(self.layout)

    def addTokenSelector(self, tokenSelector: "TokenSelector"):
        self.layout.addWidget(tokenSelector)
        tokenSelector.tokenSelected.connect(self.tokenSelected)


class TokenSelector(QtWidgets.QWidget):

    tokenSelected = QtCore.pyqtSignal(Token)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.colorLbl = QtWidgets.QLabel(' ')
        size = QtGui.QFontMetrics(QtGui.QFont()).height()
        self.colorLbl.setFixedSize(QtCore.QSize(size, size))

        self.tokenCmb = tokenCmb = EditorComboBox()

        insertBtn = QtWidgets.QPushButton('Insert')
        insertBtn.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
            )
        )

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.colorLbl)
        layout.addWidget(tokenCmb)
        layout.addWidget(insertBtn)

        self.setLayout(layout)

        tokenCmb.activated.connect(self.selectToken)
        insertBtn.clicked.connect(self.selectToken)

    def setColor(self, color: str):
        self.colorLbl.setStyleSheet(f'QLabel {{background-color: {color};}}')

    def insertItem(self, index: int, text: str, userData: "Token"):
        self.tokenCmb.insertItem(index, text, userData)

    def selectToken(self):
        self.tokenSelected.emit(self.tokenCmb.currentData())


class TokenSelectorBuilder(Visitor):

    def visitTokenTree(self, tokenTree: "TokenTree"):
        tokenListView = TokenSelectorList()

        for tokenNode in tokenTree.children:
            tokenGroup = tokenNode.accept(self)
            tokenListView.addTokenGroup(tokenGroup)

        return tokenListView

    def visitTokenFamily(self, tokenFamily: "TokenFamily") -> QtWidgets.QGroupBox:
        tokenGroup = TokenGroup(tokenFamily.name)

        color = TOKEN_COLORS[tokenFamily.name]
        for tokenNode in tokenFamily.children:
            tokenSelector = tokenNode.accept(self)
            tokenSelector.setColor(color)
            tokenGroup.addTokenSelector(tokenSelector)

        return tokenGroup

    def visitTokenGenus(self, tokenGenus: "TokenGenus") -> TokenSelector:
        tokenSelector = TokenSelector()
        for index, tokenNode in enumerate(tokenGenus.children):
            item = tokenNode.accept(self)
            tokenSelector.insertItem(index, *item)
        return tokenSelector

    @staticmethod
    def visitToken(token: Token) -> Tuple[str, Token]:
        return token.name, token
