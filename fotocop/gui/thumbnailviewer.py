import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Tuple

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models import settings as Config
from fotocop.models.sources import Selection
from .timelineviewer import ZoomLevel, TimelineViewer

if TYPE_CHECKING:
    from fotocop.models.sources import Image

logger = logging.getLogger(__name__)

THUMB_WIDTH = 150
THUMB_HEIGHT = 112
THUMB_HEIGHT_3_2 = 100
THUMB_TOP_3_2 = 6
CAPTION_HEIGHT = 30
CELL_MARGIN = 2
CELL_IN_WIDTH = 160
CELL_IN_HEIGHT = 190
CELL_IN_MARGIN = (CELL_IN_WIDTH - THUMB_WIDTH) / 2
CELL_WIDTH = CELL_IN_WIDTH + 2*CELL_MARGIN
CELL_HEIGHT = CELL_IN_HEIGHT + 2*CELL_MARGIN
THUMB_MARGIN = (CELL_IN_WIDTH - THUMB_HEIGHT) / 2


class ImageModel(QtCore.QAbstractListModel):
    def __init__(
        self,
        images: List["Image"] = None,
        parent=None,
    ):
        super().__init__(parent)

        self.images = images or list()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self.images)

    def flags(self, index):
        if index.isValid():
            return super().flags(index) | QtCore.Qt.ItemIsUserCheckable         # noqa
        return super().flags(index)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        images = self.images
        if row < 0 or row >= len(images):
            return None

        if role == QtCore.Qt.DisplayRole:
            return images[row].name

        if role == QtCore.Qt.UserRole:
            # logger.debug(f"Access to UserRole for {images[row].name}")
            return images[row].getThumbnail()

        # if role == QtCore.Qt.ToolTipRole:
        #     dateTime = images[row].datetime
        #     if dateTime:
        #         year, month, day, hour, minute, second = dateTime
        #         return f"{year}{month}{day}-{hour}{minute}{second}"
        #     else:
        #         return None

        if role == QtCore.Qt.CheckStateRole:
            if images[row].isSelected:
                return QtCore.Qt.Checked
            else:
                return QtCore.Qt.Unchecked

        return None

    def setData(
        self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole
    ) -> bool:
        if not index.isValid():
            return False

        row = index.row()
        if role == QtCore.Qt.CheckStateRole:
            image = self.images[row]
            isSelected = True if value == QtCore.Qt.Checked else False
            image.isSelected = isSelected
            # print(f"    > {image.name} check state is {isSelected}")
            self.dataChanged.emit(index, index, (role,))
            return True

        return False

    def clearImages(self):
        self.beginResetModel()
        self.images = list()
        self.endResetModel()

    def addImages(self, images: List["Image"]):
        self.beginInsertRows(QtCore.QModelIndex(), self.rowCount(), self.rowCount() + len(images) - 1)
        self.images.extend(images)
        self.endInsertRows()

    def updateImage(self, imageKey: str):
        found = False
        row = -1
        for row, image in enumerate(self.images):
            if image.path == imageKey:
                found = True
                break
        if found:
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, (QtCore.Qt.UserRole, QtCore.Qt.ToolTipRole))


class ThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        resources = Config.fotocopSettings.resources
        self.dummyImage = QtGui.QPixmap(f"{resources}/dummy-image.png")

    def paint(self, painter, option, index):
        imageName = index.data(QtCore.Qt.DisplayRole)
        imageThumb, aspectRatio, orientation = index.data(QtCore.Qt.UserRole)

        if imageThumb == "loading":
            px = self.dummyImage
            px = px.scaledToWidth(THUMB_WIDTH)
        else:
            px = QtGui.QPixmap()
            px.loadFromData(imageThumb)
            px = px.scaledToWidth(THUMB_WIDTH)
            rm = QtGui.QTransform().rotate(orientation)
            px = px.transformed(rm)

        rect = option.rect
        cellLeft = rect.left() + CELL_MARGIN
        cellTop = rect.top() + CELL_MARGIN
        if aspectRatio == 1.5:
            landscapeSource = QtCore.QRect(
                0, THUMB_TOP_3_2, THUMB_WIDTH, THUMB_HEIGHT_3_2
            )
            landscapeTarget = QtCore.QRect(
                cellLeft + CELL_IN_MARGIN,
                cellTop + THUMB_MARGIN + THUMB_TOP_3_2,
                THUMB_WIDTH,
                THUMB_HEIGHT_3_2,
            )
            portraitSource = QtCore.QRect(
                THUMB_TOP_3_2, 0, THUMB_HEIGHT_3_2, THUMB_WIDTH
            )
            portraitTarget = QtCore.QRect(
                cellLeft + THUMB_MARGIN + THUMB_TOP_3_2,
                cellTop + CELL_IN_MARGIN,
                THUMB_HEIGHT_3_2,
                THUMB_WIDTH,
            )
        else:
            landscapeSource = QtCore.QRect(0, 0, THUMB_WIDTH, THUMB_HEIGHT)
            landscapeTarget = QtCore.QRect(
                cellLeft + CELL_IN_MARGIN,
                cellTop + THUMB_MARGIN,
                THUMB_WIDTH,
                THUMB_HEIGHT,
            )
            portraitSource = QtCore.QRect(0, 0, THUMB_HEIGHT, THUMB_WIDTH)
            portraitTarget = QtCore.QRect(
                cellLeft + THUMB_MARGIN,
                cellTop + CELL_IN_MARGIN,
                THUMB_HEIGHT,
                THUMB_WIDTH,
            )
        if orientation != 0:
            source = portraitSource
            target = portraitTarget
        else:
            source = landscapeSource
            target = landscapeTarget

        textRect = QtCore.QRect(
            cellLeft, cellTop + CELL_IN_WIDTH, CELL_IN_WIDTH, CAPTION_HEIGHT
        )
        cellRect = QtCore.QRect(cellLeft, cellTop, CELL_IN_WIDTH, CELL_IN_HEIGHT)

        defaultPen = painter.pen()

        state = index.data(QtCore.Qt.CheckStateRole)
        bgdColor = QtGui.QColor("aliceblue") if state == QtCore.Qt.Checked else QtGui.QColor("lightgray")

        painter.fillRect(cellRect, bgdColor)

        painter.drawPixmap(target, px, source)
        painter.drawText(textRect, QtCore.Qt.AlignCenter, imageName)

        pen = QtGui.QPen(QtGui.QColor("gray"), 2)
        painter.setPen(pen)
        painter.drawRect(target)

        painter.drawRect(cellRect)

        if option.state & QtWidgets.QStyle.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("deepskyblue"), 3)
            painter.setPen(pen)
            painter.drawRect(target)

        painter.setPen(defaultPen)

        # Check state
        # https://stackoverflow.com/questions/57793643/position-qcheckbox-top-left-of-item-in-qlistview
        if state is not None:
            opt = QtWidgets.QStyleOptionViewItem()
            opt.rect = self.getCheckboxRect(option.rect)
            opt.state = opt.state & ~QtWidgets.QStyle.State_HasFocus
            if state == QtCore.Qt.Unchecked:
                opt.state |= QtWidgets.QStyle.State_Off
            elif state == QtCore.Qt.PartiallyChecked:
                opt.state |= QtWidgets.QStyle.State_NoChange
            elif state == QtCore.Qt.Checked:
                opt.state = QtWidgets.QStyle.State_On
            style = QtWidgets.QApplication.style()
            style.drawPrimitive(
                QtWidgets.QStyle.PE_IndicatorViewItemCheck, opt, painter, None
            )

    def editorEvent(self, event, model, option, index):
        flags = model.flags(index)
        if (
            not (flags & QtCore.Qt.ItemIsUserCheckable)
            or not (option.state & QtWidgets.QStyle.State_Enabled)
            or not (flags & QtCore.Qt.ItemIsEnabled)
        ):
            return False

        state = index.data(QtCore.Qt.CheckStateRole)
        if state is None:
            return False

        if event.type() in (
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QEvent.MouseButtonPress,
        ):
            viewOpt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(viewOpt, index)
            checkRect = self.getCheckboxRect(viewOpt.rect)
            if event.button() != QtCore.Qt.LeftButton or not checkRect.contains(
                event.pos()
            ):
                return False
            if event.type() in (
                QtCore.QEvent.MouseButtonPress,
                QtCore.QEvent.MouseButtonDblClick,
            ):
                # Pass event forward to handle normal item selection
                return False
        elif event.type() == QtCore.QEvent.KeyPress:
            if event.key() not in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Select):
                return False
        else:
            return False

        # Left mouse button released in the checkbox rect or space key pressed:
        # change the checkbox state.
        if flags & QtCore.Qt.ItemIsTristate:
            state = QtCore.Qt.CheckState((state + 1) % 3)
        else:
            state = (
                QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
            )
        model.setData(index, state, QtCore.Qt.CheckStateRole)
        if event.type() == QtCore.QEvent.KeyPress:
            return False
        else:
            return True

    @staticmethod
    def getCheckboxRect(rect: QtCore.QRect) -> QtCore.QRect:
        return QtCore.QRect(4, 4, 18, 18).translated(rect.topLeft())

    def sizeHint(self, QStyleOptionViewItem, QModelIndex):
        return QtCore.QSize(CELL_WIDTH, CELL_HEIGHT)


