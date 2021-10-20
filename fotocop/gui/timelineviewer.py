from typing import Tuple, Optional, Any

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models import settings as Config
from fotocop.models.timeline import Timeline, TimelineNode, NodeKind
from fotocop.models.sources import Selection


class TimelineModel(QtCore.QAbstractItemModel):
    def __init__(self, timeline: Timeline, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)

        self.rootItem = timeline

    def getItem(self, index: QtCore.QModelIndex) -> TimelineNode:
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item
        return self.rootItem

    def indexOfItem(self, item: TimelineNode) -> QtCore.QModelIndex:
        return self.createIndex(item.childRow(), 0, item)

    def index(
            self,
            row: int,
            column: int,
            parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> QtCore.QModelIndex:

        if parent.isValid() and parent.column() != 0:
            return QtCore.QModelIndex()

        parentItem = self.getItem(parent)
        if not parentItem:
            return QtCore.QModelIndex()

        childItem = parentItem.childAtRow(row)
        if childItem:
            return self.createIndex(row, column, childItem)

        return QtCore.QModelIndex()

    def parent(self, index: QtCore.QModelIndex) -> QtCore.QModelIndex:
        if not index.isValid():
            return QtCore.QModelIndex()

        childItem = self.getItem(index)
        parentItem = childItem.parent if childItem else None

        if not parentItem or parentItem == self.rootItem:
            return QtCore.QModelIndex()

        return self.createIndex(parentItem.childRow(), 0, parentItem)

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        parentItem = self.getItem(parent)
        return parentItem.childCount() if parentItem else 0

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 2

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        item = self.getItem(index)

        if role == QtCore.Qt.FontRole:
            if not item.is_leaf:
                boldFont = QtGui.QFont()
                boldFont.setBold(True)
                return boldFont

        if role == QtCore.Qt.TextAlignmentRole:
            if index.column() == 1:
                return QtCore.Qt.AlignCenter
            return QtCore.Qt.AlignLeft


        # if role == QtCore.Qt.ForegroundRole:
        #     if isinstance(item, A664Link):
        #         color = QtGui.QColor(QtCore.Qt.darkCyan)
        #         return QtGui.QBrush(color)
        #     if isinstance(item, A429Link):
        #         color = QtGui.QColor(QtCore.Qt.darkGreen)
        #         return QtGui.QBrush(color)
        #     if isinstance(item, RamLink):
        #         color = QtGui.QColor('darkslateblue')
        #         return QtGui.QBrush(color)
        #     if isinstance(item, DisLink):
        #         color = QtGui.QColor('darkorange')
        #         return QtGui.QBrush(color)
        #     if isinstance(item, Message):
        #         color = QtGui.QColor('darkviolet')
        #         return QtGui.QBrush(color)
        #     if isinstance(item, Block):
        #         color = QtGui.QColor(QtCore.Qt.darkRed)
        #         return QtGui.QBrush(color)
        #     color = QtGui.QColor(QtCore.Qt.black)
        #     return QtGui.QBrush(color)

        if role == QtCore.Qt.DisplayRole:
            return item.record[index.column()]

        return None

    def headerData(
            self, section: int,
            orientation: QtCore.Qt.Orientation,
            role: int = QtCore.Qt.DisplayRole) -> Optional[Tuple[str, str]]:

        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return 'Date Time', 'Images count'

        return None


class IcdFilterProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # self._linksOnly = False
        self._mediaFilter = NodeKind.MONTH
        # self._dirFilter = dt.DirFilter.ALL
        # self._textFilter = ''
        # self._isTextFilterOn = False
        # self._matchCase = False
    #
    # @property
    # def linksOnly(self) -> bool:
    #     return self._linksOnly
    #
    # @linksOnly.setter
    # def linksOnly(self, value: bool):
    #     self._linksOnly = value
    #     self.invalidateFilter()

    def mediaFilter(self) -> NodeKind:
        return self._mediaFilter

    def setMediaFilter(self, filter_: NodeKind):
        self._mediaFilter = filter_
        self.invalidateFilter()
    #
    # def dirFilter(self) -> dt.DirFilter:
    #     return self._dirFilter
    #
    # def setDirFilter(self, filter_: dt.DirFilter):
    #     self._dirFilter = filter_
    #     self.invalidateFilter()
    #
    # def textFilter(self) -> str:
    #     return self._textFilter
    #
    # def setTextFilter(self, value: str):
    #     self._textFilter = value
    #     self.invalidateFilter()
    #
    # def isTextFilterOn(self) -> bool:
    #     return self._isTextFilterOn
    #
    # def setIsTextFilterOn(self, value: bool):
    #     self._isTextFilterOn = value
    #     self.invalidateFilter()
    #
    # def matchCase(self) -> bool:
    #     return self._matchCase
    #
    # def setMatchCase(self, value: bool):
    #     self._matchCase = value
    #     self.invalidateFilter()
    #
    # def containsText(self, searchText: str, text: str) -> bool:
    #     if not self.matchCase():
    #         searchText = searchText.lower()
    #         text = text.lower()
    #     return searchText in text
    #
    # def recursiveContainsText(
    #         self,
    #         searchText: str,
    #         model,
    #         index: QtCore.QModelIndex) -> bool:
    #     if model.hasChildren(index):
    #         count = model.rowCount(index)
    #         for i in range(count):
    #             if self.recursiveContainsText(searchText, model, model.index(i, 0, index)):
    #                 return True
    #         return False
    #     item = model.getItem(index)                                     # noqa
    #     text = item.pathString
    #     return self.containsText(searchText, text)

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QtCore.QModelIndex) -> bool:
        model = self.sourceModel()
        index = model.index(sourceRow, 0, sourceParent)
        item = model.getItem(index)                                     # noqa

        # if self.isTextFilterOn():
        #     filterText = self.textFilter()
        #     if self._linksOnly:
        #         textOk = self.containsText(filterText, item.id)
        #     else:
        #         textOk = self.recursiveContainsText(filterText, model, index)
        # else:
        #     textOk = True

        # if not isinstance(item, Link):
        #     return not self._linksOnly and textOk

        filter = self._mediaFilter
        kind = item.kind
        if filter is NodeKind.ROOT:
            return True
        if filter is NodeKind.YEAR:
            return kind in (NodeKind.YEAR, NodeKind.MONTH)
        if filter is NodeKind.MONTH:
            return kind in (NodeKind.MONTH, NodeKind.DAY)
        if filter in (NodeKind.DAY, NodeKind.HOUR):
            return kind in (NodeKind.DAY, NodeKind.HOUR)
        # return (
        #     (self._mediaFilter is dt.MediaFilter.ALL or item.media.value == self._mediaFilter.value) and
        #     (self._dirFilter is dt.DirFilter.ALL or item.direction.value == self._dirFilter.value) and
        #     textOk
        # )


