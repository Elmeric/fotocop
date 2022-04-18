import re
import webbrowser
from typing import TYPE_CHECKING, Optional, Tuple, List, NamedTuple
from enum import Enum, auto
from copy import deepcopy

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Visitor
from fotocop.models.naming import TemplateType, TokensDescription, Token, NamingTemplates

if TYPE_CHECKING:
    from fotocop.models.naming import TokenTree, TokenFamily, TokenGenus, NamingTemplate
    from fotocop.models.downloader import Downloader

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


class TemplateTextEdit(QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.highlighter = TokenHighlighter(self.document())

        self._editedTemplate: Optional["NamingTemplate"] = None
        self._selectedToken: Optional["Token"] = None
        self._heightMin = 0
        self._heightMax = 200

        self.document().documentLayout().documentSizeChanged.connect(           # noqa
            self.wrapHeightToContents
        )

    @property
    def template(self) -> Tuple[Token, ...]:
        if self._editedTemplate is not None:
            return self._editedTemplate.template
        return tuple()

    @QtCore.pyqtSlot()
    def wrapHeightToContents(self):
        """Adjust the text area size to show contents without vertical scrollbar.

        Derived from:
        http://stackoverflow.com/questions/11851020/a-qwidget-like-qtextedit-that-wraps-its-height-
        automatically-to-its-contents/11858803#11858803
        """
        docHeight = self.document().size().height() + 5
        if (
            self._heightMin <= docHeight <= self._heightMax
            and docHeight > self.minimumHeight()
        ):
            self.setMinimumHeight(docHeight)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        super().mousePressEvent(event)

        if event.button() == QtCore.Qt.LeftButton:
            cursor = self.textCursor()
            position = cursor.position()
            cursorNeighborhood = self._tokenAtPos(position)
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
            assert cursorNeighborhood.position == CursorPosition.IN
            token, _, _, _ = cursorNeighborhood.leftToken
            if token.genusName == "Free text":
                self.viewport().setCursor(QtCore.Qt.IBeamCursor)
            else:
                self.viewport().setCursor(QtCore.Qt.PointingHandCursor)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent):
        pass

    def mouseDoubleClickEvent(self, e: QtGui.QMouseEvent):
        pass

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Automatically select tokens when navigating through the document.

        Suppress the return / enter key.

        Args:
            event: the key press event.
        """
        key = event.key()
        ctrl = event.modifiers() & QtCore.Qt.ControlModifier  # noqa
        # shift = event.modifiers() & QtCore.Qt.ShiftModifier  # noqa

        if key in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return, QtCore.Qt.Key_Tab):
            return

        if key == QtCore.Qt.Key_Escape:
            super().keyPressEvent(event)
            return

        if ctrl and key in (
            QtCore.Qt.Key_A,
            QtCore.Qt.Key_C,
            QtCore.Qt.Key_V,
            QtCore.Qt.Key_Z,
            QtCore.Qt.Key_Y,
            QtCore.Qt.Key_X,
        ):
            # TODO: Implement dedicated copy/cut/paste, delete, undo/redo actions
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
                backward = key == QtCore.Qt.Key_Backspace
                if token.genusName == "Free text" and len(token.name) > 1:
                    self._delCarInFreetext(index, position - start, backward)
                    cursor.setPosition(position - 1 if backward else position)
                    self.setTextCursor(cursor)
                else:
                    self._removeToken(index)
                    cursor.setPosition(newPos)
                    self.setTextCursor(cursor)
            return

        if bool(re.match(r"^[a-zA-Z0-9-_/]$", event.text())):
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
                (
                    rightToken,
                    rightIndex,
                    rightStart,
                    rightEnd,
                ) = cursorNeighborhood.rightToken
                if leftToken.genusName == "Free text":
                    self._updateFreetext(event.text(), leftIndex, position - leftStart)
                    cursor.setPosition(position + 1)
                    self.setTextCursor(cursor)
                    return
                elif rightToken.genusName == "Free text":
                    self._updateFreetext(
                        event.text(), rightIndex, position - rightStart
                    )
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

        backward = key in (
            QtCore.Qt.Key_Left,
            QtCore.Qt.Key_Home,
            QtCore.Qt.Key_PageUp,
            QtCore.Qt.Key_Up,
        )
        forward = key in (
            QtCore.Qt.Key_Right,
            QtCore.Qt.Key_End,
            QtCore.Qt.Key_PageDown,
            QtCore.Qt.Key_Down,
        )
        if backward or forward:
            cursorNeighborhood = self._tokenAtPos(position)
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
                TokenFootprint(Token("", "Free text", None), -1, 0, 0),
            )

        previousFootprint = TokenFootprint(Token("", "Free text", None), -1, 0, 0)
        for index, boundary in enumerate(template.boundaries()):
            if position == boundary.start:
                # At start or between two tokens
                return CursorNeighborhood(
                    CursorPosition.BETWEEN,
                    previousFootprint,
                    TokenFootprint(
                        template.template[index], index, position, boundary.end
                    ),
                )
            if boundary.start < position < boundary.end:
                # In a token
                footprint = TokenFootprint(
                    template.template[index], index, boundary.start, boundary.end
                )
                return CursorNeighborhood(CursorPosition.IN, footprint, footprint)
            previousFootprint = TokenFootprint(
                template.template[index], index, boundary.start, boundary.end
            )
        # At end
        return CursorNeighborhood(
            CursorPosition.BETWEEN,
            previousFootprint,
            TokenFootprint(
                Token("", "Free text", None), len(template.template), position, position
            ),
        )

    def setTemplate(self, template: "NamingTemplate"):
        self._editedTemplate = deepcopy(template)
        self.setPlainText(template.asText())
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(cursor)
        self.setFocus()

    def _changeToken(self, action: QtWidgets.QAction, index: int):
        token = NamingTemplates.getToken(action.text())
        tokens = list(self._editedTemplate.template)
        tokens[index] = token
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _removeToken(self, index: int):
        tokens = list(self._editedTemplate.template)
        del tokens[index]
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _updateFreetext(self, text: str, index: int, position: int):
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
            tokens.insert(len(tokens), Token(text, "Free text", None))

        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _delCarInFreetext(self, index: int, position: int, backward: bool):
        tokens = list(self._editedTemplate.template)
        token = tokens[index]
        if backward:
            token.name = token.name[: position - 1] + token.name[position:]
        else:
            token.name = token.name[:position] + token.name[position + 1:]
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    def _insertFreetext(self, text: str, index: int):
        tokens = list(self._editedTemplate.template)
        tokens.insert(index, Token(text, "Free text", None))
        self._editedTemplate.template = tuple(tokens)
        self.setPlainText(self._editedTemplate.asText())

    @QtCore.pyqtSlot(Token)
    def insertToken(self, token: "Token"):
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

        for family in TokensDescription.TOKEN_FAMILIES:
            format_ = QtGui.QTextCharFormat()
            format_.setFontWeight(QtGui.QFont.Bold)
            format_.setForeground(QtGui.QColor(TOKEN_COLORS[family]))
            for genus in TokensDescription.TOKEN_GENUS[family]:
                pattern = QtCore.QRegularExpression(fr"(\<{genus} \([a-zA-Z0-9 ]+\)\>)")
                rule = HighlightingRule(pattern, format_)
                self.highlightingRules.append(rule)

    def highlightBlock(self, text: str):
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
                self.setFormat(
                    match.capturedStart(), match.capturedLength(), rule.format
                )


class NameEditor(QtWidgets.QDialog):
    """Very simple dialog window that allows user entry of new template name.

    Save button is disabled when the current name entered is already in use or is empty.

    Args:
        existingCustomNames: List of existing custom template's names.
    """

    def __init__(self, existingCustomNames: List[str], parent=None):
        super().__init__(parent)

        self.existingCustomNames = existingCustomNames

        self.setModal(True)

        title = "Save New Custom Template - Fotocop"
        self.setWindowTitle(title)

        self.nameEdit = QtWidgets.QLineEdit()
        metrics = QtGui.QFontMetrics(QtGui.QFont())
        self.nameEdit.setMinimumWidth(metrics.width(title))

        buttonBox = QtWidgets.QDialogButtonBox()
        buttonBox.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.saveButton = buttonBox.addButton(QtWidgets.QDialogButtonBox.Save)
        self.saveButton.setEnabled(False)

        flayout = QtWidgets.QFormLayout()
        flayout.addRow("Template Name:", self.nameEdit)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(flayout)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

        self.nameEdit.textEdited.connect(self._nameEdited)
        buttonBox.rejected.connect(self.reject)
        buttonBox.accepted.connect(self.accept)

    @property
    def templateName(self) -> str:
        return self.nameEdit.text()

    @QtCore.pyqtSlot(str)
    def _nameEdited(self, name: str):
        enabled = False
        if len(name) > 0:
            enabled = name not in self.existingCustomNames
        self.saveButton.setEnabled(enabled)


class NamingTemplateEditor(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setModal(True)

        self.buttonBox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok
            | QtWidgets.QDialogButtonBox.Cancel
            | QtWidgets.QDialogButtonBox.Help,
            QtCore.Qt.Horizontal,
            self,
        )
        self.helpButton = self.buttonBox.button(QtWidgets.QDialogButtonBox.Help)
        self.helpButton.setToolTip("Get help online...")

        self.helpButton.clicked.connect(self._helpButtonClicked)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    @staticmethod
    def _helpButtonClicked() -> None:
        location = "#rename"
        webbrowser.open_new_tab(
            "http://www.elmeric.fr/fotocop/documentation/{}".format(location)
        )


class ImageNamingTemplateEditor(NamingTemplateEditor):
    def __init__(self, downloader: "Downloader", kind: "TemplateType", parent=None):
        super().__init__(parent=parent)

        self._downloader = downloader
        self._templateKind = kind

        self._existingTemplateNames = list()
        self._templateSaved = True

        templateLbl = QtWidgets.QLabel("Preset:")
        self.templateCmb = QtWidgets.QComboBox()
        exampleLbl = QtWidgets.QLabel("Example:")
        self.example = QtWidgets.QLabel()
        self.deleteBtn = QtWidgets.QPushButton("Delete")
        self.replaceChk = QtWidgets.QCheckBox("Replace existing template")
        self.saveBtn = QtWidgets.QPushButton("Save As")
        self.templateTextEdit = TemplateTextEdit()
        sizePolicy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        sizePolicy.setVerticalStretch(1)
        self.templateTextEdit.setSizePolicy(sizePolicy)

        glayout = QtWidgets.QGridLayout()
        glayout.addWidget(templateLbl, 0, 0)
        glayout.addWidget(self.templateCmb, 0, 1)
        glayout.addWidget(self.deleteBtn, 0, 2)
        glayout.addWidget(exampleLbl, 1, 0)
        glayout.addWidget(self.example, 1, 1, 1, 2)
        glayout.setColumnStretch(1, 1)

        hlayout = QtWidgets.QHBoxLayout()
        hlayout.addWidget(self.replaceChk)
        hlayout.addWidget(self.saveBtn)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(glayout)
        layout.addSpacing(int(QtGui.QFontMetrics(QtGui.QFont()).height() / 2))
        layout.addWidget(self.templateTextEdit)
        layout.addLayout(hlayout)
        # layout.addWidget(self.messageWidget)

        self.tokenSelectorList = NamingTemplates.tokensRootNode.accept(
            TokenSelectorBuilder(templateKind=kind)
        )
        layout.addWidget(self.tokenSelectorList)

        layout.addWidget(self.buttonBox)

        self.tokenSelectorList.tokenSelected.connect(self.templateTextEdit.insertToken)
        self.templateCmb.activated.connect(self._editTemplate)
        self.deleteBtn.clicked.connect(self._deleteTemplate)
        self.replaceChk.stateChanged.connect(self._setReplace)
        self.saveBtn.clicked.connect(self._saveTemplate)
        self.templateTextEdit.textChanged.connect(self._checkTemplate)
        self._downloader.imageSampleChanged.connect(self._updateSample)
        # self._downloader.destinationSampleChanged.connect(self._updateSample)

        self.show()
        self._updateTemplates(isInit=True)

    @property
    def templateName(self) -> str:
        return self.templateCmb.currentText()

    @property
    def templateKey(self) -> str:
        return self.templateCmb.currentData()

    @property
    def _editedTemplate(self) -> Optional["NamingTemplate"]:
        """Convenient property to retrieve the template in edition.

        It cannot be None as it was existing to be placed in the template combo box and
        the template editor is modal.

        Returns:
            The Namingtemplate object currently selected for edition.
        """
        template = self._downloader.getNamingTemplateByKey(
            self._templateKind,
            self.templateCmb.currentData()
        )
        assert template is not None
        return template

    @property
    def _isDirty(self) -> bool:
        return (
                self.templateTextEdit.toPlainText() != self._editedTemplate.asText()
                or not self._templateSaved
        )

    def editTemplate(self, key: str):
        # Set the template to be edited: retrieve the selected template from its key
        # and select it to update the dialog state.
        template = self._downloader.getNamingTemplateByKey(self._templateKind, key)
        assert template is not None
        self._selectTemplate(template)

    def _updateTemplates(self, isInit: bool = False):
        downloader = self._downloader

        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()
            self._existingTemplateNames.clear()

            builtins = downloader.listBuiltinNamingTemplates(self._templateKind)
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)
                self._existingTemplateNames.append(template.name)

            customs = downloader.listCustomNamingTemplates(self._templateKind)
            if customs:
                self.templateCmb.insertSeparator(len(builtins))
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)
                self._existingTemplateNames.append(template.name)

            self.templateCmb.setCurrentIndex(0)

        self._setWidgetSizes(isInit)

    def _setWidgetSizes(self, isInit: bool):
        """Resize widgets for enhanced visual layout.

        Args:
            isInit: False for succesive calls after first init one to avoid adding
                scrollbar witdh several time.
        """
        # Set the widths of the templates ComboBox to the width of the longest item text.
        width = max(
            QtGui.QFontMetrics(QtGui.QFont()).width(self.templateCmb.itemText(index))
            for index in range(self.templateCmb.count())
        )
        self.templateCmb.setMinimumWidth(width + 30)

        # Set the scroll area to be big enough to eliminate the horizontal scrollbar
        scrollbarWidth = (
            self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
            if isInit
            else 0
        )
        self.tokenSelectorList.setMinimumWidth(
            self.tokenSelectorList.widget().width() + scrollbarWidth
        )

    @QtCore.pyqtSlot()
    def _checkTemplate(self):
        self.saveBtn.setEnabled(self._isDirty)

    @QtCore.pyqtSlot(int)
    def _editTemplate(self, _index: int):
        # The user selects a template in the combo box: retrieve the selected template
        # from its key and select it to update the dialog state.
        key = self.templateCmb.currentData()
        template = self._downloader.getNamingTemplateByKey(self._templateKind, key)
        assert template is not None
        self._selectTemplate(template)

    def _selectTemplate(self, template: "NamingTemplate"):
        # Select the template in the combo box if not already done.
        self.templateCmb.setCurrentText(template.name)

        # Fill the template text edit with it.
        self.templateTextEdit.setTemplate(template)

        # Enable / check deletion and saving widgets according to the template type.
        if template.isBuiltin:
            self.replaceChk.setEnabled(False)
            self.replaceChk.setChecked(False)
            self.deleteBtn.setEnabled(False)
        else:
            self.replaceChk.setEnabled(True)
            self.replaceChk.setChecked(True)
            self.deleteBtn.setEnabled(True)

        # set it as the downloader selected template to allow correct sample name.
        self._downloader.setNamingTemplate(self._templateKind, template.key)

    @QtCore.pyqtSlot(int)
    def _setReplace(self, state: int):
        if state == QtCore.Qt.Checked:
            self.saveBtn.setText("Save")
        else:
            self.saveBtn.setText("Save As")

    def _updateSample(self, name: str, path: str) -> None:
        if self._templateKind == TemplateType.IMAGE:
            self.example.setText(name)
        else:
            assert self._templateKind == TemplateType.DESTINATION
            self.example.setText(path)

    @QtCore.pyqtSlot()
    def _saveTemplate(self):
        template = None
        if not self.replaceChk.isChecked():
            # Save the changed template with a new name (Save As).
            # Query a name for the new template.
            dialog = NameEditor(self._existingTemplateNames, self)
            dialog.nameEdit.setText(self._editedTemplate.name)
            if dialog.exec_():
                templateName = dialog.templateName
                # Command the template creation to the downloader and show command status.
                template = self._downloader.addCustomNamingTemplate(
                    self._templateKind,
                    templateName, self.templateTextEdit.template
                )
        else:
            # Command the template modification to the downloader and show command status.
            template = self._downloader.changeCustomNamingTemplate(
                self._templateKind,
                self.templateCmb.currentData(),
                self.templateTextEdit.template
            )

        # A template has been added or changed: save it and update the template editor.
        if template is not None:
            success, msg = self._downloader.saveCustomNamingTemplates()
            QtUtil.getMainWindow().showStatusMessage(msg, not success)
            self._templateSaved = success
            # Update content of the template combo box.
            self._updateTemplates()
            # Select the new template to update dialog state.
            self._selectTemplate(template)

    @QtCore.pyqtSlot()
    def _deleteTemplate(self):
        # Command the template deletion to the downloader and show command status.
        self._downloader.deleteCustomNamingTemplate(self._templateKind, self.templateCmb.currentData())
        success, msg = self._downloader.saveCustomNamingTemplates()
        QtUtil.getMainWindow().showStatusMessage(msg, not success)
        # Update content of the template combo box.
        self._updateTemplates()
        # Select the first template in the combo box to update dialog state.
        firstTemplate = self._downloader.getNamingTemplateByKey(
            self._templateKind,
            self.templateCmb.itemData(0)
        )
        assert firstTemplate is not None
        self._selectTemplate(firstTemplate)


class TokenSelectorList(QtWidgets.QScrollArea):

    tokenSelected = QtCore.pyqtSignal(Token)  #

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

        self.colorLbl = QtWidgets.QLabel(" ")
        size = QtGui.QFontMetrics(QtGui.QFont()).height()
        self.colorLbl.setFixedSize(QtCore.QSize(size, size))

        self.tokenCmb = tokenCmb = EditorComboBox()

        insertBtn = QtWidgets.QPushButton("Insert")
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

        tokenCmb.activated.connect(self._selectToken)
        insertBtn.clicked.connect(self._selectToken)

    def setColor(self, color: str):
        self.colorLbl.setStyleSheet(f"QLabel {{background-color: {color};}}")

    def insertItem(self, index: int, text: str, userData: "Token"):
        self.tokenCmb.insertItem(index, text, userData)

    def _selectToken(self):
        self.tokenSelected.emit(self.tokenCmb.currentData())


class TokenSelectorBuilder(Visitor):
    def __init__(self, templateKind: TemplateType) -> None:
        self._templateKind = templateKind

    def visitTokenTree(self, tokenTree: "TokenTree"):
        tokenListView = TokenSelectorList()

        for tokenNode in tokenTree.children:
            if tokenNode.isAllowed(self._templateKind):
                tokenGroup = tokenNode.accept(self)
                tokenListView.addTokenGroup(tokenGroup)

        return tokenListView

    def visitTokenFamily(self, tokenFamily: "TokenFamily") -> QtWidgets.QGroupBox:
        tokenGroup = TokenGroup(tokenFamily.name)

        color = TOKEN_COLORS[tokenFamily.name]
        for tokenNode in tokenFamily.children:
            if tokenNode.isAllowed(self._templateKind):
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
    def visitToken(token: "Token") -> Tuple[str, "Token"]:
        return token.name, token
