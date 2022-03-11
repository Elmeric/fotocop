from typing import TYPE_CHECKING, Iterable
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config
from fotocop.models.naming import TemplateType
from .fileexplorer import FileSystemView
from .virtualfsmodel import VirtualFolderTreeView
from .nameseditor import ImageNamingTemplateEditor

if TYPE_CHECKING:
    from fotocop.models.downloader import Downloader
    from fotocop.gui.fileexplorer import FileSystemModel, FileSystemDelegate, FileSystemFilter

EDIT_TEMPLATE = "Custom..."

MediumGray = '#5d5b59'

ThumbnailBackgroundName = MediumGray


class DestinationWidget(QtUtil.QFramedWidget):

    destBrowser: "FileSystemView"

    def __init__(
            self,
            downloader: "Downloader",
            fsModel: "FileSystemModel",
            fsFilter: "FileSystemFilter",
            fsDelegate: "FileSystemDelegate",
            parent: QtWidgets.QWidget = None
    ) -> None:
        super().__init__(parent)

        self._downloader = downloader
        self._delayedScrollTo = True

        resources = Config.fotocopSettings.resources

        self.setBackgroundRole(QtGui.QPalette.Background)
        self.setAutoFillBackground(True)
        # self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        self.destinationPix = QtWidgets.QLabel()
        self.destinationPix.setPixmap(
            QtGui.QPixmap(f"{resources}/blue-image-folder.png").scaledToHeight(
                48, QtCore.Qt.SmoothTransformation
            )
        )
        self.destinationLbl = QtWidgets.QLabel("Select destination")
        self.templateCmb = QtWidgets.QComboBox()

        self.destBrowser = FileSystemView(fsModel)
        self.destBrowser.setObjectName("destBrowser")
        self.destBrowser.setModel(fsFilter)
        self.destBrowser.setRootIndex(fsFilter.mapFromSource(fsModel.index(fsModel.myComputer())))
        self.destBrowser.setItemDelegate(fsDelegate)
        self.destBrowser.setStyleSheet('FileSystemView#destBrowser {border: none;}')
        self.destBrowser.setAnimated(False)
        self.destBrowser.setIndentation(10)
        self.destBrowser.setSortingEnabled(False)
        self.destBrowser.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)
        for i in range(1, fsModel.columnCount()):
            self.destBrowser.hideColumn(i)
        self.destBrowser.collapseAll()

        self.previewer = VirtualFolderTreeView()
        self.previewBtn = QtWidgets.QPushButton("Preview")
        self.previewBtn.setCheckable(True)

        self.destStack = QtWidgets.QStackedWidget()
        self.destStack.addWidget(self.destBrowser)
        self.destStack.addWidget(self.previewer)

        dstLayout = QtWidgets.QHBoxLayout()
        dstLayout.setContentsMargins(9, 0, 9, 0)
        dstLayout.addWidget(self.destinationPix, 0, QtCore.Qt.AlignCenter)
        dstLayout.addWidget(self.destinationLbl, 0, QtCore.Qt.AlignCenter)
        dstLayout.addStretch()

        presetLayout = QtWidgets.QHBoxLayout()
        presetLayout.setContentsMargins(9, 0, 9, 0)
        presetLayout.addWidget(QtWidgets.QLabel("Preset:    "), 0, QtCore.Qt.AlignCenter)
        presetLayout.addWidget(self.templateCmb, 0, QtCore.Qt.AlignCenter)
        presetLayout.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 0, 1, 1)
        layout.addLayout(dstLayout)
        layout.addLayout(presetLayout)
        layout.addWidget(self.previewBtn)
        layout.addWidget(self.destStack)

        self.setLayout(layout)

        self.templateCmb.currentIndexChanged.connect(self.selectTemplate)
        self.destBrowser.selectionModel().selectionChanged.connect(self.onFolderSelection)
        self.previewBtn.toggled.connect(self.previewToggle)

        # Initialize the template combo box entries.
        self._updateTemplateCmb()

    @QtCore.pyqtSlot(bool)
    def previewToggle(self, checked: bool) -> None:
        self.destStack.setCurrentIndex(1 if checked else 0)

    @QtCore.pyqtSlot(Path)
    def showSelectedDestination(self, path: Path) -> None:
        def scrollTo(p):
            print(p)
            dBrowser = self.destBrowser
            m = destBrowser.model().sourceModel()  # type: FileSystemModel
            pIdx = dBrowser.model().mapFromSource(m.index(p))
            dBrowser.scrollTo(pIdx, QtWidgets.QAbstractItemView.EnsureVisible)

        print(f"Show selected destination: {path}{', INIT' if self._delayedScrollTo else ''}")
        path = path.as_posix()

        self.destinationLbl.setText(path)

        self.previewer.setRootPath(Path(path))

        destBrowser = self.destBrowser
        model = destBrowser.model().sourceModel()   # type: FileSystemModel
        proxyIndex = destBrowser.model().mapFromSource(model.index(path))
        destBrowser.setExpanded(proxyIndex, True)
        with QtCore.QSignalBlocker(destBrowser.selectionModel()):
            destBrowser.setCurrentIndex(proxyIndex)
        # First scrollTo to force directory loading.
        destBrowser.scrollTo(proxyIndex, QtWidgets.QAbstractItemView.EnsureVisible)

        if self._delayedScrollTo:
            # Schedule a second scrollTo, delay adjusted to let the directory being loaded.
            QtCore.QTimer.singleShot(750, lambda p=path: scrollTo(p))
            self._delayedScrollTo = False

    @QtCore.pyqtSlot(QtCore.QItemSelection, QtCore.QItemSelection)
    def onFolderSelection(
        self, selected: QtCore.QItemSelection, _deselected: QtCore.QItemSelection
    ):
        if not selected.indexes():
            # No destination selected: keep the previous one
            self.showSelectedDestination(self._downloader.destination)
            return

        # Select the new destination
        proxy = self.destBrowser.model()
        index = proxy.mapToSource(selected.indexes()[0])
        self._downloader.selectDestination(Path(proxy.sourceModel().filePath(index)))

    @QtCore.pyqtSlot(str)
    def showDestinationNamingTemplate(self, key: str) -> None:
        index = self.templateCmb.findData(key, QtCore.Qt.UserRole)
        if index > 0:
            with QtCore.QSignalBlocker(self.templateCmb):
                self.templateCmb.setCurrentIndex(index)

    @QtCore.pyqtSlot(int)
    def selectTemplate(self, _index: int):
        currentKey = self._downloader.destinationNamingTemplate.key
        selectedKey = self.templateCmb.currentData()

        if selectedKey == EDIT_TEMPLATE:
            # The user wants to edit the template's list.
            dialog = ImageNamingTemplateEditor(self._downloader, TemplateType.DESTINATION, parent=self)
            dialog.editTemplate(currentKey)

            if dialog.exec():
                selectedKey = dialog.templateKey
            else:
                selectedKey = currentKey

            # Regardless of whether the user clicked OK or cancel, refresh the template
            # combo box entries and select the bew template if any, the first one otherwise.
            self._updateTemplateCmb()

        self._downloader.setNamingTemplate(TemplateType.DESTINATION, selectedKey)

    @QtCore.pyqtSlot(set)
    def updateFolderPreview(self, folders: Iterable[str]) -> None:
        self.previewer.setFolders(folders)

    def _updateTemplateCmb(self):
        downloader = self._downloader

        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()

            builtins = downloader.listBuiltinNamingTemplates(TemplateType.DESTINATION)
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)
            self.templateCmb.insertSeparator(len(builtins))

            customs = downloader.listCustomNamingTemplates(TemplateType.DESTINATION)
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)

            self.templateCmb.addItem(EDIT_TEMPLATE, EDIT_TEMPLATE)


