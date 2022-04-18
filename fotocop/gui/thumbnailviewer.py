import logging
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Dict, Optional, cast

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.util.rangeutil import runs
from fotocop.models import settings as Config
from fotocop.models.sources import Selection, ImageProperty
from fotocop.models.timeline import TimeRange
from .timelineviewer import tlv

if TYPE_CHECKING:
    from fotocop.models.sources import ImageKey, Image

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
CELL_WIDTH = CELL_IN_WIDTH + 2 * CELL_MARGIN
CELL_HEIGHT = CELL_IN_HEIGHT + 2 * CELL_MARGIN
THUMB_MARGIN = (CELL_IN_WIDTH - THUMB_HEIGHT) / 2


class ImageModel(QtCore.QAbstractListModel):
    class UserRoles(IntEnum):
        ThumbnailRole = QtCore.Qt.UserRole + 1
        DateTimeRole = QtCore.Qt.UserRole + 2
        SessionRole = QtCore.Qt.UserRole + 3
        PreviouslyDownloadedRole = QtCore.Qt.UserRole + 4

    def __init__(self, parent=None):
        super().__init__(parent)

        self._sourceSelection: Optional["Selection"] = None
        self._images: List["ImageKey"] = list()
        self.sessionRequired = False

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self._images)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if index.isValid():
            return super().flags(index) | QtCore.Qt.ItemIsUserCheckable  # noqa
        return super().flags(index)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        imageKey = self._imageKeyFromIndex(index)
        if imageKey is None:
            return None

        if role == QtCore.Qt.DisplayRole:
            return self._sourceSelection.getImageProperty(imageKey, ImageProperty.NAME)

        if role == ImageModel.UserRoles.ThumbnailRole:
            return self._sourceSelection.getImageProperty(
                imageKey, ImageProperty.THUMBNAIL
            )

        if role == ImageModel.UserRoles.DateTimeRole:
            return self._sourceSelection.getImageProperty(
                imageKey, ImageProperty.DATETIME
            )

        if role == ImageModel.UserRoles.SessionRole:
            return self._sourceSelection.getImageProperty(
                imageKey, ImageProperty.SESSION
            )

        if role == ImageModel.UserRoles.PreviouslyDownloadedRole:
            return self._sourceSelection.getImageProperty(
                imageKey, ImageProperty.DOWNLOAD_INFO
            ).isPreviouslyDownloaded

        if role == QtCore.Qt.ToolTipRole:
            sourceSelection = self._sourceSelection
            name = sourceSelection.getImageProperty(imageKey, ImageProperty.NAME)
            datetime_ = sourceSelection.getImageProperty(
                imageKey, ImageProperty.DATETIME
            )
            downloadInfo = sourceSelection.getImageProperty(
                imageKey, ImageProperty.DOWNLOAD_INFO
            )
            if datetime_:
                takenOn = datetime_.strftime("%a %d %b %Y %I:%M:%S %p")
            else:
                takenOn = ""
            session = sourceSelection.getImageProperty(imageKey, ImageProperty.SESSION)
            isSelected = sourceSelection.getImageProperty(
                imageKey, ImageProperty.IS_SELECTED
            )

            tip = f"<b>{name}</b><br>Taken on {takenOn}"

            previouslyDownloaded = downloadInfo.isPreviouslyDownloaded
            if previouslyDownloaded:
                downloadPath = downloadInfo.downloadPath
                downloadTime = downloadInfo.downloadTime.strftime(
                    "%a %d %b %Y %I:%M:%S %p"
                )
                if downloadPath != ".":
                    downloadName = Path(downloadPath).name
                    downloadPath = Path(downloadPath).parent
                    tip += f"<br><br>Previously downloaded as:<br>{downloadName}<br>{downloadPath}<br>{downloadTime}"
                else:
                    tip += f"<br><br><i>Manually set as previously downloaded on {downloadTime}</i>"

            if session:
                tip += f"<br><br>Session: {session}"
            elif self.sessionRequired and isSelected:
                tip += f"<br><br><i>A session is required!</i>"

            return tip

        if role == QtCore.Qt.CheckStateRole:
            if self._sourceSelection.getImageProperty(
                imageKey, ImageProperty.IS_SELECTED
            ):
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
            imageKey = self._images[row]
            self._sourceSelection.markImagesAsSelected([imageKey], True if value == QtCore.Qt.Checked else False)
            self.dataChanged.emit(index, index, (role,))
            return True

        if role == ImageModel.UserRoles.SessionRole:
            imageKey = self._images[row]
            self._sourceSelection.setImagesSession([imageKey], value)
            self.dataChanged.emit(index, index, (role,))
            return True

        if role == ImageModel.UserRoles.PreviouslyDownloadedRole:
            imageKey = self._images[row]
            self._sourceSelection.markImagesAsPreviouslyDownloaded([(imageKey, None, None)])
            self.dataChanged.emit(index, index, (role,))
            return True

        return False

    def setSourceSelection(self, selection: "Selection") -> None:
        self._sourceSelection = selection

    def clearImages(self) -> None:
        self.beginResetModel()
        self._images = list()
        self.endResetModel()

    def addImages(self, images: List["ImageKey"]):
        row = self.rowCount()
        self.beginInsertRows(QtCore.QModelIndex(), row, row + len(images) - 1)
        self._images.extend(images)
        self.endInsertRows()

    def updateImage(self, imageKey: "ImageKey") -> None:
        index = self._indexFromImageKey(imageKey)
        if index.isValid():
            self.dataChanged.emit(
                index,
                index,
                (ImageModel.UserRoles.ThumbnailRole, ImageModel.UserRoles.DateTimeRole),
            )

    def setDataRange(
        self,
        selection: List[QtCore.QModelIndex],
        value: Any,
        role: int = QtCore.Qt.EditRole,
    ) -> bool:
        rows = list()
        imageKeys = list()
        imagesInfo = list()
        for index in selection:
            row = index.row()
            rows.append(row)
            imageKeys.append(self._images[row])
            imagesInfo.append((self._images[row], None, None))

        if imageKeys:
            if role == QtCore.Qt.CheckStateRole:
                self._sourceSelection.markImagesAsSelected(imageKeys, value)

            elif role == ImageModel.UserRoles.SessionRole:
                self._sourceSelection.setImagesSession(imageKeys, value)

            elif role == ImageModel.UserRoles.PreviouslyDownloadedRole:
                self._sourceSelection.markImagesAsPreviouslyDownloaded(imagesInfo)
            else:
                return False

        rows.sort()
        for first, last in runs(rows):
            self.dataChanged.emit(self.index(first, 0), self.index(last, 0), (role,))
        return True

    def selectedImagesCount(self) -> int:
        sourceSelection = self._sourceSelection
        if sourceSelection is None:
            return 0

        return sourceSelection.selectedImagesCount

    def _imageKeyFromIndex(self, index: QtCore.QModelIndex) -> Optional["ImageKey"]:
        if not index.isValid():
            return None

        row = index.row()
        if row < 0 or row >= self.rowCount():
            return None

        return self._images[row]

    def _indexFromImageKey(self, imageKey: "ImageKey") -> QtCore.QModelIndex:
        try:
            row = self._images.index(imageKey)
        except ValueError:
            return QtCore.QModelIndex()
        else:
            return self.index(row, 0)


class ThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

        resources = Config.fotocopSettings.resources
        self._dummyImage = QtGui.QPixmap(f"{resources}/dummy-image.png")

        self.sessionRequired = False

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        # Retrieves image properties.
        imageName = index.data(QtCore.Qt.DisplayRole)
        imageSession = index.data(ImageModel.UserRoles.SessionRole)
        imageIsSelected = index.data(QtCore.Qt.CheckStateRole) == QtCore.Qt.Checked
        imageThumb, aspectRatio, orientation = index.data(
            ImageModel.UserRoles.ThumbnailRole
        )
        previouslyDownloaded = index.data(ImageModel.UserRoles.PreviouslyDownloadedRole)

        # Build the image pixmap: a portrait dummy image when the image thumbnail is
        # not yet loaded, the loaded thumbnail with the correct orientation otherwise.
        if imageThumb == "loading":
            px = self._dummyImage
            px = px.scaledToWidth(THUMB_WIDTH)
        else:
            px = QtGui.QPixmap()
            px.loadFromData(imageThumb)
            px = px.scaledToWidth(THUMB_WIDTH)
            rm = QtGui.QTransform().rotate(orientation)
            px = px.transformed(rm)

        # Build rect for the pixmap source and target with the correct aspect ratio
        # and orientation.
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

        # Build rect for the image name and the whole cell.
        textRect = QtCore.QRect(
            cellLeft, cellTop + CELL_IN_WIDTH, CELL_IN_WIDTH, CAPTION_HEIGHT
        )
        cellRect = QtCore.QRect(cellLeft, cellTop, CELL_IN_WIDTH, CELL_IN_HEIGHT)

        # Add dimming on the image pixmap when previously downloaded and not selected.
        if (
            previouslyDownloaded
            and not imageIsSelected
            # and download_status == DownloadStatus.not_downloaded
        ):
            disabled = QtGui.QPixmap(px.size())
            disabled.setDevicePixelRatio(px.devicePixelRatioF())
            disabled.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(disabled)
            p.setBackgroundMode(QtCore.Qt.TransparentMode)
            p.setBackground(QtGui.QBrush(QtCore.Qt.transparent))
            p.eraseRect(px.rect())
            p.setOpacity(0.5)
            p.drawPixmap(0, 0, px)
            p.end()
            px = disabled

        defaultPen = painter.pen()

        # Paint the cell background: color depends on its selection state.
        state = index.data(QtCore.Qt.CheckStateRole)
        bgdColor = (
            QtGui.QColor("aliceblue")
            if state == QtCore.Qt.Checked
            else QtGui.QColor("lightgray")
        )
        painter.fillRect(cellRect, bgdColor)

        # Draw the image pixmap and name.
        painter.drawPixmap(target, px, source)
        painter.drawText(textRect, QtCore.Qt.AlignCenter, imageName)

        # Draw a caution flag for selected images without a session when required.
        if self.sessionRequired and imageIsSelected and not imageSession:
            sessionRect = QtCore.QRect(
                rect.left() + CELL_IN_WIDTH - CAPTION_HEIGHT,
                cellTop,
                CAPTION_HEIGHT,
                CAPTION_HEIGHT,
            )
            font = painter.font()
            fontSize = font.pointSize()
            font.setPointSize(fontSize + 4)
            pen = QtGui.QPen(QtGui.QColor("darkorange"), 2)
            painter.setPen(pen)
            painter.setFont(font)
            painter.drawText(sessionRect, QtCore.Qt.AlignCenter, "\u26A0")  # /!\
            font.setPointSize(fontSize)
            painter.setFont(font)

        # Draw a border around the image pixmap and the whole cell.
        pen = QtGui.QPen(QtGui.QColor("gray"), 2)
        painter.setPen(pen)
        painter.drawRect(target)
        painter.drawRect(cellRect)

        # Overload the border the image pixmap when image is selected
        if option.state & QtWidgets.QStyle.State_Selected:
            pen = QtGui.QPen(QtGui.QColor("deepskyblue"), 3)
            painter.setPen(pen)
            painter.drawRect(target)

        painter.setPen(defaultPen)

        # Draw the image check state
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

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: "ImageModel",
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        flags = cast(int, model.flags(index))
        # Filter items that are not enabled or not checkable.
        if (
            not (flags & QtCore.Qt.ItemIsUserCheckable)
            or not (option.state & QtWidgets.QStyle.State_Enabled)
            or not (flags & QtCore.Qt.ItemIsEnabled)
        ):
            return False

        # Filter items with undefined check state.
        state = index.data(QtCore.Qt.CheckStateRole)
        if state is None:
            return False

        # Filter mouse button press or double-clicked outside the checkbox, key
        # events that are not a check state key and or all non mouse or key events.
        if event.type() in (
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QEvent.MouseButtonPress,
        ):
            event: QtGui.QMouseEvent
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
                # Pass event forward to handle normal item selection.
                return False
        elif event.type() == QtCore.QEvent.KeyPress:
            event: QtGui.QKeyEvent
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

        # Pass key press event forward to handle normal key action.
        if event.type() == QtCore.QEvent.KeyPress:
            return False
        else:
            return True

    @staticmethod
    def getCheckboxRect(rect: QtCore.QRect) -> QtCore.QRect:
        return QtCore.QRect(4, 4, 18, 18).translated(rect.topLeft())

    def sizeHint(self, QStyleOptionViewItem, QModelIndex) -> QtCore.QSize:
        return QtCore.QSize(CELL_WIDTH, CELL_HEIGHT)