class TimelineView(QtWidgets.QWidget):

    selectionChanged = QtCore.pyqtSignal(QtCore.QItemSelection)
    nodeSelected = QtCore.pyqtSignal(TimelineNode)

    def __init__(self, parent=None, timeline: Timeline = None):
        super().__init__(parent)

        self._timeline = None

        resources = Config.fotocopSettings.resources

        self.noTimelineLbl = QtWidgets.QLabel(
            '\nNo timeline:\n'
            '  select a device or an images folder'
        )

        self.timelineTree = QtWidgets.QTreeView()
        self.timelineTree.setAlternatingRowColors(True)
        self.timelineTree.setSelectionBehavior(QtWidgets.QTreeView.SelectRows)
        self.timelineTree.setUniformRowHeights(True)
        self.timelineTree.setExpandsOnDoubleClick(False)
        self.timelineTree.header().hide()
        self.timelineTree.expanded.connect(self.onExpanded)
        self.timelineTree.setSizeAdjustPolicy(
            QtWidgets.QAbstractScrollArea.AdjustToContents
        )
        self.timelineTree.doubleClicked.connect(self.selectNode)

        mediaLbl = QtWidgets.QLabel('Timeline filter')
        self.mediaCmb = QtWidgets.QComboBox()
        self.mediaCmb.setSizeAdjustPolicy(
            QtWidgets.QComboBox.AdjustToContents
        )
        self.mediaCmb.addItems([f.name for f in NodeKind])
        self.mediaCmb.currentTextChanged.connect(
            lambda f: self.timelineTree.model().setMediaFilter(NodeKind[f])
        )

        # dirLbl = QtWidgets.QLabel('Direction filter')
        # self.dirCmb = QtWidgets.QComboBox()
        # self.dirCmb.setSizeAdjustPolicy(
        #     QtWidgets.QComboBox.AdjustToContents
        # )
        # self.dirCmb.addItems([f.name for f in dt.DirFilter])
        # self.dirCmb.currentTextChanged.connect(
        #     lambda f: self.timelineTree.model().setDirFilter(dt.DirFilter[f])
        # )

        # self.textFilter = QtUtil.TextFilterWidget(
        #     QtGui.QIcon(f'{resources}/filter.png'),
        #     QtGui.QIcon(f'{resources}/match-case.png')
        # )
        # self.textFilter.toggled.connect(
        #     lambda isFilterOn: self.timelineTree.model().setIsTextFilterOn(isFilterOn)
        # )
        # self.textFilter.matchCaseToggled.connect(
        #     lambda matchCaseOn: self.timelineTree.model().setMatchCase(matchCaseOn)
        # )
        # self.textFilter.filterTextEdited.connect(
        #     lambda text: self.timelineTree.model().setTextFilter(text)
        # )

        # self.filterToolbar = QtWidgets.QToolBar("Filtering tools")
        # self.filterToolbar.setIconSize(QtCore.QSize(32, 32))
        # self.filterToolbar.addSeparator()
        # self.filterToolbar.addWidget(self.textFilter)
        # self.filterToolbar.addSeparator()

        # self.selNodeBtn = QtWidgets.QPushButton('Select')
        # self.selNodeBtn.clicked.connect(self.onSelectNode)

        gLayout = QtWidgets.QGridLayout()
        gLayout.addWidget(mediaLbl, 0, 0)
        # gLayout.addWidget(dirLbl, 0, 1)
        gLayout.addWidget(self.mediaCmb, 1, 0)
        # gLayout.addWidget(self.dirCmb, 1, 1)
        # gLayout.addWidget(self.filterToolbar, 0, 2, 2, 1)
        # gLayout.addWidget(self.selNodeBtn, 0, 3, 2, 1)
        hLayout = QtWidgets.QHBoxLayout()
        hLayout.addLayout(gLayout)
        hLayout.addStretch()
        vLayout = QtWidgets.QVBoxLayout()
        vLayout.addLayout(hLayout)
        vLayout.addWidget(self.noTimelineLbl)
        vLayout.addWidget(self.timelineTree)
        vLayout.addStretch()

        self.setLayout(vLayout)

        self.setTimeline(timeline)

    @QtCore.pyqtSlot(Selection)
    def onSourceSelected(self, selection):
        # self.timelineTree.model().layoutAboutToBeChanged().emit()
        self.setTimeline(selection.timeline)
        # self.timelineTree.model().layoutChanged.emit()

    @QtCore.pyqtSlot(str)
    def updateTimeline(self, imageKey: str):
        # self.timelineTree.model().layoutAboutToBeChanged().emit()
        self.timelineTree.model().sourceModel().layoutChanged.emit()
        self.timelineTree.expandAll()
        for column in range(self.timelineTree.model().columnCount()):
            self.timelineTree.header().setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeToContents
            )

    def setTimeline(self, timeline: Timeline):
        if timeline:
            self._timeline = timeline
            proxyModel = IcdFilterProxyModel()
            proxyModel.setSourceModel(TimelineModel(timeline))
            self.timelineTree.setModel(proxyModel)
            # self.timelineTree.setModel(TimelineModel(timeline))
            self.timelineTree.setSortingEnabled(False)
            self.timelineTree.selectionModel().selectionChanged.connect(
                self.selectionChanged
            )
            # self.timelineTree.selectionModel().selectionChanged.connect(
            #     self.selNodeBtn.setFocus
            # )

            for column in range(self.timelineTree.model().columnCount()):
                self.timelineTree.header().setSectionResizeMode(
                    column, QtWidgets.QHeaderView.ResizeToContents
                )

            self.noTimelineLbl.hide()
            self.timelineTree.show()
            self.mediaCmb.setEnabled(True)
            # self.dirCmb.setEnabled(True)
            # self.filterToolbar.setEnabled(True)
            # self.selNodeBtn.setEnabled(True)
            # if not self.linksOnly():
            #     self.mediaCmb.setCurrentText(dt.MediaFilter.ALL.name)
            #     self.dirCmb.setCurrentText(dt.DirFilter.ALL.name)
            self.mediaCmb.setCurrentText(NodeKind.MONTH.name)
            # self.textFilter.clear()
        else:
            self._timeline = None
            self.timelineTree.setModel(None)                                 # noqa
            self.noTimelineLbl.show()
            self.timelineTree.hide()
            self.mediaCmb.setEnabled(False)
            # self.dirCmb.setEnabled(False)
            # self.filterToolbar.setEnabled(False)
            # self.selNodeBtn.setEnabled(False)

    # def linksOnly(self) -> bool:
    #     if self.timelineTree.model():
    #         return self.timelineTree.model().linksOnly
    #     return False
    #
    # def setLinksOnly(self, value: bool):
    #     if self.timelineTree.model():
    #         self.timelineTree.model().linksOnly = value

    def mediaFilter(self) -> NodeKind:
        if self.timelineTree.model():
            return self.timelineTree.model().mediaFilter()
        return NodeKind.MONTH

    def setMediaOnly(self, value: NodeKind):
        if self.timelineTree.model():
            self.timelineTree.model().setMediaFilter(value)
            self.mediaCmb.setCurrentText(value.name)
            self.mediaCmb.setEnabled(False)
    #
    # def dirFilter(self) -> dt.DirFilter:
    #     if self.timelineTree.model():
    #         return self.timelineTree.model().dirFilter()
    #     return dt.DirFilter.ALL
    #
    # def setDirOnly(self, value: dt.DirFilter):
    #     if self.timelineTree.model():
    #         self.timelineTree.model().setDirFilter(value)
    #         self.dirCmb.setCurrentText(value.name)
    #         self.dirCmb.setEnabled(False)

    @QtCore.pyqtSlot()
    def onExpanded(self):
        for column in range(self.timelineTree.model().columnCount()):
            self.timelineTree.resizeColumnToContents(column)

    # @QtCore.pyqtSlot()
    # def onSelectNode(self):
    #     selIndexes = self.timelineTree.selectedIndexes()
    #     if len(selIndexes) < 1:
    #         return
    #     self.selectNode(selIndexes[0])

    @QtCore.pyqtSlot(QtCore.QModelIndex)
    def selectNode(self, currentIndex: QtCore.QModelIndex):
        if currentIndex.isValid():
            proxy = self.timelineTree.model()
            sourceIndex = proxy.mapToSource(currentIndex)
            model = proxy.sourceModel()
            item = model.getItem(sourceIndex)
            # item = self.timelineTree.model().getItem(currentIndex)
            print(item.path)
            self.nodeSelected.emit(item)
