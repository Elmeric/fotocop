from typing import Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui


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