class ThumbnailViewer(QtWidgets.QWidget):

    zoomLevelChanged = QtCore.pyqtSignal(tlv.ZoomLevel)

    def __init__(self, parent=None):
        super().__init__(parent)

        resources = Config.fotocopSettings.resources

        iconSize = QtCore.QSize(24, 24)
        filterIcon = QtGui.QIcon(f"{resources}/filter.png")

        self.logger = logging.getLogger(__name__)

        self.thumbnailView = ThumbnailView()
        self.thumbnailView.setItemDelegate(ThumbnailDelegate())

        proxyModel = ThumbnailFilterProxyModel()
        self._imageModel = ImageModel()
        proxyModel.setSourceModel(self._imageModel)
        self.thumbnailView.setModel(proxyModel)

        self.toolbar = QtWidgets.QToolBar("Thumbnails tools")
        interToolsSpacing = 4

        self.selectWidget = QtWidgets.QWidget()
        allBtn = QtWidgets.QPushButton("All")
        allBtn.setToolTip("Select all images")
        allBtn.setStatusTip("Select all images")
        noneBtn = QtWidgets.QPushButton("None")
        noneBtn.setToolTip("Deselect all images")
        noneBtn.setStatusTip("Deselect all images")
        selectLayout = QtWidgets.QHBoxLayout()
        selectLayout.setContentsMargins(0, 0, interToolsSpacing, 0)
        selectLayout.addWidget(allBtn)
        selectLayout.addWidget(noneBtn)
        self.selectWidget.setLayout(selectLayout)

        filterWidget = QtWidgets.QWidget()
        self.newChk = QtWidgets.QCheckBox()
        self.newChk.setText("New only")
        self.newChk.setToolTip("Mask images previously downloaded")
        self.newChk.setStatusTip("Mask images previously downloaded")
        self.filterBtn = QtWidgets.QToolButton()
        self.filterBtn.setIconSize(iconSize)
        self.filterBtn.setIcon(filterIcon)
        self.filterBtn.setCheckable(True)
        self.filterBtn.setToolTip("Filter images by selecting dates in the timeline")
        self.filterBtn.setStatusTip("Filter images by selecting dates in the timeline")
        self.selStatusLbl = QtWidgets.QLabel("")
        filterLayout = QtWidgets.QHBoxLayout()
        filterLayout.setContentsMargins(interToolsSpacing, 0, interToolsSpacing, 0)
        filterLayout.addWidget(self.filterBtn)
        filterLayout.addWidget(self.selStatusLbl)
        filterWidget.setLayout(filterLayout)

        sessionWidget = QtWidgets.QWidget()
        self.sessionLbl = QtWidgets.QLabel("Session:")
        self.sessionTxt = QtWidgets.QLineEdit()
        # Accept space separated word of latin accented letter plus &',_-
        # First character shall be a latin capital letter or _
        # refer to https://www.ascii-code.com/ and https://regex101.com/library/g6gJyf
        validator = QtGui.QRegularExpressionValidator(
            QtCore.QRegularExpression(r"^[A-ZÀ-ÖØ-Þ_][0-9A-Za-zÀ-ÖØ-öø-ÿ &',_-]*$")
        )
        self.sessionTxt.setValidator(validator)
        self.applySessionBtn = QtWidgets.QPushButton("Apply")
        self.removeSessionBtn = QtWidgets.QPushButton("Remove")
        sessionLayout = QtWidgets.QHBoxLayout()
        sessionLayout.setContentsMargins(interToolsSpacing, 0, interToolsSpacing, 0)
        sessionLayout.addWidget(self.sessionLbl)
        sessionLayout.addWidget(self.sessionTxt)
        sessionLayout.addWidget(self.applySessionBtn)
        sessionLayout.addWidget(self.removeSessionBtn)
        sessionWidget.setLayout(sessionLayout)

        spacer = QtWidgets.QWidget(self)
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )

        self.zoomLevelSelector = QtWidgets.QComboBox()
        for z in tlv.ZoomLevel:
            self.zoomLevelSelector.addItem(z.name, z)
        self.zoomLevelSelector.setCurrentText(tlv.DEFAULT_ZOOM_LEVEL.name)

        self.toolbar.addWidget(self.newChk)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(self.selectWidget)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(filterWidget)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(sessionWidget)
        self.toolbar.addWidget(spacer)
        self.toolbar.addWidget(self.zoomLevelSelector)

        hlayout = QtWidgets.QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.addWidget(self.toolbar)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(0)
        layout.addWidget(self.thumbnailView)
        layout.addLayout(hlayout)
        self.setLayout(layout)

        self.thumbnailView.model().sourceModel().dataChanged.connect(
            self.onImageModelChanged
        )
        self.thumbnailView.selectionModel().selectionChanged.connect(
            self.onSelectionChanged
        )
        allBtn.clicked.connect(
            lambda: self.thumbnailView.setSelected(QtCore.Qt.Checked)
        )
        noneBtn.clicked.connect(
            lambda: self.thumbnailView.setSelected(QtCore.Qt.Unchecked)
        )
        self.newChk.toggled.connect(self.toggleNewOnly)
        self.filterBtn.toggled.connect(self.toggleFilter)
        self.zoomLevelSelector.activated.connect(
            lambda: self.zoomLevelChanged.emit(self.zoomLevelSelector.currentData())
        )
        self.sessionTxt.textEdited.connect(self.checkSession)
        self.sessionTxt.returnPressed.connect(self.applySession)
        self.applySessionBtn.clicked.connect(self.applySession)
        self.removeSessionBtn.clicked.connect(self.removeSession)

        self.selectWidget.setEnabled(False)
        self.newChk.setChecked(True)
        self.newChk.setEnabled(False)
        self.filterBtn.setChecked(False)
        self.filterBtn.setEnabled(False)
        self.selStatusLbl.hide()
        self.applySessionBtn.setEnabled(False)
        self.removeSessionBtn.setEnabled(False)
        self.zoomLevelSelector.setEnabled(False)

    @QtCore.pyqtSlot(Selection)
    def setSourceSelection(self, selection: "Selection") -> None:
        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()
        # Register the source selection in the model and clear it.
        model.setSourceSelection(selection)
        model.clearImages()
        # Reset the time range filter to the default "full time" range.
        proxy.setTimeRangeFilter([TimeRange()])

        # Hide or disable all the toolbar widget.
        self.selectWidget.setEnabled(False)
        self.newChk.setEnabled(False)
        self.filterBtn.setChecked(False)
        self.filterBtn.setEnabled(False)
        self.selStatusLbl.hide()
        self.zoomLevelSelector.setEnabled(False)

    @QtCore.pyqtSlot(dict)
    def addImages(self, images: Dict["ImageKey", "Image"]) -> None:
        images = list(images)
        self.thumbnailView.model().sourceModel().addImages(images)
        self.selectWidget.setEnabled(True)
        self.newChk.setEnabled(True)

    @QtCore.pyqtSlot(str)
    def updateImage(self, imageKey: str) -> None:
        self.thumbnailView.model().sourceModel().updateImage(imageKey)

    @QtCore.pyqtSlot(QtCore.QModelIndex, QtCore.QModelIndex, "QVector<int>")
    def onImageModelChanged(
        self,
        _topleft: QtCore.QModelIndex,
        _bottomright: QtCore.QModelIndex,
        roles: List[int],
    ) -> None:
        if (
            QtCore.Qt.CheckStateRole in roles
            or ImageModel.UserRoles.PreviouslyDownloadedRole in roles
        ):
            self.updateSelStatus()

    @QtCore.pyqtSlot(bool)
    def toggleNewOnly(self, checked: bool) -> None:
        self.thumbnailView.model().setIsNewFilterOn(checked)
        self.updateSelStatus()

    @QtCore.pyqtSlot(bool)
    def toggleFilter(self, checked: bool) -> None:
        self.thumbnailView.model().setIsDateFilterOn(checked)
        self.updateSelStatus()

    @QtCore.pyqtSlot(tlv.ZoomLevel)
    def onZoomLevelChanged(self, zoomLevel: tlv.ZoomLevel) -> None:
        self.zoomLevelSelector.setCurrentText(zoomLevel.name)

    @QtCore.pyqtSlot(str, int)
    def showNodeInfo(self, nodeKey: str, nodeWeight: int) -> None:
        mainWindow = QtUtil.getMainWindow()
        if nodeKey:
            mainWindow.showStatusMessage(f"{nodeKey}: {nodeWeight} images")

    @QtCore.pyqtSlot(list)
    def updateTimeRange(self, timeRange: List["TimeRange"]) -> None:
        if timeRange:
            self.filterBtn.setChecked(True)
        else:
            self.filterBtn.setChecked(False)
        thumbnailView = self.thumbnailView
        thumbnailView.model().setTimeRangeFilter(timeRange)
        thumbnailView.selectImages()
        self.updateSelStatus()
        self.sessionTxt.selectAll()
        self.sessionTxt.setFocus()

    @QtCore.pyqtSlot()
    def activateDateFilter(self) -> None:
        self.filterBtn.setChecked(False)
        self.filterBtn.setEnabled(True)
        self.selStatusLbl.show()
        self.zoomLevelSelector.setEnabled(True)
        self.updateSelStatus()

    @QtCore.pyqtSlot(QtCore.QItemSelection, QtCore.QItemSelection)
    def onSelectionChanged(
        self, _selected: QtCore.QItemSelection, _deselected: QtCore.QItemSelection
    ):
        """Update the session editor text and apply action availability."""
        thumbnailView = self.thumbnailView
        selectedProxyIndexes = thumbnailView.selectionModel().selection().indexes()
        session = self._sessionOfSelectedImages(selectedProxyIndexes)

        # In all cases, indicates the selected images count if not null.
        applyCount = f" ({len(selectedProxyIndexes)})" if selectedProxyIndexes else ""
        self.applySessionBtn.setText(f"Apply{applyCount}")
        self.removeSessionBtn.setText(f"Remove{applyCount}")
        self.removeSessionBtn.setEnabled(session is not None and session != "")

        # Empty selection: cannot apply any session (but leave edited session unchanged if any).
        if session is None:
            self.applySessionBtn.setEnabled(False)
            return

        editedSession = self.sessionTxt.text()
        if session in ("", "!="):
            # The selected images have empty or different sessions: can apply the edited
            # session if not empty, but select it to ease its modification.
            self.applySessionBtn.setEnabled(editedSession != "")
            self.sessionTxt.selectAll()
            self.sessionTxt.setFocus()
            return

        # The selected images have the same non-empty session:
        if not editedSession:
            # No edited session: set it to the selected images' one and disable apply
            # action.
            self.sessionTxt.setText(session)
            self.applySessionBtn.setEnabled(False)
            return

        if editedSession != session:
            # Another non-empty edited session exists: change it to the selected
            # images' one and disable apply action.
            self.sessionTxt.setText(session)
            self.applySessionBtn.setEnabled(False)
            return

        # A non-empty edited session exists, but it is the selected images' one: apply
        # is useless.
        self.applySessionBtn.setEnabled(False)

    @QtCore.pyqtSlot(str)
    def checkSession(self, text: str) -> None:
        selectedProxyIndexes = self.thumbnailView.selectionModel().selection().indexes()
        nonEmptySelection = len(selectedProxyIndexes) > 0

        # Session can be applied if non-empty and at least one image is selected.
        ok = text != "" and nonEmptySelection
        self.applySessionBtn.setEnabled(ok)

        # In all cases, indicates the selected images count if not null.
        applyCount = f" ({len(selectedProxyIndexes)})" if nonEmptySelection else ""
        self.applySessionBtn.setText(f"Apply{applyCount}")

    @QtCore.pyqtSlot()
    def applySession(self) -> None:
        self._updateSession(self.sessionTxt.text())

    @QtCore.pyqtSlot()
    def removeSession(self) -> None:
        self._updateSession("")

    @QtCore.pyqtSlot(bool)
    def requestSession(self, sessionRequired: bool) -> None:
        self.thumbnailView.requestSession(sessionRequired)

    @QtCore.pyqtSlot()
    def updateSelStatus(self):
        proxy = self.thumbnailView.model()
        proxy.invalidateFilter()
        model = proxy.sourceModel()
        imagesCount = model.rowCount()
        imagesShown = proxy.rowCount()
        selectedImagesCount = model.selectedImagesCount()
        self.selStatusLbl.setText(
            f"Show {imagesShown} images on {imagesCount}, {selectedImagesCount} are selected"
        )

    def _sessionOfSelectedImages(
        self, selectedProxyIndexes: List[QtCore.QModelIndex]
    ) -> Optional[str]:
        """Get the session of the current images selection.

        Returns:
            None if no images selected, empty string if the selected images have empty
            or different sessions, session string if all selected images have the same
            session.
        """
        if len(selectedProxyIndexes) <= 0:
            # No images selected: return None.
            return None

        # At least one images is selected: check if they belong to the same session.
        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()
        session = None
        sameSession = True
        for proxyIndex in selectedProxyIndexes:
            sourceIndex = proxy.mapToSource(proxyIndex)
            # Initialize session to the first selected image's session.
            if session is None:
                session = model.data(sourceIndex, ImageModel.UserRoles.SessionRole)
                sameSession = True
                continue

            # For the next selected images: compare to the first one.
            if model.data(sourceIndex, ImageModel.UserRoles.SessionRole) == session:
                sameSession = True
                continue

            # Images with a different session is found: stop iteration.
            sameSession = False
            break

        if session and sameSession:
            # The selected images have all the same non-empty session.
            return session

        if session:
            # The selected images have different sessions.
            return "!="

        # The selected images have all an empty session.
        return ""

    def _updateSession(self, session: str) -> None:
        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()

        selectedIndexes = proxy.mapSelectionToSource(
            self.thumbnailView.selectionModel().selection()
        ).indexes()

        model.setDataRange(selectedIndexes, session, ImageModel.UserRoles.SessionRole)

        self.thumbnailView.selectionModel().clearSelection()
        self.sessionTxt.clear()
        self.applySessionBtn.setEnabled(False)


