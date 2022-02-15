from typing import TYPE_CHECKING
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config
from .fileexplorer import FileSystemView

if TYPE_CHECKING:
    from fotocop.models.downloader import Downloader
    from fotocop.gui.fileexplorer import FileSystemModel, FileSystemDelegate, FileSystemFilter

MediumGray = '#5d5b59'

ThumbnailBackgroundName = MediumGray


class DestinationWidget(QtUtil.QFramedWidget):

    templateSelected = QtCore.pyqtSignal(str)
    extensionSelected = QtCore.pyqtSignal(str)

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
        self._fsModel = fsModel
        self._fsFilter = fsFilter
        self._fsDelegate = fsDelegate
        self._initCompleted = False

        resources = Config.fotocopSettings.resources

        self._selectedTemplateKey = None

        self.setBackgroundRole(QtGui.QPalette.Background)
        self.setAutoFillBackground(True)
        # self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        self.destinationPix = QtWidgets.QLabel()
        self.destinationPix.setPixmap(
            QtGui.QPixmap(f"{resources}/image-folder.png").scaledToHeight(
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
        self.destBrowser.header().hide()
        for i in range(1, fsModel.columnCount()):
            self.destBrowser.hideColumn(i)
        self.destBrowser.collapseAll()

        dstLayout = QtWidgets.QHBoxLayout()
        dstLayout.setContentsMargins(9, 0, 9, 0)
        dstLayout.addWidget(self.destinationPix, 0, QtCore.Qt.AlignCenter)
        dstLayout.addWidget(self.destinationLbl, 0, QtCore.Qt.AlignCenter)
        dstLayout.addStretch()

        presetLayout = QtWidgets.QHBoxLayout()
        presetLayout.setContentsMargins(9, 0, 9, 0)
        presetLayout.addWidget(QtWidgets.QLabel("Preset:"), 0, QtCore.Qt.AlignCenter)
        presetLayout.addWidget(self.templateCmb, 0, QtCore.Qt.AlignCenter)
        presetLayout.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 0, 1, 1)
        layout.addLayout(dstLayout)
        layout.addLayout(presetLayout)
        layout.addWidget(self.destBrowser)

        self.setLayout(layout)

        # self.templateCmb.currentIndexChanged.connect(self.selectTemplate)
        # self.extensionCmb.currentIndexChanged.connect(self.selectExtension)
        self.destBrowser.selectionModel().selectionChanged.connect(self.onFolderSelection)

        # Initialize the template combo box entries and select the first one.
        # self._updateTemplateCmb()
        self.templateCmb.setCurrentIndex(0)

    @QtCore.pyqtSlot(Path)
    def showSelectedDestination(self, path: Path)-> None:
        def scrollTo(p):
            print(p)
            idx = self._fsModel.index(p)
            pIdx = self.destBrowser.model().mapFromSource(idx)
            self.destBrowser.scrollTo(pIdx, QtWidgets.QAbstractItemView.EnsureVisible)

        print(f"Show selected destination: {path}{', INIT' if not self._initCompleted else ''}")
        path = path.as_posix()

        self.destinationLbl.setText(path)

        proxyIndex = self.destBrowser.model().mapFromSource(self._fsModel.index(path))
        self.destBrowser.setExpanded(proxyIndex, True)
        with QtCore.QSignalBlocker(self.destBrowser.selectionModel()):
            self.destBrowser.setCurrentIndex(proxyIndex)
        # First scrollTo to force directory loading.
        self.destBrowser.scrollTo(proxyIndex, QtWidgets.QAbstractItemView.EnsureVisible)

        if not self._initCompleted:
            # Schedule a second scrollTo, delay adjusted to let the directory being loaded.
            self._initCompleted = True
            QtCore.QTimer.singleShot(
                750,
                lambda p=path: scrollTo(p)
            )

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
        model = proxy.sourceModel()
        proxyIndex = selected.indexes()[0]
        index = proxy.mapToSource(proxyIndex)
        path = model.filePath(index)
        self._downloader.selectDestination(Path(path))


class DestinationPanel(QtWidgets.QScrollArea):
    """Panel where destination is selected.

    It is a pure graphical UI entity. All its functionalities are handled by its
    DestinationWidget instance.
    """

    destinationSelected = QtCore.pyqtSignal(Path)

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
        self.destinationWidget.templateSelected.connect(downloader.setImageNamingTemplate)
        self.destinationWidget.extensionSelected.connect(downloader.setExtension)