class DestinationPanel(QtWidgets.QScrollArea):
    """Panel where destination is selected.

    It is a pure graphical UI entity. All its functionalities are handled by its
    DestinationWidget instance.
    """

    destinationSelected = QtCore.pyqtSignal(Path)
    destinationNamingTemplateSelected = QtCore.pyqtSignal(str)
    folderPreviewChanged = QtUtil.QtSignalAdapter(set)

    def __init__(
            self,
            downloader: "Downloader",
            fsModel: "FileSystemModel",
            fsFilter: "FileSystemFilter",
            fsDelegate: "FileSystemDelegate",
            parent: QtWidgets.QWidget
    ) -> None:
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        destinationPanel = QtUtil.QPanelView(
            label='Destination', headerColor=QtGui.QColor(ThumbnailBackgroundName),
            headerFontColor=QtGui.QColor(QtCore.Qt.white)
        )
        self.destinationWidget = DestinationWidget(
            downloader=downloader,
            fsModel=fsModel,
            fsFilter=fsFilter,
            fsDelegate=fsDelegate,
            parent=self
        )
        destinationPanel.addWidget(self.destinationWidget)

        # b = QtWidgets.QPushButton("B")
        # imageRenamePanel.addHeaderWidget(b)

        widget = QtWidgets.QWidget()
        widget.setMinimumHeight(640)
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(destinationPanel)
        widget.setLayout(layout)
        self.setWidget(widget)

        self.destinationSelected.connect(self.destinationWidget.showSelectedDestination)
        self.destinationNamingTemplateSelected.connect(self.destinationWidget.showDestinationNamingTemplate)
        self.folderPreviewChanged.connect(self.destinationWidget.updateFolderPreview)