class ThumbnailView(QtWidgets.QListView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._possiblyPreserveSelectionPostClick = False

        # https://stackoverflow.com/questions/42673010/how-to-correctly-load-images-asynchronously-in-pyqt5
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setWrapping(True)
        self.setMovement(QtWidgets.QListView.Static)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setLayoutMode(QtWidgets.QListView.SinglePass)
        self.setGridSize(QtCore.QSize(CELL_WIDTH, CELL_HEIGHT))
        self.setUniformItemSizes(True)
        self.setMinimumWidth(4 * CELL_WIDTH + 24)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.setStyleSheet(
            f"QListView{{background-color: {QtGui.QColor(240, 240, 240).name()};}}"
        )

        self.contextMenu = QtWidgets.QMenu()
        self.markAsDownloadedAct = self.contextMenu.addAction("Mark as Downloaded")
        self.markAsDownloadedAct.setVisible(True)
        self.markAsDownloadedAct.setEnabled(False)
        self.markAsDownloadedAct.triggered.connect(self.markImagesAsDownloaded)

    @QtCore.pyqtSlot(QtCore.QItemSelection, QtCore.QItemSelection)
    def selectionChanged(
        self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ) -> None:
        """Reselect items if the user clicked a checkmark within an existing selection.

        Args:
            selected: new selection
            deselected: previous selection
        """

        super().selectionChanged(deselected, selected)

        if self._possiblyPreserveSelectionPostClick:
            # Must set this to False before adjusting the selection!
            self._possiblyPreserveSelectionPostClick = False

            current = self.currentIndex()
            if not (len(selected.indexes()) == 1 and selected.indexes()[0] == current):
                # Other items than the current one are selected: add the selection to
                # the deselected items and make the deselected items the new selection.
                deselected.merge(
                    self.selectionModel().selection(), QtCore.QItemSelectionModel.Select
                )
                self.selectionModel().select(
                    deselected, QtCore.QItemSelectionModel.Select
                )

    @QtCore.pyqtSlot(QtGui.QMouseEvent)
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Filter selection changes when click is on a thumbnail checkbox.

        When the user has selected multiple items (thumbnails), and
        then clicks one of the checkboxes, Qt's default behaviour is to
        treat that click as selecting the single item, because it doesn't
        know about our checkboxes. Therefore, if the user is in fact
        clicking on a checkbox, we need to filter that event.

        Does not apply to the clicked thumbnail as the delegate's editorEvent will still
        be triggered.

        Args:
            event: the mouse click event
        """
        rightButtonPressed = event.button() == QtCore.Qt.RightButton
        if rightButtonPressed:
            super().mousePressEvent(event)

        else:
            clickedProxyIndex = self.indexAt(event.pos())
            clickedRow = clickedProxyIndex.row()

            if clickedRow >= 0:
                rect = self.visualRect(clickedProxyIndex)
                delegate = self.itemDelegate(clickedProxyIndex)
                checkboxRect = delegate.getCheckboxRect(rect)
                checkboxClicked = checkboxRect.contains(event.pos())

                if checkboxClicked:
                    self._possiblyPreserveSelectionPostClick = True
                    proxy = self.model()
                    model = proxy.sourceModel()
                    selectedIndexes = proxy.mapSelectionToSource(
                        self.selectionModel().selection()
                    ).indexes()
                    clickedIndex = proxy.mapToSource(clickedProxyIndex)
                    state = model.data(clickedIndex, QtCore.Qt.CheckStateRole)
                    if len(selectedIndexes) > 1 and clickedIndex in selectedIndexes:
                        selection = [
                            index
                            for index in selectedIndexes
                            if not index == clickedIndex
                        ]
                        model.setDataRange(
                            selection,
                            False if state == QtCore.Qt.Checked else True,
                            QtCore.Qt.CheckStateRole,
                        )

            super().mousePressEvent(event)

    @QtCore.pyqtSlot(QtGui.QKeyEvent)
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Allow thumbnails' checkboxes activation with the keyboard.

        As Qt does not know about our checkboxes, this event filter traps the
        corresponding keys and reproduces the normal key behavior on checkboxes.

        Does not apply to the current thumbnail as the delegate's editorEvent will still
        be triggered.

        Args:
            event: the key event.
        """
        proxy = self.model()
        model = proxy.sourceModel()
        selectedIndexes = proxy.mapSelectionToSource(
            self.selectionModel().selection()
        ).indexes()
        if len(selectedIndexes) < 1 or event.key() not in (
            QtCore.Qt.Key_Space,
            QtCore.Qt.Key_Select,
        ):
            super().keyPressEvent(event)

        else:
            clickedIndex = proxy.mapToSource(self.currentIndex())
            state = model.data(clickedIndex, QtCore.Qt.CheckStateRole)
            selection = [
                index for index in selectedIndexes if not index == clickedIndex
            ]
            model.setDataRange(
                selection,
                False if state == QtCore.Qt.Checked else True,
                QtCore.Qt.CheckStateRole,
            )

            super().keyPressEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        """Determine if user can manually mark images as previously downloaded."""
        notDownloaded = self._oneOrMoreNotDownloaded()
        self.markAsDownloadedAct.setEnabled(notDownloaded)

        globalPos = self.mapToGlobal(event.pos())
        self.contextMenu.popup(globalPos)

    def setSelected(self, state: QtCore.Qt.CheckState) -> None:
        proxy = self.model()
        model = proxy.sourceModel()

        allIndexes = [
            proxy.mapToSource(proxy.index(i, 0)) for i in range(proxy.rowCount())
        ]

        if len(allIndexes) <= 0:
            return

        model.setDataRange(
            allIndexes,
            True if state == QtCore.Qt.Checked else False,
            QtCore.Qt.CheckStateRole,
        )

    @QtCore.pyqtSlot()
    def markImagesAsDownloaded(self) -> None:
        proxy = self.model()
        model = proxy.sourceModel()

        selectedIndexes = proxy.mapSelectionToSource(
            self.selectionModel().selection()
        ).indexes()

        if len(selectedIndexes) <= 0:
            return

        model.setDataRange(
            selectedIndexes, None, ImageModel.UserRoles.PreviouslyDownloadedRole
        )

    def selectImages(self) -> None:
        proxy = self.model()
        topleft = proxy.index(0, 0)
        bottomright = proxy.index(proxy.rowCount() - 1, 0)
        selection = QtCore.QItemSelection(topleft, bottomright)
        self.selectionModel().select(selection, QtCore.QItemSelectionModel.Select)

    def requestSession(self, sessionRequired: bool) -> None:
        """Set a flag on the item delagate and model to warn that a session is required.

        Args:
            sessionRequired: True if a session is required by the selected naming
                template.
        """
        self.itemDelegate().sessionRequired = sessionRequired
        self.model().sourceModel().sessionRequired = sessionRequired
        self.viewport().repaint()

    def _oneOrMoreNotDownloaded(self) -> bool:
        selectedIndexes = self.selectedIndexes()

        if selectedIndexes is None:
            return False

        else:
            return any(
                [
                    not index.data(ImageModel.UserRoles.PreviouslyDownloadedRole)
                    for index in selectedIndexes
                ]
            )


class ThumbnailFilterProxyModel(QtCore.QSortFilterProxyModel):

    _isDateFilterOn: bool = False
    _timeRangeFilter: List["TimeRange"] = [TimeRange()]
    _isNewFilterOn: bool = False

    @classmethod
    def timeRangeFilter(cls) -> List["TimeRange"]:
        return cls._timeRangeFilter

    def setTimeRangeFilter(self, value: List["TimeRange"]) -> None:
        if not value:
            value = [TimeRange()]
        ThumbnailFilterProxyModel._timeRangeFilter = value
        self.invalidateFilter()

    @classmethod
    def isDateFilterOn(cls) -> bool:
        return cls._isDateFilterOn

    def setIsDateFilterOn(self, value: bool) -> None:
        ThumbnailFilterProxyModel._isDateFilterOn = value
        self.invalidateFilter()

    @classmethod
    def isNewFilterOn(cls) -> bool:
        return cls._isNewFilterOn

    def setIsNewFilterOn(self, value: bool) -> None:
        ThumbnailFilterProxyModel._isNewFilterOn = value
        self.invalidateFilter()

    def filterAcceptsRow(
        self, sourceRow: int, sourceParent: QtCore.QModelIndex
    ) -> bool:
        okDate = True
        model = self.sourceModel()

        if self.isDateFilterOn():
            index = model.index(sourceRow, 0, sourceParent)
            dateTime = model.data(index, ImageModel.UserRoles.DateTimeRole)
            if dateTime:
                okDate = any(
                    [tr.start <= dateTime <= tr.end for tr in self.timeRangeFilter()]
                )

        isNew = True
        if self.isNewFilterOn():
            index = model.index(sourceRow, 0, sourceParent)
            isNew = not model.data(index, ImageModel.UserRoles.PreviouslyDownloadedRole)

        return okDate and isNew