class ThumbnailViewer(QtWidgets.QWidget):

    zoomLevelChanged = QtCore.pyqtSignal(ZoomLevel)

    def __init__(self, parent=None):
        super().__init__(parent)

        # self.selectedImagesSource = None

        resources = Config.fotocopSettings.resources

        iconSize = QtCore.QSize(24, 24)
        filterIcon = QtGui.QIcon(f"{resources}/filter.png")

        self.logger = logging.getLogger(__name__)

        # https://stackoverflow.com/questions/42673010/how-to-correctly-load-images-asynchronously-in-pyqt5
        self.thumbnailView = ThumbnailView()
        self.thumbnailView.setViewMode(QtWidgets.QListView.IconMode)
        self.thumbnailView.setWrapping(True)
        self.thumbnailView.setMovement(QtWidgets.QListView.Static)
        self.thumbnailView.setResizeMode(QtWidgets.QListView.Adjust)
        self.thumbnailView.setLayoutMode(QtWidgets.QListView.SinglePass)
        self.thumbnailView.setGridSize(QtCore.QSize(CELL_WIDTH, CELL_HEIGHT))
        self.thumbnailView.setUniformItemSizes(True)
        self.thumbnailView.setMinimumWidth(4 * CELL_WIDTH + 24)
        self.thumbnailView.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )

        # self.thumbnailView.setModel(ImageModel())

        self.thumbnailView.setItemDelegate(ThumbnailDelegate())

        # self.setSortingEnabled(True)

        proxyModel = ThumbnailFilterProxyModel()
        self._imageModel = ImageModel()
        proxyModel.setSourceModel(self._imageModel)
        self.thumbnailView.setModel(proxyModel)

        self.allBtn = QtWidgets.QPushButton("All")
        self.allBtn.setToolTip("Select all images")
        self.allBtn.setStatusTip("Select all images")
        self.noneBtn = QtWidgets.QPushButton("None")
        self.noneBtn.setToolTip("Deselect all images")
        self.noneBtn.setStatusTip("Deselect all images")
        self.filterBtn = QtWidgets.QToolButton()
        self.filterBtn.setIconSize(iconSize)
        self.filterBtn.setIcon(filterIcon)
        self.filterBtn.setCheckable(True)
        self.filterBtn.setToolTip('Filter images on date')
        self.filterBtn.setStatusTip('Filter images on date')
        self.fromDateSelector = QtWidgets.QDateEdit()
        self.fromDateSelector.setCalendarPopup(True)
        self.toDateSelector = QtWidgets.QDateEdit()
        self.toDateSelector.setCalendarPopup(True)

        self.zoomLevelSelector = QtWidgets.QComboBox()
        for z in ZoomLevel:
            self.zoomLevelSelector.addItem(z.name, z)
        self.zoomLevelSelector.setCurrentText(TimelineViewer.DEFAULT_ZOOM_LEVEL.name)

        hlayout = QtWidgets.QHBoxLayout()
        hlayout.addWidget(self.allBtn)
        hlayout.addWidget(self.noneBtn)
        hlayout.addWidget(self.filterBtn)
        hlayout.addWidget(self.fromDateSelector)
        hlayout.addWidget(self.toDateSelector)
        hlayout.addWidget(self.zoomLevelSelector)
        hlayout.addStretch()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.thumbnailView)
        layout.addLayout(hlayout)
        self.setLayout(layout)

        self.allBtn.clicked.connect(self.selectAll)
        self.noneBtn.clicked.connect(self.deselectAll)
        self.fromDateSelector.dateChanged.connect(self.setFromDate)
        self.toDateSelector.dateChanged.connect(self.setToDate)
        self.filterBtn.toggled.connect(self.toggleFilter)
        self.zoomLevelSelector.activated.connect(
            lambda: self.zoomLevelChanged.emit(self.zoomLevelSelector.currentData())
        )

        self.allBtn.setEnabled(False)
        self.noneBtn.setEnabled(False)
        self.fromDateSelector.setDate(QtCore.QDate.currentDate())
        self.toDateSelector.setDate(QtCore.QDate.currentDate())
        self.filterBtn.setChecked(False)

    @QtCore.pyqtSlot(Selection)
    def onSourceSelected(self, _selection):
        self.thumbnailView.model().sourceModel().clearImages()
        self.allBtn.setEnabled(False)
        self.noneBtn.setEnabled(False)

    @QtCore.pyqtSlot(dict)
    def addImages(self, images):
        images = list(images.values())
        self.thumbnailView.model().sourceModel().addImages(images)
        self.allBtn.setEnabled(True)
        self.noneBtn.setEnabled(True)

    @QtCore.pyqtSlot(str)
    def updateImage(self, imageKey: str):
        self.thumbnailView.model().sourceModel().updateImage(imageKey)

    @QtCore.pyqtSlot()
    def selectAll(self):
        model = self.thumbnailView.model().sourceModel()
        for i in range(model.rowCount()):
            index = model.index(i, 0, QtCore.QModelIndex())
            model.setData(index, QtCore.Qt.Checked, QtCore.Qt.CheckStateRole)

    @QtCore.pyqtSlot()
    def deselectAll(self):
        model = self.thumbnailView.model().sourceModel()
        for i in range(model.rowCount()):
            index = model.index(i, 0, QtCore.QModelIndex())
            model.setData(index, QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)

    @QtCore.pyqtSlot(QtCore.QDate)
    def setFromDate(self, date: QtCore.QDate):
        fromDate = date.toString("yyyyMMdd")
        # fromDate = date.toPyDate()
        toDate = self.toDateSelector.date().toString("yyyyMMdd")
        self.thumbnailView.model().setDateFilter((fromDate, toDate))

    @QtCore.pyqtSlot(QtCore.QDate)
    def setToDate(self, date: QtCore.QDate):
        toDate = date.toString("yyyyMMdd")
        fromDate = self.fromDateSelector.date().toString("yyyyMMdd")
        self.thumbnailView.model().setDateFilter((fromDate, toDate))

    @QtCore.pyqtSlot(bool)
    def toggleFilter(self, checked: bool):
        self.thumbnailView.model().setIsDateFilterOn(checked)

    @QtCore.pyqtSlot(ZoomLevel)
    def onZoomLevelChanged(self, zoomLevel: ZoomLevel):
        self.zoomLevelSelector.setCurrentText(zoomLevel.name)


