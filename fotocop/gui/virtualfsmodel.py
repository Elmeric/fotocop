from typing import Optional, Tuple, List, Any, Iterable
from pathlib import Path
from enum import IntEnum

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config
from fotocop.gui.fileexplorer import FileSystemDelegate

VirtualFolderOrNone = Optional["_VirtualFolderItem"]


class _VirtualFolderItem:
    """A single "virtual" folder node in the folders tree.

    It is assumed that the node's data with index 0 is the folder name (str) and index
    1 is the folder path (Path) relatively to the root folder of the tree.
    """

    _data: List[Any]
    _parent: "_VirtualFolderItem"
    children: List["_VirtualFolderItem"]

    def __init__(self, data: List[Any], parent: VirtualFolderOrNone = None) -> None:
        self._data = data
        self._parent = parent
        self.children = list()

    def child(self, row: int) -> VirtualFolderOrNone:
        try:
            return self.children[row]
        except IndexError:
            return None

    def childCount(self) -> int:
        return len(self.children)

    def columnCount(self) -> int:
        return len(self._data)

    def data(self, column: int) -> Any:
        try:
            return self._data[column]
        except IndexError:
            return None

    def setData(self, column: int, value: Any) -> bool:
        if column < 0 or column >= len(self._data):
            return False

        self._data[column] = value
        return True

    def folderName(self) -> str:
        try:
            return self._data[0]
        except IndexError:
            return ""

    def folderPath(self) -> Path:
        try:
            return Path(self._data[1])
        except IndexError:
            return Path("")

    def row(self) -> int:
        if self._parent is not None:
            return self._parent.children.index(self)

        return 0

    def parent(self) -> VirtualFolderOrNone:
        return self._parent


