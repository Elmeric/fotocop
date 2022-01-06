import webbrowser
from typing import TYPE_CHECKING, Optional, Tuple

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.util.basicpatterns import Visitor
from fotocop.models.naming import BuiltinTokens, ROOT_TOKENS_NODE, Token

if TYPE_CHECKING:
    from fotocop.models.naming import NamingTemplates, TokenNode, TokenTree

NEW_TEMPLATE = "Save New Custom Preset..."
DELETE_ALL_TEMPLATES = "Remove All Custom Presets..."


class EditorComboBox(QtWidgets.QComboBox):
    """Regular QComboBox that ignores the mouse wheel.

    Leave the wheel event to scroll its parent scrollable widget.
    """

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        event.ignore()


class NamingTemplateEditor(QtWidgets.QDialog):
    def __init__(self, fixedSize=True, parent=None):
        super().__init__(parent)

        # Prevent resizing the view when required.
        # if fixedSize:
        #     self.setWindowFlags(
        #         QtCore.Qt.Dialog |
        #         QtCore.Qt.MSWindowsFixedSizeDialogHint
        #     )

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
    def __init__(self, templates: "NamingTemplates", parent=None):
        super().__init__(parent=parent)

        self.templates = templates

        templateLbl = QtWidgets.QLabel('Preset:')
        self.templateCmb = QtWidgets.QComboBox()
        self.exampleLbl = QtWidgets.QLabel("Example:")
        self.example = QtWidgets.QLabel()
        self.templateEditor = QtWidgets.QTextEdit()

        glayout = QtWidgets.QGridLayout()
        glayout.addWidget(templateLbl, 0, 0)
        glayout.addWidget(self.templateCmb, 0, 1)
        glayout.addWidget(self.exampleLbl, 1, 0)
        glayout.addWidget(self.example, 1, 1)
        glayout.setColumnStretch(1, 10)

        layout = QtWidgets.QVBoxLayout()
        self.setLayout(layout)

        layout.addLayout(glayout)
        layout.addSpacing(int(QtGui.QFontMetrics(QtGui.QFont()).height() / 2))
        layout.addWidget(self.templateEditor)
        # layout.addWidget(self.messageWidget)

        self.area = ROOT_TOKENS_NODE.accept(TokenSelectorBuilder())
        self.area.tokenSelected.connect(self.insertToken)
        layout.addWidget(self.area)

        layout.addWidget(self.buttonBox)

        self.show()
        self.updateTemplateCmb()
        self.setWidgetSizes()
        #
        # self.highlighter = QtUtil.PatternHighlighter(QtCore.QRegularExpression(r'(\<\w+\>)'), self.nameText.document())
        # self.setEditMode(False)
        # self.enableButtons(self.isValid)
        # self.nameText.setFocus()

    def updateTemplateCmb(self):
        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()

            builtins = self.templates.listBuiltinImageNamingTemplates()
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.insertSeparator(len(builtins))

            customs = self.templates.listImageNamingTemplates()
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.addItem(NEW_TEMPLATE, NEW_TEMPLATE)
            self.templateCmb.addItem(DELETE_ALL_TEMPLATES, DELETE_ALL_TEMPLATES)

    def setWidgetSizes(self) -> None:
        """
        Resize widgets for enhanced visual layout
        """

        # Set the widths of the comboboxes and labels to the width of the
        # longest control
        # width = max(widget.width() for widget in self.widget_mapper.values())
        # for widget in self.widget_mapper.values():
        #     widget.setMinimumWidth(width)

        # Set the scroll area to be big enough to eliminate the horizontal scrollbar
        scrollbar_width = self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent)
        self.area.setMinimumWidth(self.area.widget().width() + scrollbar_width)

    @QtCore.pyqtSlot(str, Token)
    def insertToken(self, title: str, token: Token):
        print(title, token.name)

    @property
    def templateName(self) -> str:
        return "By date and time (YYYYMMDD-HHMMSS)"

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

    tokenSelected = QtCore.pyqtSignal(str, Token)

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

    tokenSelected = QtCore.pyqtSignal(str, Token)

    TOKEN_COLORS = {
        "Date time": "#7a9c00",
        "Filename": "#7a9c38",
        "Sequences": "#7a9c76",
        "Session": "#7a9cb4",
    }

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

    def addTokens(self, tokenNode):
        color = self.TOKEN_COLORS[tokenNode.title]
        if tokenNode.isLeaf:
            tokenSelector = TokenSelector(color, tokenNode.title, tokenNode.tokens)
            self.layout.addWidget(tokenSelector)
            tokenSelector.tokenSelected.connect(self.tokenSelected)
        else:
            for row, tokenChild in enumerate(tokenNode.children):
                assert tokenChild.isLeaf
                tokenSelector = TokenSelector(color, tokenChild.title, tokenChild.tokens)
                self.layout.addWidget(tokenSelector)
                tokenSelector.tokenSelected.connect(self.tokenSelected)


class TokenSelector(QtWidgets.QWidget):

    tokenSelected = QtCore.pyqtSignal(str, Token)

    def __init__(self, color: str, title: str, tokens: Tuple[Token], parent=None):
        super().__init__(parent)

        self.widget_mapper = dict()

        colorLbl = QtWidgets.QLabel(' ')
        colorLbl.setStyleSheet(f'QLabel {{background-color: {color};}}')
        size = QtGui.QFontMetrics(QtGui.QFont()).height()
        colorLbl.setFixedSize(QtCore.QSize(size, size))

        tokenCmb = EditorComboBox()
        self.widget_mapper[title] = tokenCmb

        insertBtn = QtWidgets.QPushButton('Insert')
        insertBtn.setSizePolicy(
            QtWidgets.QSizePolicy(
                QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
            )
        )

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(colorLbl)
        layout.addWidget(tokenCmb)
        layout.addWidget(insertBtn)

        self.setLayout(layout)

        for token in tokens:
            tokenCmb.addItem(f"{title} ({token.name})", token)
        tokenCmb.activated.connect(
            lambda _, t=title: self.insertToken(t)
        )
        insertBtn.clicked.connect(
            lambda _, t=title: self.insertToken(t)
        )

    def insertToken(self, title:str):
        tokenCmb = self.widget_mapper[title]
        self.tokenSelected.emit(tokenCmb.currentText(), tokenCmb.currentData())


class TokenSelectorBuilder(Visitor):

    def visitTokenTree(self, tokenTree: "TokenTree"):
        tokenListView = TokenSelectorList()

        for tokenNode in tokenTree.children:
            tokenGroup = tokenNode.accept(self)
            tokenListView.addTokenGroup(tokenGroup)

        return tokenListView

    def visitTokenNode(self, tokenNode: "TokenNode") -> QtWidgets.QGroupBox:
        tokenGroup = TokenGroup(tokenNode.title)
        # tokenGroup = TokenGroup(tokenNode.title, self.widget_mapper, self.insertToken)
        tokenGroup.addTokens(tokenNode)

        return tokenGroup