class ThumbnailView(QtWidgets.QListView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.possiblyPreserveSelectionPostClick = False

    @QtCore.pyqtSlot(QtCore.QItemSelection, QtCore.QItemSelection)
    def selectionChanged(
        self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ):
        """
        Reselect items if the user clicked a checkmark within an existing selection
        :param selected: new selection
        :param deselected: previous selection
        """

        super().selectionChanged(deselected, selected)

        if self.possiblyPreserveSelectionPostClick:
            # Must set this to False before adjusting the selection!
            self.possiblyPreserveSelectionPostClick = False

            # print("Selection preserved")
            current = self.currentIndex()
            if not(len(selected.indexes()) == 1 and selected.indexes()[0] == current):
                deselected.merge(self.selectionModel().selection(), QtCore.QItemSelectionModel.Select)
                self.selectionModel().select(deselected, QtCore.QItemSelectionModel.Select)

    @QtCore.pyqtSlot(QtGui.QMouseEvent)
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """
        Filter selection changes when click is on a thumbnail checkbox.

        When the user has selected multiple items (thumbnails), and
        then clicks one of the checkboxes, Qt's default behaviour is to
        treat that click as selecting the single item, because it doesn't
        know about our checkboxes. Therefore if the user is in fact
        clicking on a checkbox, we need to filter that event.

        On some versions of Qt 5 (to be determined), no matter what we do here,
        the delegate's editorEvent will still be triggered.

        :param event: the mouse click event
        """
        rightButtonPressed = event.button() == QtCore.Qt.RightButton
        if rightButtonPressed:
            super().mousePressEvent(event)

        else:
            clickedIndex = self.indexAt(event.pos())
            clickedRow = clickedIndex.row()

            if clickedRow >= 0:
                rect = self.visualRect(clickedIndex)
                delegate = self.itemDelegate(clickedIndex)
                checkboxRect = delegate.getCheckboxRect(rect)
                checkboxClicked = checkboxRect.contains(event.pos())

                if checkboxClicked:
                    # print("Preserving selection")
                    self.possiblyPreserveSelectionPostClick = True
                    selected = self.selectionModel().selection()
                    model = self.model()
                    state = model.data(clickedIndex, QtCore.Qt.CheckStateRole)
                    state = QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
                    if len(selected.indexes()) > 1 and clickedIndex in selected.indexes():
                        for index in selected.indexes():
                            if not index == clickedIndex:
                                model.setData(index, state, QtCore.Qt.CheckStateRole)

            super().mousePressEvent(event)

    @QtCore.pyqtSlot(QtGui.QKeyEvent)
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """
        Filter selection changes when click is on a thumbnail checkbox.

        When the user has selected multiple items (thumbnails), and
        then clicks one of the checkboxes, Qt's default behaviour is to
        treat that click as selecting the single item, because it doesn't
        know about our checkboxes. Therefore if the user is in fact
        clicking on a checkbox, we need to filter that event.

        On some versions of Qt 5 (to be determined), no matter what we do here,
        the delegate's editorEvent will still be triggered.

        :param event: the mouse click event
        """
        selectedIndexes = self.selectionModel().selection().indexes()
        if len(selectedIndexes) < 1 or event.key() not in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Select):
            super().keyPressEvent(event)

        else:
            clickedIndex = self.currentIndex()
            model = self.model()
            state = model.data(clickedIndex, QtCore.Qt.CheckStateRole)
            state = QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
            for index in selectedIndexes:
                if not index == clickedIndex:
                    model.setData(index, state, QtCore.Qt.CheckStateRole)

            super().keyPressEvent(event)


