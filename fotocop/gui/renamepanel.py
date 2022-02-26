from typing import TYPE_CHECKING

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models.naming import Case, TemplateType
from .nameseditor import ImageNamingTemplateEditor

if TYPE_CHECKING:
    from fotocop.models.downloader import Downloader

EDIT_TEMPLATE = "Custom..."

MediumGray = '#5d5b59'

ThumbnailBackgroundName = MediumGray


class RenameWidget(QtUtil.QFramedWidget):

    def __init__(self, downloader: "Downloader", parent: QtWidgets.QWidget = None):
        super().__init__(parent)

        self._downloader = downloader

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

        self.extensionCmb.addItem(Case.ORIGINAL_CASE.value, Case.ORIGINAL_CASE)
        self.extensionCmb.addItem(Case.UPPERCASE.value, Case.UPPERCASE)
        self.extensionCmb.addItem(Case.LOWERCASE.value, Case.LOWERCASE)

        self.templateCmb.currentIndexChanged.connect(self.selectTemplate)
        self.extensionCmb.currentIndexChanged.connect(self.selectExtension)

        # Initialize the template combo box entries.
        self._updateTemplateCmb()

    @property
    def sampleName(self) -> str:
        return self.exampleLbl.text()

    @sampleName.setter
    def sampleName(self, name: str):
        self.exampleLbl.setText(name)

    @QtCore.pyqtSlot(str)
    def showImageNamingTemplate(self, key: str) -> None:
        index = self.templateCmb.findData(key, QtCore.Qt.UserRole)
        if index > 0:
            with QtCore.QSignalBlocker(self.templateCmb):
                self.templateCmb.setCurrentIndex(index)

    @QtCore.pyqtSlot(Case)
    def showImageNamingExtension(self, extension: Case) -> None:
        index = self.extensionCmb.findData(extension, QtCore.Qt.UserRole)
        if index > 0:
            with QtCore.QSignalBlocker(self.extensionCmb):
                self.extensionCmb.setCurrentIndex(index)

    @QtCore.pyqtSlot(int)
    def selectTemplate(self, _index: int):
        currentKey = self._downloader.imageNamingTemplate.key
        selectedKey = self.templateCmb.currentData()

        if selectedKey == EDIT_TEMPLATE:
            # The user wants to edit the template's list.
            dialog = ImageNamingTemplateEditor(self._downloader, TemplateType.IMAGE, parent=self)
            dialog.editTemplate(currentKey)

            if dialog.exec():
                selectedKey = dialog.templateKey
            else:
                selectedKey = currentKey

            # Regardless of whether the user clicked OK or cancel, refresh the template
            # combo box entries and select the bew template if any, the first one otherwise.
            self._updateTemplateCmb()

        self._downloader.setNamingTemplate(TemplateType.IMAGE, selectedKey)

    @QtCore.pyqtSlot(int)
    def selectExtension(self, _index: int):
        extensionKind = self.extensionCmb.currentData()
        self._downloader.setExtension(extensionKind)

    def _updateTemplateCmb(self):
        downloader = self._downloader

        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()

            builtins = downloader.listBuiltinNamingTemplates(TemplateType.IMAGE)
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)
            self.templateCmb.insertSeparator(len(builtins))

            customs = downloader.listCustomNamingTemplates(TemplateType.IMAGE)
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.addItem(EDIT_TEMPLATE, EDIT_TEMPLATE)


class RenamePanel(QtWidgets.QScrollArea):
    """Panel where image naming template is selected.

    It is a pure graphical UI entity. All its functionalities are handled by its
    RenameWidget instance.
    """

    imageNamingTemplateSelected = QtUtil.QtSignalAdapter(str)
    imageNamingExtensionSelected = QtUtil.QtSignalAdapter(Case)

    def __init__(self, downloader: "Downloader",  parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        # self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        imageRenamePanel = QtUtil.QPanelView(
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

        self.imageNamingTemplateSelected.connect(self.imageRenameWidget.showImageNamingTemplate)
        self.imageNamingExtensionSelected.connect(self.imageRenameWidget.showImageNamingExtension)

    def updateImageSample(self, name: str, _path: str) -> None:
        self.imageRenameWidget.sampleName = name
