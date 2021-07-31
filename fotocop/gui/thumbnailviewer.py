from typing import TYPE_CHECKING, Any, Tuple, List
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models import settings as Config

if TYPE_CHECKING:
    from fotocop.models.sources import SourceManager, Image


THUMB_WIDTH = 150
THUMB_HEIGHT = 112
THUMB_HEIGHT_3_2 = 100
THUMB_TOP_3_2 = 6
CAPTION_HEIGHT = 30
CELL_MARGIN = 2
CELL_IN_WIDTH = 160
CELL_IN_HEIGHT = 190
CELL_IN_MARGIN = (CELL_IN_WIDTH - THUMB_WIDTH) / 2
CELL_WIDTH = CELL_IN_WIDTH + 2 * CELL_MARGIN
CELL_HEIGHT = CELL_IN_HEIGHT + 2 * CELL_MARGIN
THUMB_MARGIN = (CELL_IN_WIDTH - THUMB_HEIGHT) / 2


class ImageModel(QtCore.QAbstractListModel):
    def __init__(
        self,
        sourceManager: "SourceManager",
        images: List["Image"] = None,
        parent=None,
    ):
        super().__init__(parent)

        self.sourceManager = sourceManager
        self.images = images or list()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self.images)

    def flags(self, index):
        if index.isValid():
            return super().flags(index) | QtCore.Qt.ItemIsUserCheckable
        return super().flags(index)
        # return (
        #     QtCore.Qt.ItemIsEnabled
        #     | QtCore.Qt.ItemIsSelectable
        #     | QtCore.Qt.ItemIsUserCheckable
        # )

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
            return self.sourceManager.getThumbnail(images[row].path)

        if role == QtCore.Qt.ToolTipRole:
            dateTime = self.sourceManager.getDateTime(images[row].path)
            if dateTime:
                year, month, day, hour, minute, second = dateTime
                return f"{year}{month}{day}-{hour}{minute}{second}"
            else:
                return None

        if role == QtCore.Qt.CheckStateRole:
            if images[row].isSelected:
                print(f"    > {images[row].name} is checked")
                return QtCore.Qt.Checked
            else:
                print(f"    > {images[row].name} is unchecked")
                return QtCore.Qt.Unchecked

        return None

    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole):
        if not index.isValid():
            return False

        row = index.row()
        if role == QtCore.Qt.CheckStateRole:
            image = self.images[row]
            isSelected = True if value == QtCore.Qt.Checked else False
            image.isSelected = isSelected
            print(f"    > {image.name} check state is {isSelected}")
            self.dataChanged.emit(index, index, (role,))
            return True

        return False

    def newImages(self, images: List["Image"]):
        self.beginResetModel()
        self.images = images
        self.endResetModel()

    def addImages(self, images: List["Image"], end: bool = False):
        self.images.extend(images)
        self.layoutChanged.emit()

    def setImages(self, images: List["Image"]):
        self.beginResetModel()
        self.images = images
        self.endResetModel()


class ThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    # t1 = QtCore.pyqtSignal(str, str, dict)

    def __init__(self, parent=None):
        # def __init__(self, image_cache, loader_thread, parent=None):
        super().__init__(parent)
        # self.imageCache = imageCache
        # resources = Config.fotocopSettings.resources
        # self.placeholder_image = QtGui.QPixmap(f"{resources}/dummy-image.png").scaled(
        #     160, 120
        # )
        # self.image_cache = image_cache
        # self.loader_thread = loader_thread
        # self.t1.connect(self.loader_thread.insert_into_queue)

    def paint(self, painter, option, index):
        imageName = index.data(QtCore.Qt.DisplayRole)
        imageThumb, aspectRatio, orientation = index.data(QtCore.Qt.UserRole)

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

        # try:
        #     cachedThumb = self.image_cache[imageName]
        #     print("Got image: {} from cache".format(imageName)
        # except KeyError as e:
        #     self.t1.emit(imageName, imageThumb, self.image_cache)
        #     cachedThumb = self.placeholder_image
        #     print("Drawing placeholder image for {}".format(imageName)

        defaultPen = painter.pen()

        painter.fillRect(
            QtCore.QRect(cellLeft, cellTop, CELL_IN_WIDTH, CELL_IN_HEIGHT),
            QtGui.QColor("lightgray"),
        )

        painter.drawPixmap(target, px, source)
        painter.drawText(textRect, QtCore.Qt.AlignCenter, imageName)

        pen = QtGui.QPen(QtGui.QColor("gray"), 2)
        painter.setPen(pen)
        painter.drawRect(target)

        painter.drawRect(cellLeft, cellTop, CELL_IN_WIDTH, CELL_IN_HEIGHT)

        if option.state & QtWidgets.QStyle.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("white"), 3)
            painter.setPen(pen)
            painter.drawRect(target)
            # highlight_color = option.palette.highlight().color()
            # highlight_color.setAlpha(50)
            # highlight_brush = QtGui.QBrush(highlight_color)
            # painter.fillRect(
            #     QtCore.QRect(cellLeft, cellTop, CELL_IN_WIDTH, CELL_IN_HEIGHT),
            #     highlight_brush,
            # )

        painter.setPen(defaultPen)

        # Checkstate
        # https://stackoverflow.com/questions/57793643/position-qcheckbox-top-left-of-item-in-qlistview
        value = index.data(QtCore.Qt.CheckStateRole)
        if value is not None:
            opt = QtWidgets.QStyleOptionViewItem()
            opt.rect = self.getCheckboxRect(option)
            opt.state = opt.state & ~QtWidgets.QStyle.State_HasFocus
            if value == QtCore.Qt.Unchecked:
                opt.state |= QtWidgets.QStyle.State_Off
            elif value == QtCore.Qt.PartiallyChecked:
                opt.state |= QtWidgets.QStyle.State_NoChange
            elif value == QtCore.Qt.Checked:
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

        value = index.data(QtCore.Qt.CheckStateRole)
        if value is None:
            return False

        style = QtWidgets.QApplication.style()
        if event.type() in (
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QEvent.MouseButtonPress,
        ):
            viewOpt = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(viewOpt, index)
            checkRect = self.getCheckboxRect(viewOpt)
            if event.button() != QtCore.Qt.LeftButton or not checkRect.contains(
                event.pos()
            ):
                return False
            if event.type() in (
                QtCore.QEvent.MouseButtonPress,
                QtCore.QEvent.MouseButtonDblClick,
            ):
                return True
        elif event.type() == QtCore.QEvent.KeyPress:
            if event.key() not in (QtCore.Qt.Key_Space, QtCore.Qt.Key_Select):
                return False
        else:
            return False
        state = value
        if flags & QtCore.Qt.ItemIsTristate:
            state = QtCore.Qt.CheckState((state + 1) % 3)
        else:
            state = (
                QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
            )
        return model.setData(index, state, QtCore.Qt.CheckStateRole)

    @staticmethod
    def getCheckboxRect(option):
        return QtCore.QRect(4, 4, 18, 18).translated(option.rect.topLeft())

    def sizeHint(self, QStyleOptionViewItem, QModelIndex):
        return QtCore.QSize(CELL_WIDTH, CELL_HEIGHT)


class ThumbnailViewer(QtWidgets.QWidget):
    def __init__(self, sourceManager: "SourceManager", parent=None):
        super().__init__(parent)

        self.sourceManager = sourceManager

        # https://stackoverflow.com/questions/42673010/how-to-correctly-load-images-asynchronously-in-pyqt5
        self.thumbnailView = QtWidgets.QListView()
        self.thumbnailView.setViewMode(QtWidgets.QListView.IconMode)
        self.thumbnailView.setWrapping(True)
        self.thumbnailView.setMovement(QtWidgets.QListView.Static)
        self.thumbnailView.setResizeMode(QtWidgets.QListView.Adjust)
        self.thumbnailView.setLayoutMode(QtWidgets.QListView.SinglePass)
        # self.thumbnailView.setLayoutMode(QtWidgets.QListView.Batched)
        # self.thumbnailView.setBatchSize(10)
        self.thumbnailView.setGridSize(QtCore.QSize(CELL_WIDTH, CELL_HEIGHT))
        self.thumbnailView.setUniformItemSizes(True)
        self.thumbnailView.setMinimumWidth(4 * CELL_WIDTH + 24)
        self.thumbnailView.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )

        self.thumbnailView.setModel(ImageModel(sourceManager))

        self.thumbnailView.setItemDelegate(ThumbnailDelegate())

        # self.thumbnailView.selectionModel().selectionChanged.connect(
        #     self.onSelectionChange
        # )

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.thumbnailView)
        self.setLayout(layout)

    def newImages(self, images):
        self.thumbnailView.model().newImages(images)

    def addImages(self, images):
        self.thumbnailView.model().addImages(images)

    def imagesLoaded(self, images):
        self.thumbnailView.model().addImages(images, end=True)

    # def updateImages(self):
    #     images = self.sourceManager.getImages()
    #     self.thumbnailView.model().setImages(images)

    def onSelectionChange(
        self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ):
        for index in selected.indexes():
            model = index.model()
            image = model.images[index.row()]
            image.isSelected = True
            model.dataChanged.emit(index, index, (QtCore.Qt.CheckStateRole,))
            print(f"==> {image.name} is selected")

        for index in deselected.indexes():
            model = index.model()
            image = model.images[index.row()]
            image.isSelected = False
            model.dataChanged.emit(index, index, (QtCore.Qt.CheckStateRole,))
            print(f"==> {image.name} is deselected")