class ThumbnailFilterProxyModel(QtCore.QSortFilterProxyModel):

    _dateFilter = tuple()
    _isDateFilterOn = False

    @classmethod
    def dateFilter(cls) -> Tuple[str, str]:
        return cls._dateFilter

    def setDateFilter(self, value: Tuple[str, str]):
        ThumbnailFilterProxyModel._dateFilter = value
        self.invalidateFilter()

    @classmethod
    def isDateFilterOn(cls) -> bool:
        return cls._isDateFilterOn

    def setIsDateFilterOn(self, value: bool):
        ThumbnailFilterProxyModel._isDateFilterOn = value
        self.invalidateFilter()

    def filterAcceptsRow(self, sourceRow: int, sourceParent: QtCore.QModelIndex) -> bool:
        OkDate = True

        if self.isDateFilterOn():
            index = self.sourceModel().index(sourceRow, 0, sourceParent)
            dateTime = self.sourceModel().data(index, QtCore.Qt.ToolTipRole)
            if dateTime:
                dateTime = datetime.strptime(dateTime, "%Y%m%d-%H%M%S")
                start, end = self.dateFilter()
                start = datetime.strptime(start, "%Y%m%d")
                end = datetime.strptime(end, "%Y%m%d")
                OkDate = start <= dateTime <= end

        return OkDate
