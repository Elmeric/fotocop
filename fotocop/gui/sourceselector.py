from typing import TYPE_CHECKING
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.util.collapsiblewidget import CollapsibleWidget
from fotocop.models import settings as Config
from fotocop.models.sources import SourceType, DriveType, Selection

if TYPE_CHECKING:
    from fotocop.models.sources import SourceManager


class SourceSelector(QtWidgets.QWidget):
    def __init__(self, sourceManager: "SourceManager", parent=None):
        super().__init__(parent)

        self.sourceManager = sourceManager

        resources = Config.fotocopSettings.resources

        iconSize = QtCore.QSize(24, 24)
        refreshIcon = QtGui.QIcon(f"{resources}/reload.png")
        refreshTip = "Refresh devices and files source lists"

        self.sourcePix = QtWidgets.QLabel()
        self.sourcePix.setPixmap(
            QtGui.QPixmap(f"{resources}/double-down.png").scaledToHeight(
                48, QtCore.Qt.SmoothTransformation
            )
        )
        self.sourceLbl = QtWidgets.QLabel("Select a source")
        self.sourceLbl.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.sourceLbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.sourceLbl.setFixedWidth(350)
        self.sourceLbl.setText("Select a source")
        self.sourceLbl.setToolTip("")

        deviceLbl = QtWidgets.QLabel("DEVICES")
        deviceLbl.setMaximumHeight(24)
        refreshDevBtn = QtWidgets.QPushButton(refreshIcon, "")
        refreshDevBtn.setIconSize(iconSize)
        refreshDevBtn.setToolTip(refreshTip)
        refreshDevBtn.setFlat(True)
        self.ejectChk = QtWidgets.QCheckBox("Eject after copy")
        self.ejectChk.setChecked(False)
        self.ejectChk.stateChanged.connect(self.onEjectSelection)
        self.noDeviceLbl = QtWidgets.QLabel("Insert a device and refresh list")
        self.devicesLst = QtWidgets.QListWidget()
        self.devicesLst.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.devicesLst.setItemDelegate(QtUtil.NoFocusDelegate(self.devicesLst))
        self.devicesLst.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.devicesLst.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.devicesLst.setFrameShape(QtWidgets.QFrame.NoFrame)

        diskLbl = QtWidgets.QLabel("FILES")
        refreshFileBtn = QtWidgets.QPushButton(refreshIcon, "")
        refreshFileBtn.setIconSize(iconSize)
        refreshFileBtn.setToolTip(refreshTip)
        refreshFileBtn.setFlat(True)
        self.subDirsChk = QtWidgets.QCheckBox("Include sub folders")
        self.subDirsChk.setChecked(False)
        self.subDirsChk.stateChanged.connect(self.onSubDirsSelection)
        self.fsModel = QtWidgets.QFileSystemModel()
        self.fsModel.setRootPath("")
        self.fsModel.setOption(QtWidgets.QFileSystemModel.DontUseCustomDirectoryIcons)
        self.fsModel.setOption(QtWidgets.QFileSystemModel.DontWatchForChanges)
        self.fsModel.setFilter(QtCore.QDir.NoDotAndDotDot | QtCore.QDir.AllDirs)
        self.diskHeaders = dict()

        srcLayout = QtWidgets.QHBoxLayout()
        srcLayout.addWidget(self.sourcePix, 0, QtCore.Qt.AlignCenter)
        srcLayout.addWidget(self.sourceLbl, 0, QtCore.Qt.AlignCenter)
        srcLayout.addStretch()

        devHLayout = QtWidgets.QHBoxLayout()
        devHLayout.setSpacing(15)
        devHLayout.addWidget(refreshDevBtn)
        devHLayout.addWidget(deviceLbl)
        devHLayout.addStretch()
        devHLayout.addWidget(self.ejectChk)

        devLayout = QtWidgets.QVBoxLayout()
        devLayout.setContentsMargins(5, 0, 5, 5)
        devLayout.addWidget(self.noDeviceLbl)
        devLayout.addWidget(self.devicesLst)

        devVLayout = QtWidgets.QVBoxLayout()
        devVLayout.addLayout(devHLayout)
        devVLayout.addLayout(devLayout)

        fileLayout = QtWidgets.QHBoxLayout()
        fileLayout.setSpacing(15)
        fileLayout.addWidget(refreshFileBtn)
        fileLayout.addWidget(diskLbl)
        fileLayout.addStretch()
        fileLayout.addWidget(self.subDirsChk)

        self.diskLayout = QtWidgets.QVBoxLayout()
        self.diskLayout.setContentsMargins(0, 0, 0, 0)
        self.diskLayout.setSpacing(0)
        self.diskLayout.addLayout(fileLayout)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(srcLayout)
        layout.addLayout(devVLayout)
        layout.addLayout(self.diskLayout)
        layout.addStretch()

        self.setLayout(layout)

        refreshDevBtn.clicked.connect(self.refreshSources)
        refreshFileBtn.clicked.connect(self.refreshSources)
        self.devicesLst.selectionModel().selectionChanged.connect(
            self.onDeviceSelection
        )

        QtCore.QTimer.singleShot(50, self.refreshSources)

    @QtCore.pyqtSlot()
    def refreshSources(self):
        resources = Config.fotocopSettings.resources
        manager = self.sourceManager

        manager.enumerateSources()

        noDevice = True
        self.devicesLst.clear()
        for row, device in enumerate(manager.getDevices()):
            noDevice = False
            icon = QtGui.QIcon(f"{resources}/device.png")
            item = QtWidgets.QListWidgetItem(icon, device.caption)
            item.setToolTip(device.name)
            item.setData(QtCore.Qt.UserRole, device)
            self.devicesLst.addItem(item)
            if row == 0:
                self.devicesLst.setCurrentRow(row)
                self.devicesLst.setFocus()

        # https://stackoverflow.com/questions/6337589/qlistwidget-adjust-size-to-content
        self.devicesLst.setFixedHeight(
            self.devicesLst.sizeHintForRow(0) * self.devicesLst.count()
            + 2 * self.devicesLst.frameWidth()
        )

        self.devicesLst.setVisible(not noDevice)
        self.noDeviceLbl.setVisible(noDevice)

        for header, tree in self.diskHeaders.values():
            tree.clearSelection()
            self.diskLayout.removeWidget(header)
            del header
        self.diskHeaders.clear()
        for drive in manager.getDrives():
            driveId = drive.id
            header = CollapsibleWidget(title=drive.caption, isCollapsed=True)
            tree = QtWidgets.QTreeView()
            tree.setModel(self.fsModel)
            tree.setRootIndex(self.fsModel.index(f"{driveId}\\\\"))
            tree.setAnimated(False)
            tree.setIndentation(10)
            tree.setSortingEnabled(False)
            tree.header().hide()
            for i in range(1, self.fsModel.columnCount()):
                tree.hideColumn(i)
            tree.collapseAll()
            tree.selectionModel().selectionChanged.connect(
                lambda selected, unselected, d=driveId: self.onFileSelection(
                    selected, unselected, d
                )
            )
            header.addWidget(tree)
            self.diskHeaders[driveId] = header, tree

        for header, _ in self.diskHeaders.values():
            self.diskLayout.addWidget(header)

    @QtCore.pyqtSlot(QtCore.QItemSelection, QtCore.QItemSelection)
    def onDeviceSelection(
        self, selected: QtCore.QItemSelection, _deselected: QtCore.QItemSelection
    ):
        if not selected.indexes():
            # Clear any selected device by selecting an unknown device
            self.sourceManager.selectDevice("NOTHING")
            return

        # Deselect any selected drive
        for _, tree in self.diskHeaders.values():
            tree.selectionModel().clearSelection()

        # Select the new device
        index = selected.indexes()[0]
        model = index.model()
        device = model.data(index, QtCore.Qt.UserRole)
        self.sourceManager.selectDevice(device.name, self.ejectChk.isChecked())

    @QtCore.pyqtSlot(int)
    def onSubDirsSelection(self, _state: int):
        self.sourceManager.setDriveSubDirsState(self.subDirsChk.isChecked())

    @QtCore.pyqtSlot(int)
    def onEjectSelection(self, _state: int):
        self.sourceManager.setDeviceEjectState(self.ejectChk.isChecked())

    def onFileSelection(
        self,
        selected: QtCore.QItemSelection,
        _deselected: QtCore.QItemSelection,
        selectedDrive: str,
    ):
        if not selected.indexes():
            # Clear any selected drive by selecting an unknown drive
            self.sourceManager.selectDrive("NOTHING", Path())
            return

        # Deselect device and any other selected drive
        self.devicesLst.selectionModel().clearSelection()
        for driveId, (_, tree) in self.diskHeaders.items():
            if driveId != selectedDrive:
                tree.selectionModel().clearSelection()

        # Select the new drive
        index = selected.indexes()[0]
        model = index.model()
        path = Path(model.filePath(index))
        self.sourceManager.selectDrive(selectedDrive, path, self.subDirsChk.isChecked())

    @QtCore.pyqtSlot(Selection)
    def onSourceSelected(self, selection: Selection):
        resources = Config.fotocopSettings.resources

        source = selection.source
        kind = selection.kind

        if kind == SourceType.DEVICE:
            caption = source.caption
            self.sourcePix.setPixmap(
                QtGui.QPixmap(f"{resources}/device.png").scaledToHeight(
                    48, QtCore.Qt.SmoothTransformation
                )
            )
            self._setElidedText(self.sourceLbl, f"FROM {caption}\nAll pictures")
            self.sourceLbl.setToolTip(f"Device: {caption}")

        elif kind == SourceType.DRIVE:
            driveKind = source.kind
            if driveKind == DriveType.LOCAL:
                icon = "drive.png"
            elif driveKind == DriveType.NETWORK:
                icon = "network-drive.png"
            elif driveKind == DriveType.CD:
                icon = "CD.png"
            else:
                icon = "device.png"
            self.sourcePix.setPixmap(
                QtGui.QPixmap(f"{resources}/{icon}").scaledToHeight(
                    48, QtCore.Qt.SmoothTransformation
                )
            )
            caption = source.caption
            path = source.selectedPath.as_posix()
            sourcePath = path[3:].replace("/", " / ")
            subDirs = source.subDirs
            self._setElidedText(self.sourceLbl, f"FROM {caption}\n{sourcePath}{' +' if subDirs else ''}")
            self.sourceLbl.setToolTip(
                f"Drive: {caption}\nPath: {path}"
                f"{' (including subfolders)' if subDirs else ''}"
            )

        else:
            self.sourcePix.setPixmap(
                QtGui.QPixmap(f"{resources}/double-down.png").scaledToHeight(
                    48, QtCore.Qt.SmoothTransformation
                )
            )
            self.sourceLbl.setText("Select a source")
            self.sourceLbl.setToolTip("")

    @staticmethod
    def _setElidedText(label: QtWidgets.QLabel, text: str):
        fm = label.fontMetrics()
        width = label.width() - 2
        elidedText = fm.elidedText(text, QtCore.Qt.ElideMiddle, width)
        label.setText(elidedText)
