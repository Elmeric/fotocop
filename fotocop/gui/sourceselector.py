from typing import TYPE_CHECKING, Tuple, List
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config
from fotocop.models.sources import SourceType, DriveType, Selection
from.fileexplorer import FileSystemView

if TYPE_CHECKING:
    from fotocop.models.sources import SourceManager, Device, LogicalDisk, Source
    from .fileexplorer import FileSystemModel, FileSystemFilter, FileSystemDelegate


class SourceSelector(QtWidgets.QWidget):

    DRIVE_ICON = {
        DriveType.LOCAL: "drive.png",
        DriveType.NETWORK: "network-drive.png",
        DriveType.CD: "CD.png",
        DriveType.REMOVABLE: "device.png",
    }

    def __init__(
            self,
            sourceManager: "SourceManager",
            fsModel: "FileSystemModel",
            fsFilter: "FileSystemFilter",
            fsDelegate: "FileSystemDelegate",
            parent=None
    ) -> None:
        super().__init__(parent)

        self._sourceManager = sourceManager
        self._fsModel = fsModel
        self._fsFilter = fsFilter
        self._fsDelegate = fsDelegate
        self._delayedScrollTo = 1250
        self._diskHeaders = dict()   # Container for 'disk' collapsibleWidgets

        resources = Config.fotocopSettings.resources

        iconSize = QtCore.QSize(24, 24)
        refreshIcon = QtGui.QIcon(f"{resources}/reload.png")
        refreshTip = "Refresh devices and files source lists"

        # self.sourcePix = QtWidgets.QLabel()
        # self.sourceLbl = QtWidgets.QLabel()
        # self.sourceLbl.setFrameShape(QtWidgets.QFrame.NoFrame)
        # self.sourceLbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        # self.sourceLbl.setFixedWidth(350)

        deviceLbl = QtWidgets.QLabel("DEVICES")
        deviceLbl.setMaximumHeight(32)
        refreshDevBtn = QtWidgets.QPushButton(refreshIcon, "")
        refreshDevBtn.setIconSize(iconSize)
        refreshDevBtn.setToolTip(refreshTip)
        refreshDevBtn.setStatusTip(refreshTip)
        refreshDevBtn.setFlat(True)
        self.ejectChk = QtWidgets.QCheckBox("Eject after copy")
        self.noDeviceLbl = QtWidgets.QLabel("  Insert a device and refresh list")
        self.noDeviceLbl.setMinimumHeight(36)
        self.devicesLst = QtWidgets.QListWidget()
        self.devicesLst.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.devicesLst.setItemDelegate(QtUtil.NoFocusDelegate(self.devicesLst))
        self.devicesLst.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.devicesLst.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        diskLbl = QtWidgets.QLabel("MY COMPUTER")
        diskLbl.setMaximumHeight(32)
        refreshFileBtn = QtWidgets.QPushButton(refreshIcon, "")
        refreshFileBtn.setIconSize(iconSize)
        refreshFileBtn.setToolTip(refreshTip)
        refreshFileBtn.setStatusTip(refreshTip)
        refreshFileBtn.setFlat(True)
        self.subDirsChk = QtWidgets.QCheckBox("Include sub folders")

        # srcLayout = QtWidgets.QHBoxLayout()
        # srcLayout.addWidget(self.sourcePix, 0, QtCore.Qt.AlignCenter)
        # srcLayout.addWidget(self.sourceLbl, 0, QtCore.Qt.AlignCenter)
        # srcLayout.addStretch()

        devHeader = QtWidgets.QWidget()
        headerColor = QtGui.QColor('#5d5b59')
        headerFontColor = QtGui.QColor(QtCore.Qt.white)
        headerStyle = f"""QWidget {{ background-color: {headerColor.name()}; color: {headerFontColor.name()};}}"""
        devHeader.setStyleSheet(headerStyle)
        devHeader.setMinimumWidth(350)
        devHeader.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        devHLayout = QtWidgets.QHBoxLayout()
        devHLayout.setContentsMargins(0, 0, 0, 0)
        devHLayout.setSpacing(5)
        devHLayout.addWidget(refreshDevBtn)
        devHLayout.addWidget(deviceLbl)
        devHLayout.addStretch()
        devHLayout.addWidget(self.ejectChk)
        devHeader.setLayout(devHLayout)

        devWidget = QtWidgets.QWidget()
        devWidget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        devLayout = QtWidgets.QVBoxLayout()
        devLayout.setContentsMargins(0, 0, 0, 0)
        devLayout.addWidget(self.noDeviceLbl)
        devLayout.addWidget(self.devicesLst)
        devWidget.setLayout(devLayout)

        devVLayout = QtWidgets.QVBoxLayout()
        devVLayout.setContentsMargins(0, 0, 0, 0)
        devVLayout.setSpacing(0)
        devVLayout.addWidget(devHeader)
        devVLayout.addWidget(devWidget)

        fileHeader = QtWidgets.QWidget()
        fileHeader.setStyleSheet(headerStyle)
        fileHeader.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        fileLayout = QtWidgets.QHBoxLayout()
        fileLayout.setContentsMargins(0, 0, 0, 0)
        fileLayout.setSpacing(5)
        fileLayout.addWidget(refreshFileBtn)
        fileLayout.addWidget(diskLbl)
        fileLayout.addStretch()
        fileLayout.addWidget(self.subDirsChk)
        fileHeader.setLayout(fileLayout)

        self.diskLayout = QtWidgets.QVBoxLayout()
        self.diskLayout.setContentsMargins(0, 0, 0, 0)
        self.diskLayout.setSpacing(0)
        self.diskLayout.addStretch()

        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setFrameShape(QtWidgets.QFrame.NoFrame)
        scrollArea.setWidgetResizable(True)
        scrollArea.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.MinimumExpanding)

        diskWidget = QtUtil.QFramedWidget()
        diskWidget.setLayout(self.diskLayout)
        scrollArea.setWidget(diskWidget)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # layout.addLayout(srcLayout)
        layout.addLayout(devVLayout)
        layout.addWidget(fileHeader)
        layout.addWidget(scrollArea)

        self.setLayout(layout)

        self.ejectChk.setChecked(False)
        self.subDirsChk.setChecked(False)

        self.ejectChk.stateChanged.connect(self.onEjectSelection)
        self.subDirsChk.stateChanged.connect(self.onSubDirsSelection)
        refreshDevBtn.clicked.connect(lambda: self.displaySources(enumerateFirst=True))
        refreshFileBtn.clicked.connect(lambda: self.displaySources(enumerateFirst=True))
        self.devicesLst.selectionModel().selectionChanged.connect(
            self.onDeviceSelection
        )

    @QtCore.pyqtSlot()
    def displaySources(self, enumerateFirst: bool = False):
        manager = self._sourceManager

        # Get the source manager current selection
        selection = manager.selection
        sourceKind = selection.kind
        source = selection.source

        # Get the sources from the manager, after new enumeration if required.
        devices, logicalDisks = manager.getSources(enumerateFirst)

        # Display devices, selecting the previous selection if still exists.
        self._displayDevices(devices, prevSource=(sourceKind, source))

        # Display logicalDisks, selecting the previous selection if still exists.
        self._displayLogicalDisks(logicalDisks, prevSource=(sourceKind, source))

    @QtCore.pyqtSlot(QtCore.QItemSelection, QtCore.QItemSelection)
    def onDeviceSelection(
        self, selected: QtCore.QItemSelection, _deselected: QtCore.QItemSelection
    ):
        manager = self._sourceManager

        if not selected.indexes():
            # No device selected: clear any selected one by selecting an unknown device
            manager.selectDevice("NOTHING")
            return

        # A device is selected: retrieve it.
        index = selected.indexes()[0]
        model = index.model()
        device = model.data(index, QtCore.Qt.UserRole)

        selection = manager.selection
        source = selection.source
        sourceKind = selection.kind
        if source is not None and sourceKind == SourceType.DEVICE and device.name == source.name:
            # this device is already the selected one: nothing to do.
            return

        # A new device is selected: deselect any selected drive
        for _, tree in self._diskHeaders.values():
            with QtCore.QSignalBlocker(tree.selectionModel()):
                tree.selectionModel().clearSelection()

        # Select the new device
        manager.selectDevice(device.name, self.ejectChk.isChecked())

    @QtCore.pyqtSlot(int)
    def onSubDirsSelection(self, _state: int):
        self._sourceManager.setDriveSubDirsState(self.subDirsChk.isChecked())

    @QtCore.pyqtSlot(int)
    def onEjectSelection(self, _state: int):
        self._sourceManager.setDeviceEjectState(self.ejectChk.isChecked())

    def onFolderSelection(
        self,
        selected: QtCore.QItemSelection,
        _deselected: QtCore.QItemSelection,
        selectedDrive: str,
    ):
        manager = self._sourceManager

        if not selected.indexes():
            # No drive/folder selected: clear any selected drive by selecting an unknown drive
            manager.selectDrive("NOTHING", Path())
            return

        # A drive/folder is selected: retrieve its path.
        proxyIndex = selected.indexes()[0]
        proxy = proxyIndex.model()
        path = Path(proxy.sourceModel().filePath(proxy.mapToSource(proxyIndex)))

        selection = manager.selection
        source = selection.source
        sourceKind = selection.kind
        if source is not None and sourceKind == SourceType.DRIVE and path == source.selectedPath:
            # this drive/folder is already the selected one: nothing to do.
            return

        # A new drive/folder is selected: deselect device and any other selected drive.
        with QtCore.QSignalBlocker(self.devicesLst.selectionModel()):
            self.devicesLst.selectionModel().clearSelection()
        for driveId, (_, tree) in self._diskHeaders.items():
            if driveId != selectedDrive:
                with QtCore.QSignalBlocker(tree.selectionModel()):
                    tree.selectionModel().clearSelection()

        # Select the new drive and folder
        manager.selectDrive(selectedDrive, path, self.subDirsChk.isChecked())

    @QtCore.pyqtSlot(Selection)
    def displaySelectedSource(self, selection: Selection) -> None:
        """Update the sourceSelector widgets on source selection.

        Call when the source manager signals that a source is selected. The selected
        source may be a Device or a LogicalDisk object, or unknown (none).

        Args:
            selection: the source manager selection
        """
        def scrollTo(t: FileSystemView, p: str) -> None:
            idx = t.model().mapFromSource(self._fsModel.index(p))
            t.scrollTo(idx, QtWidgets.QAbstractItemView.EnsureVisible)

        # resources = Config.fotocopSettings.resources

        source = selection.source
        kind = selection.kind

        if kind == SourceType.DEVICE:
            caption = source.caption
            # self.sourcePix.setPixmap(
            #     QtGui.QPixmap(f"{resources}/device.png").scaledToHeight(
            #         48, QtCore.Qt.SmoothTransformation
            #     )
            # )
            # self._setElidedText(self.sourceLbl, f"FROM {caption}\nAll pictures")
            # toolTip = f"Device: {caption}"
            # self.sourceLbl.setToolTip(toolTip)
            # self.sourceLbl.setStatusTip(toolTip)

            item = self.devicesLst.findItems(caption, QtCore.Qt.MatchExactly)[0]
            index = self.devicesLst.indexFromItem(item)
            with QtCore.QSignalBlocker(self.devicesLst.selectionModel()):
                self.devicesLst.selectionModel().select(index, QtCore.QItemSelectionModel.ClearAndSelect)

        elif kind == SourceType.DRIVE:
            # icon = SourceSelector.DRIVE_ICON.get(source.kind, "drive.png")
            # self.sourcePix.setPixmap(
            #     QtGui.QPixmap(f"{resources}/{icon}").scaledToHeight(
            #         48, QtCore.Qt.SmoothTransformation
            #     )
            # )
            # caption = source.caption
            path = source.selectedPath
            posixPath = path.as_posix()
            # sourcePath = posixPath[3:].replace("/", " / ")
            subDirs = source.subDirs
            # self._setElidedText(self.sourceLbl, f"FROM {caption}\n{sourcePath}{' +' if subDirs else ''}")
            # toolTip = f"Drive: {caption}\nPath: {posixPath}{' (including subfolders)' if subDirs else ''}"
            # self.sourceLbl.setToolTip(toolTip)
            # self.sourceLbl.setStatusTip(toolTip)

            driveId = source.id
            header, tree = self._diskHeaders[driveId]
            header.expand()
            index = tree.model().mapFromSource(self._fsModel.index(str(path)))
            with QtCore.QSignalBlocker(tree.selectionModel()):
                tree.selectionModel().select(index, QtCore.QItemSelectionModel.ClearAndSelect)
            # with QtCore.QSignalBlocker(tree.selectionModel()):
            #     tree.setCurrentIndex(index)
            with QtCore.QSignalBlocker(self.subDirsChk):
                self.subDirsChk.setChecked(subDirs)
            # First scrollTo to force directory loading.
            tree.scrollTo(index, QtWidgets.QAbstractItemView.EnsureVisible)
            if self._delayedScrollTo:
                # Schedule a second scrollTo, delay adjusted to let the directory being loaded.
                QtCore.QTimer.singleShot(
                    self._delayedScrollTo,
                    lambda t=tree, p=posixPath: scrollTo(t, p)
                )
            tree.setFocus()

        # else:
        #     assert kind == SourceType.UNKNOWN
        #     self.sourcePix.setPixmap(
        #         QtGui.QPixmap(f"{resources}/double-down.png").scaledToHeight(
        #             48, QtCore.Qt.SmoothTransformation
        #         )
        #     )
        #     self.sourceLbl.setText("Select a source")
        #     self.sourceLbl.setToolTip("")
        #     self.sourceLbl.setStatusTip("")

        self._delayedScrollTo = 0

    def _displayDevices(
            self,
            devices: List["Device"],
            prevSource: Tuple[SourceType, "Source"]
    ) -> None:
        sourceKind, source = prevSource

        # Clear the devices list and rebuild it from the source manager data.
        with QtCore.QSignalBlocker(self.devicesLst.selectionModel()):
            self.devicesLst.clear()

        noDevice = True
        for row, device in enumerate(devices):
            noDevice = False
            icon = QtGui.QIcon(f"{Config.fotocopSettings.resources}/device.png")
            item = QtWidgets.QListWidgetItem(icon, device.caption)
            item.setToolTip(device.name)
            item.setStatusTip(device.name)
            item.setData(QtCore.Qt.UserRole, device)
            self.devicesLst.addItem(item)
            # Select this device if it was the current source manager selection.
            if sourceKind == SourceType.DEVICE and source == device:
                index = self.devicesLst.indexFromItem(item)
                self.devicesLst.selectionModel().select(
                    index,
                    QtCore.QItemSelectionModel.ClearAndSelect
                )
                self.devicesLst.setFocus()

        # https://stackoverflow.com/questions/6337589/qlistwidget-adjust-size-to-content
        self.devicesLst.setFixedHeight(
            self.devicesLst.sizeHintForRow(0) * self.devicesLst.count()
            + 2 * self.devicesLst.frameWidth()
        )

        # Show the devices list or a 'no device' label whether a device exists or not.
        self.devicesLst.setVisible(not noDevice)
        self.noDeviceLbl.setVisible(noDevice)

    def _displayLogicalDisks(
            self,
            logicalDisks: List["LogicalDisk"],
            prevSource: Tuple[SourceType, "Source"]
    ) -> None:
        sourceKind, source = prevSource

        # Clear the drive list and rebuild it from the source manager data.
        # Each drive is set in a header collapsible widget and shows the file system
        # model from the drive's root in a tree view.
        for header, tree in self._diskHeaders.values():
            with QtCore.QSignalBlocker(tree.selectionModel()):
                tree.clearSelection()
            self.diskLayout.removeWidget(header)
            del header
        self._diskHeaders.clear()

        selDriveId = None
        for drive in logicalDisks:
            driveId = drive.id
            header = QtUtil.CollapsibleWidget(title=drive.caption, isCollapsed=True)
            tree = FileSystemView(self._fsModel)
            tree.setModel(self._fsFilter)
            tree.setRootIndex(self._fsFilter.mapFromSource(self._fsModel.index(f"{driveId}\\\\")))
            tree.setItemDelegate(self._fsDelegate)
            tree.setAnimated(False)
            tree.setIndentation(10)
            tree.setSortingEnabled(False)
            tree.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)
            tree.header().hide()
            for i in range(1, self._fsModel.columnCount()):
                tree.hideColumn(i)
            tree.collapseAll()
            tree.selectionModel().selectionChanged.connect(
                lambda selected, unselected, d=driveId: self.onFolderSelection(selected, unselected, d)
            )
            header.addWidget(tree)
            self._diskHeaders[driveId] = header, tree
            if sourceKind == SourceType.DRIVE and source == drive:
                selDriveId = driveId

        for header, _ in self._diskHeaders.values():
            self.diskLayout.insertWidget(self.diskLayout.count() - 1, header)

        # Select this drive and path if it is the current source manager selection.
        if selDriveId is not None:
            self._delayedScrollTo = 100
            selHeader, selTree = self._diskHeaders[selDriveId]
            selHeader.expand()
            path = source.selectedPath.as_posix()
            index = selTree.model().mapFromSource(self._fsModel.index(path))
            selTree.selectionModel().select(index, QtCore.QItemSelectionModel.ClearAndSelect)
            selTree.setFocus()

    @staticmethod
    def _setElidedText(label: QtWidgets.QLabel, text: str):
        fm = label.fontMetrics()
        width = label.width() - 2
        elidedText = fm.elidedText(text, QtCore.Qt.ElideMiddle, width)
        label.setText(elidedText)
