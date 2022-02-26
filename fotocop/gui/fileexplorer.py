"""Display file system folders for user selection
"""
import os
import pathlib
from typing import List, Set, Optional
import logging
import subprocess

from typing import TYPE_CHECKING
from pathlib import Path
from enum import IntEnum

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config

if TYPE_CHECKING:
    from fotocop.models.downloader import Downloader


class FileSystemModel(QtWidgets.QFileSystemModel):
    """Extend QFileSystemModel to preview images download destination folders.
    """
    class UserRoles(IntEnum):
        PreviewRole = QtCore.Qt.UserRole + 4

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # self.setOption(QtWidgets.QFileSystemModel.DontUseCustomDirectoryIcons)
        # self.setOption(QtWidgets.QFileSystemModel.DontWatchForChanges)
        self.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot )

        self.setRootPath(self.myComputer())

        resources = Config.fotocopSettings.resources
        self.folderIcon = QtUtil.scaledIcon(f"{resources}/blue-folder.png")
        self.destinationFolderIcon = QtUtil.scaledIcon(f"{resources}/dark-blue-folder.png")

        # The next two values are set via FolderPreviewManager.update()
        # They concern provisional folders that will be used if the
        # download proceeds, and all files are downloaded.

        # First value: subfolders we've created to demonstrate to the user
        # where their files will be downloaded to
        self.previewFolders = set()  # type: Set[str]
        self.previewFolders = {"F:/Users/Images/Mes Photos/Négatifs/2021/2021-04"}
        # Second value: subfolders that already existed, but that we still
        # want to indicate to the user where their files will be downloaded to
        self.destinationFolders = set()  # type: Set[str]
        self.destinationFolders = {"F:/Users/Images/Mes Photos/Négatifs/2021/2021-03"}

        # Folders that were actually used to download files into
        self.downloadedFolders = set()  # type: Set[str]
        self.addToDownloadedFolders(
            "F:/Users/Images/Mes Photos/Négatifs/2022/2022-01",
            "F:/Users/Images/Mes Photos/Négatifs"
        )

    def data(self, index: QtCore.QModelIndex, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DecorationRole:
            path = index.data(QtWidgets.QFileSystemModel.FilePathRole)  # type: str
            if path in self.previewFolders or path in self.destinationFolders or path in self.downloadedFolders:
                return self.destinationFolderIcon
            else:
                return self.folderIcon

        if role == FileSystemModel.UserRoles.PreviewRole:
            path = index.data(QtWidgets.QFileSystemModel.FilePathRole)
            return path in self.previewFolders and path not in self.downloadedFolders

        return super().data(index, role)

    def addToDownloadedFolders(self, path: str, destinationFolder: str) -> bool:
        """Add a path to the set of subfolders that indicate where files where
        downloaded.

        :param path: the full path to the folder
        :return: True if the path was not added before, else False
        """

        if path not in self.downloadedFolders:
            self.downloadedFolders.add(path)

            subfolders = Path(path)
            destinationFolder = Path(destinationFolder)

            for subfolder in subfolders.parents:
                if destinationFolder not in subfolder.parents:
                    break
                self.downloadedFolders.add(str(subfolder))
            return True
        return False


class FileSystemView(QtWidgets.QTreeView):
    def __init__(self, model: FileSystemModel, parent=None) -> None:
        super().__init__(parent)

        self._fsModel: FileSystemModel = model
        self._clickedIndex: Optional[QtCore.QModelIndex] = None

        self.setHeaderHidden(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.MinimumExpanding)
        # self.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.MinimumExpanding)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.onCustomContextMenu)
        self.contextMenu = QtWidgets.QMenu()
        self.openInFileBrowserAct = self.contextMenu.addAction("Open in File Browser...")
        self.openInFileBrowserAct.triggered.connect(self.doOpenInFileBrowserAct)

    def goToPath(self, path: str, scrollTo: bool=True) -> None:
        """
        Select the path, expand its subfolders, and scroll to it
        :param path:
        :return:
        """
        if not path:
            return
        # index = self._fsModel.index(path)
        index = self.model().mapFromSource(self._fsModel.index(path))
        self.setExpanded(index, True)
        selection = self.selectionModel()
        selection.select(index, QtCore.QItemSelectionModel.ClearAndSelect|QtCore.QItemSelectionModel.Rows)
        if scrollTo:
            self.scrollTo(index, QtWidgets.QAbstractItemView.PositionAtTop)

    def expandPreviewFolders(self, path: str) -> bool:
        """
        Expand any unexpanded preview folders

        :param path: path under which to expand folders
        :return: True if path was expanded, else False
        """

        self.goToPath(path, scrollTo=True)
        if not path:
            return False

        expanded = False
        for path in self._fsModel.download_subfolders:
            # print('path', path)
            # index = self._fsModel.index(path)
            index = self.model().mapFromSource(self._fsModel.index(path))
            if not self.isExpanded(index):
                self.expand(index)
                expanded = True
        return expanded

    def onCustomContextMenu(self, point: QtCore.QPoint) -> None:
        index = self.indexAt(point)
        if index.isValid():
            self._clickedIndex = index
            self.contextMenu.exec(self.mapToGlobal(point))

    def doOpenInFileBrowserAct(self):
        index = self._clickedIndex
        if index:
            uri = Path(self._fsModel.filePath(index.model().mapToSource(index)))
            args = ["explorer", str(uri)]
            # # logging.debug("Launching: %s", cmd)
            subprocess.run(args)


class FileSystemFilter(QtCore.QSortFilterProxyModel):
    """Filter out the display of RPD's cache and temporary directories, in addition to
    a set of standard directories that should not be displayed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.filtered_dir_names = {
            "$RECYCLE.BIN",
            "System Volume Information",
            "msdownld.tmp",
            "WindowsTEMP"
        }

    def setTempDirs(self, dirs: List[str]) -> None:
        filters = [os.path.basename(path) for path in dirs]
        self.filtered_dir_names = self.filtered_dir_names | set(filters)
        self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QtCore.QModelIndex = None) -> bool:
        index = self.sourceModel().index(sourceRow, 0, sourceParent)  # type: QtCore.QModelIndex
        path = index.data(QtWidgets.QFileSystemModel.FilePathRole)  # type: str

        # if gvfs_gphoto2_path(path):
        #     logging.debug("Rejecting browsing path %s", path)
        #     return False

        if not self.filtered_dir_names:
            return True

        file_name = index.data(QtWidgets.QFileSystemModel.FileNameRole)
        return file_name not in self.filtered_dir_names


class FileSystemDelegate(QtWidgets.QStyledItemDelegate):
    """Italicize provisional download folders that were not already created.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex) -> None:
        if index is None:
            return

        previewFolder = index.data(FileSystemModel.UserRoles.PreviewRole)
        if previewFolder:
            font = QtGui.QFont()
            font.setItalic(True)
            option.font = font

        super().paint(painter, option, index)