class VirtualFolderTreeModel(QtCore.QAbstractItemModel):
    _rootPath: Path
    _rootItem: _VirtualFolderItem
    _newFolderIcon: QtGui.QIcon
    _existingFolderIcon: QtGui.QIcon

    class UserRoles(IntEnum):
        FolderIconRole = QtCore.Qt.DecorationRole
        FolderPathRole = QtCore.Qt.UserRole + 1
        FolderNameRole = QtCore.Qt.UserRole + 2
        PreviewRole = QtCore.Qt.UserRole + 4

    def __init__(
        self, folders: Iterable[str] = None, rootPath: Path = None, parent=None
    ) -> None:
        super().__init__(parent)

        self._rootPath = rootPath or Path("NO_ROOT_PATH")
        self._rootItem = _VirtualFolderItem(["Folder name", "Path from root"])

        resources = Config.fotocopSettings.resources
        self._newFolderIcon = QtUtil.scaledIcon(f"{resources}/blue-folder.png")
        self._existingFolderIcon = QtUtil.scaledIcon(
            f"{resources}/dark-blue-folder.png"
        )

        if folders is not None:
            self.setFolders(folders)
        else:
            self._setRootFolder()

    def rootPath(self) -> Path:
        return self._rootPath

    def setRootPath(self, rootPath: Path) -> None:
        self.layoutAboutToBeChanged.emit()  # noqa

        self._rootPath = rootPath
        self.setData(self.index(0, 0, QtCore.QModelIndex()), rootPath.as_posix())
        self.setData(self.index(0, 1, QtCore.QModelIndex()), "")

        self.layoutChanged.emit()  # noqa

    def rootFolder(self) -> VirtualFolderOrNone:
        return self._rootItem.child(0)

    def setFolders(self, folders: Iterable[str]) -> None:
        self.beginResetModel()

        self._setRootFolder()
        self._setupModelData(folders)

        self.endResetModel()

    def folderIcon(self, index: QtCore.QModelIndex) -> QtGui.QIcon:
        return self.data(index, VirtualFolderTreeModel.UserRoles.FolderIconRole)

    def folderName(self, index: QtCore.QModelIndex) -> str:
        return self.data(index, VirtualFolderTreeModel.UserRoles.FolderNameRole)

    def folderPath(self, index: QtCore.QModelIndex) -> Path:
        return self.data(index, VirtualFolderTreeModel.UserRoles.FolderPathRole)

    def getItem(self, index: QtCore.QModelIndex) -> _VirtualFolderItem:
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item

        return self._rootItem

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.NoItemFlags  # noqa

        return super().flags(index)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        parentItem = self.getItem(parent)

        return parentItem.childCount()

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return self._rootItem.columnCount()

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.DisplayRole,
    ) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._rootItem.data(section)

        return None

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        item: _VirtualFolderItem = self.getItem(index)

        if role == QtCore.Qt.DisplayRole:
            return str(item.data(index.column()))

        if (
            index.column() == 0
            and role == VirtualFolderTreeModel.UserRoles.FolderIconRole
        ):
            absPath = self._rootPath / item.folderPath()
            if absPath.exists():
                return self._existingFolderIcon
            return self._newFolderIcon

        if role == VirtualFolderTreeModel.UserRoles.PreviewRole:
            absPath = self._rootPath / item.folderPath()
            return not absPath.exists()

        if role == VirtualFolderTreeModel.UserRoles.FolderNameRole:
            return item.folderName()

        if role == VirtualFolderTreeModel.UserRoles.FolderPathRole:
            return item.folderPath()

        return None

    def setData(
        self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole
    ) -> bool:
        if role != QtCore.Qt.EditRole:
            return False

        item = self.getItem(index)
        result = item.setData(index.column(), value)

        if result:
            self.dataChanged.emit(index, index)

        return result

    def index(
        self, row: int, column: int, parent: QtCore.QModelIndex = QtCore.QModelIndex()
    ) -> QtCore.QModelIndex:
        if parent.isValid() and parent.column() != 0:
            return QtCore.QModelIndex()

        parentItem = self.getItem(parent)
        childItem = parentItem.child(row)

        if childItem:
            return self.createIndex(row, column, childItem)

        return QtCore.QModelIndex()

    def parent(self, index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem: _VirtualFolderItem = index.internalPointer()
        parentItem = childItem.parent()

        if parentItem == self._rootItem:
            return QtCore.QModelIndex()

        return self.createIndex(parentItem.row(), 0, parentItem)

    def _setRootFolder(self) -> None:
        root = self._rootItem
        root.children = [_VirtualFolderItem([self._rootPath.as_posix(), ""], root)]

    def _setupModelData(self, folders: Iterable[str]) -> None:
        def _addToTree(_parts: Tuple[str], _parent: _VirtualFolderItem) -> None:
            itemName, *otherParts = _parts
            for child in _parent.children:
                if itemName == child.data(0):
                    # child already exists in tree
                    _item = child
                    break
            else:
                # New child
                _item = _VirtualFolderItem(
                    [itemName, _parent.folderPath() / itemName], _parent
                )
                _parent.children.append(_item)

            if otherParts:
                _addToTree(otherParts, _item)

        for path in folders:
            parts = Path(path).relative_to(self._rootPath).parts
            _addToTree(parts, self.rootFolder())


class _SortProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def lessThan(self, left: QtCore.QModelIndex, right: QtCore.QModelIndex) -> bool:
        """Perform sorting comparison."""
        leftData = left.data(QtCore.Qt.DisplayRole)
        rightData = right.data(QtCore.Qt.DisplayRole)

        return leftData < rightData


class VirtualFolderTreeView(QtWidgets.QTreeView):
    def __init__(
        self, folders: Iterable[str] = None, rootPath: Path = None, parent=None
    ) -> None:
        super().__init__(parent)

        self._fileSystemModel = VirtualFolderTreeModel(folders, rootPath, self)

        sortModel = _SortProxyModel()
        sortModel.setSourceModel(self._fileSystemModel)
        self.setModel(sortModel)

        self.setItemDelegate(FileSystemDelegate())

        self.setHeaderHidden(True)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.MinimumExpanding
        )

        self.setStyleSheet("VirtualFolderTreeView {border: none;}")
        self.setAnimated(False)
        self.setIndentation(10)
        self.setSortingEnabled(False)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerItem)

        for i in range(1, self._fileSystemModel.columnCount()):
            self.hideColumn(i)
        self.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.expandAll()

    def setRootPath(self, rootPath: Path) -> None:
        self._fileSystemModel.setRootPath(rootPath)

    def setFolders(self, folders: Iterable[str]) -> None:
        self._fileSystemModel.setFolders(folders)
        self.expandAll()


