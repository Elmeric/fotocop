from typing import TYPE_CHECKING, Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import naming
from .nameseditor import ImageNamingTemplateEditor

if TYPE_CHECKING:
    from fotocop.models.downloader import Downloader

EDIT_TEMPLATE = "Custom..."

MediumGray = '#5d5b59'

ThumbnailBackgroundName = MediumGray


def minPanelWidth() -> int:
    """Minimum width of panels on left and right side of main window.

    Derived from standard font size.

    Returns: size in pixels.
    """

    return int(QtGui.QFontMetrics(QtGui.QFont()).height() * 13.5)


class QPanelView(QtWidgets.QWidget):
    """A header bar with a child widget.
    """

    def __init__(
            self,
            label: str,
            headerColor: Optional[QtGui.QColor] = None,
            headerFontColor: Optional[QtGui.QColor] = None,
            parent: QtWidgets.QWidget = None
    ):

        super().__init__(parent)

        self.header = QtWidgets.QWidget(self)
        if headerColor is not None:
            headerStyle = f"""QWidget {{ background-color: {headerColor.name()}; }}"""
            self.header.setStyleSheet(headerStyle)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        self.label = QtWidgets.QLabel(label.upper())
        if headerFontColor is not None:
            headerFontStyle = f"QLabel {{color: {headerFontColor.name()};}}"
            self.label.setStyleSheet(headerFontStyle)

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(5, 2, 5, 2)
        self.headerLayout.addWidget(self.label)
        self.headerLayout.addStretch()
        self.header.setLayout(self.headerLayout)

        self._headerWidget = None
        self._content = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        self.setLayout(layout)

    def addWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the Panel View.

        Any previous widget will be removed.

        Args:
            widget: widget to add
        """

        if self._content is not None:
            self.layout().removeWidget(self._content)

        self._content = widget

        self.layout().addWidget(self._content)

    def addHeaderWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the header bar, on the right side.

        Any previous widget will be removed.

        Args:
            widget: widget to add
        """
        if self._headerWidget is not None:
            self.headerLayout.removeWidget(self._headerWidget)

        self._headerWidget = widget

        self.headerLayout.addWidget(widget)

    def text(self) -> str:
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text: str) -> None:
        """Set the text of the label."""
        self.label.setText(text)

    def minimumSize(self) -> QtCore.QSize:
        if self._content is None:
            fontHeight = QtGui.QFontMetrics(QtGui.QFont()).height()
            width = minPanelWidth()
            height = fontHeight * 2
        else:
            width = self._content.minimumWidth()
            height = self._content.minimumHeight()

        return QtCore.QSize(width, self.header.height() + height)


class RenameWidget(QtUtil.QFramedWidget):

    templateSelected = QtCore.pyqtSignal(str)
    extensionSelected = QtCore.pyqtSignal(str)

    def __init__(self, downloader: "Downloader", parent: QtWidgets.QWidget = None):
        super().__init__(parent)

        self._downloader = downloader

        self._selectedTemplateKey = None

        self.setBackgroundRole(QtGui.QPalette.Base)
        self.setAutoFillBackground(True)
        # self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

        self.templateCmb = QtWidgets.QComboBox()
        self.extensionCmb = QtWidgets.QComboBox()
        self.exampleLbl = QtWidgets.QLabel("Example")

        layout = QtWidgets.QFormLayout()
        layout.addRow('Preset:', self.templateCmb)
        layout.addRow('Extension:', self.extensionCmb)
        layout.addRow('Example:', self.exampleLbl)
        self.setLayout(layout)

        self.templateCmb.currentIndexChanged.connect(self.selectTemplate)
        self.extensionCmb.currentIndexChanged.connect(self.selectExtension)

        self.extensionCmb.addItem(naming.ORIGINAL_CASE, naming.ORIGINAL_CASE)
        self.extensionCmb.addItem(naming.UPPERCASE, naming.UPPERCASE)
        self.extensionCmb.addItem(naming.LOWERCASE, naming.LOWERCASE)
        self.extensionCmb.setCurrentIndex(2)    # lowercase

        # Initialize the template combo box entries and select the first one.
        self._updateTemplateCmb()
        self.templateCmb.setCurrentIndex(0)

    @property
    def sampleName(self) -> str:
        return self.exampleLbl.text()

    @sampleName.setter
    def sampleName(self, name: str):
        self.exampleLbl.setText(name)

    @QtCore.pyqtSlot(int)
    def selectTemplate(self, _index: int):
        templateKey = self.templateCmb.currentData()

        if templateKey == EDIT_TEMPLATE:
            # The user wants to edit the template's list.
            dialog = ImageNamingTemplateEditor(self._downloader, parent=self)
            dialog.editTemplate(self._selectedTemplateKey)

            templateName = self.templateCmb.itemText(0)
            if dialog.exec():
                templateName = dialog.templateName

            # Regardless of whether the user clicked OK or cancel, refresh the template
            # combo box entries and select the bew template if any, the first one otherwise.
            self._updateTemplateCmb()
            self.templateCmb.setCurrentText(templateName)

        else:
            # The user selected an existing template.
            self._selectedTemplateKey = templateKey
            self.templateSelected.emit(templateKey)

    @QtCore.pyqtSlot(int)
    def selectExtension(self, _index: int):
        extensionKind = self.extensionCmb.currentData()
        self.extensionSelected.emit(extensionKind)

    def _updateTemplateCmb(self):
        downloader = self._downloader

        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()

            builtins = downloader.listBuiltinImageNamingTemplates()
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)
            self.templateCmb.insertSeparator(len(builtins))

            customs = downloader.listCustomImageNamingTemplates()
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.addItem(EDIT_TEMPLATE, EDIT_TEMPLATE)

            self.templateCmb.setCurrentIndex(-1)


class RenamePanel(QtWidgets.QScrollArea):
    """Panel where image naming template is selected.

    It is a pure graphical UI entity. All its functionalities are handled by its
    RenameWidget instance.
    """

    def __init__(self, downloader: "Downloader",  parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        # self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        imageRenamePanel = QPanelView(
            label='Photo Renaming', headerColor=QtGui.QColor(ThumbnailBackgroundName),
            headerFontColor=QtGui.QColor(QtCore.Qt.white)
        )
        self.imageRenameWidget = RenameWidget(
            downloader=downloader,
            parent=self
        )
        imageRenamePanel.addWidget(self.imageRenameWidget)

        # b = QtWidgets.QPushButton("B")
        # imageRenamePanel.addHeaderWidget(b)

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(imageRenamePanel)
        layout.addStretch()
        widget.setLayout(layout)
        self.setWidget(widget)

        self.imageRenameWidget.templateSelected.connect(downloader.setImageNamingTemplate)
        self.imageRenameWidget.extensionSelected.connect(downloader.setExtension)

    def updateImageSample(self, name: str):
        self.imageRenameWidget.sampleName = name