# class Widget(QtWidgets.QWidget):
#     def __init__(self, parent=None, **kwargs):
#         super().__init__(parent, **kwargs)
#
#         # rootPath = Path("F:/Users/Images/Mes Photos/Négatifs")
#         # folders = [
#         #     "F:/Users/Images/Mes Photos/Négatifs/2007/2007-07/2007-07-31-NO_SESSION",
#         #     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-06/2021-06-27-NO_SESSION",
#         #     "F:/Users/Images/Mes Photos/Négatifs/2003/2003-02/2003-02-14-NO_SESSION",
#         #     "F:/Users/Images/Mes Photos/Négatifs/2003/2003-02/2003-02-19-NO_SESSION",
#         #     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-03/2021-03-20-NO_SESSION",
#         #     "F:/Users/Images/Mes Photos/Négatifs/2018/2018-08/2018-08-26-NO_SESSION",
#         #     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-04/2021-04-16-Portets",
#         # ]
#
#         self._treeView = VirtualFolderTreeView()
#         # self._treeView = VirtualFolderTreeView(folders, rootPath, self)
#
#         testBtn = QtWidgets.QPushButton("Test...")
#         self._test = 0
#
#         layout = QtWidgets.QVBoxLayout(self)
#         layout.addWidget(testBtn)
#         layout.addWidget(self._treeView)
#
#         testBtn.clicked.connect(self.test)
#
#     def test(self):
#         self._test += 1
#         if self._test == 1:
#             self._treeView.setRootPath(Path("F:/Users/Images"))
#         elif self._test == 2:
#             self._treeView.setFolders(
#                 [
#                     "F:/Users/Images/Mes Photos/Négatifs/2007/2007-07/2007-07-31-Test",
#                     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-06/2021-06-27-Test",
#                     "F:/Users/Images/Mes Photos/Négatifs/2003/2003-02/2003-02-14-Test",
#                     "F:/Users/Images/Mes Photos/Négatifs/2003/2003-02/2003-02-19-Test",
#                     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-03/2021-03-20-Test",
#                     "F:/Users/Images/Mes Photos/Négatifs/2018/2018-08/2018-08-26-Test",
#                     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-04/2021-04-16-Portets",
#                 ]
#             )
#         elif self._test == 3:
#             self._treeView.setRootPath(Path("F:/Users/Images/Mes Photos/Négatifs"))
#             self._treeView.setFolders(
#                 [
#                     "F:/Users/Images/Mes Photos/Négatifs/2007/2007-07/2007-07-31-NO_SESSION",
#                     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-06/2021-06-27-NO_SESSION",
#                     "F:/Users/Images/Mes Photos/Négatifs/2003/2003-02/2003-02-14-NO_SESSION",
#                     "F:/Users/Images/Mes Photos/Négatifs/2003/2003-02/2003-02-19-NO_SESSION",
#                     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-03/2021-03-20-NO_SESSION",
#                     "F:/Users/Images/Mes Photos/Négatifs/2018/2018-08/2018-08-26-NO_SESSION",
#                     "F:/Users/Images/Mes Photos/Négatifs/2021/2021-04/2021-04-16-Portets",
#                 ]
#             )
#         else:
#             self._test = 0
#             self._treeView.setRootPath(Path("Select a destination"))
#             self._treeView.setFolders([])
#
#
# if __name__ == "__main__":
#     from sys import argv, exit
#     from PyQt5.QtWidgets import QApplication
#
#     a = QApplication(argv)
#     w = Widget()
#     w.show()
#     exit(a.exec())
