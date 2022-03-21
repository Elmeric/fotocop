import logging
from enum import IntEnum
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models import settings as Config
from fotocop.models.sources import Selection
from fotocop.models.timeline import TimeRange
from .timelineviewer import tlv

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
CELL_WIDTH = CELL_IN_WIDTH + 2 * CELL_MARGIN
CELL_HEIGHT = CELL_IN_HEIGHT + 2 * CELL_MARGIN
THUMB_MARGIN = (CELL_IN_WIDTH - THUMB_HEIGHT) / 2


class ImageModel(QtCore.QAbstractListModel):
    class UserRoles(IntEnum):
        ThumbnailRole = QtCore.Qt.UserRole + 1
        DateTimeRole = QtCore.Qt.UserRole + 2
        SessionRole = QtCore.Qt.UserRole + 3
        PreviouslyDownloadedRole = QtCore.Qt.UserRole + 4

    def __init__(self, images: List["Image"] = None, parent=None):
        super().__init__(parent)

        self.images = images or list()
        self.sessionRequired = False

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return len(self.images)

    def flags(self, index):
        if index.isValid():
            return super().flags(index) | QtCore.Qt.ItemIsUserCheckable  # noqa
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

        if role == ImageModel.UserRoles.ThumbnailRole:
            return images[row].getThumbnail()

        if role == ImageModel.UserRoles.DateTimeRole:
            datetime_ = images[row].datetime
            if datetime_:
                return tuple([int(e) for e in datetime_])
            else:
                return None

        if role == ImageModel.UserRoles.SessionRole:
            return images[row].session

        if role == ImageModel.UserRoles.PreviouslyDownloadedRole:
            return images[row].isPreviouslyDownloaded

        if role == QtCore.Qt.ToolTipRole:
            image = images[row]
            name = image.name
            datetime_ = image.datetime
            if datetime_:
                takenOn = datetime_.asDatetime().strftime("%a %d %b %Y %I:%M:%S %p")
            else:
                takenOn = ""
            session = image.session

            tip = f"<b>{name}</b><br>Taken on {takenOn}"

            previouslyDownloaded = image.isPreviouslyDownloaded
            if previouslyDownloaded:
                downloadPath = image.downloadPath
                downloadTime = image.downloadTime.strftime("%a %d %b %Y %I:%M:%S %p")
                if downloadPath != ".":
                    downloadName = Path(downloadPath).name
                    downloadPath = Path(downloadPath).parent
                    tip += f"<br><br>Previously downloaded as:<br>{downloadName}<br>{downloadPath}<br>{downloadTime}"
                else:
                    tip += f"<br><br><i>Manually set as previously downloaded on {downloadTime}</i>"

            if session:
                tip += f"<br><br>Session: {session}"
            elif self.sessionRequired and image.isSelected:
                tip += f"<br><br><i>A session is required!</i>"

            return tip

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
            image.isSelected = True if value == QtCore.Qt.Checked else False
            self.dataChanged.emit(index, index, (role,))
            return True

        if role == ImageModel.UserRoles.SessionRole:
            self.images[row].session = value
            self.dataChanged.emit(index, index, (role,))
            return True

        if role == ImageModel.UserRoles.PreviouslyDownloadedRole:
            image = self.images[row]
            image.markAsPreviouslyDownloaded()
            self.dataChanged.emit(index, index, (role,))
            return True

        return False

    def clearImages(self):
        self.beginResetModel()
        self.images = list()
        self.endResetModel()

    def addImages(self, images: List["Image"]):
        row = self.rowCount()
        self.beginInsertRows(QtCore.QModelIndex(), row, row + len(images) - 1)
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
            self.dataChanged.emit(
                index,
                index,
                (ImageModel.UserRoles.ThumbnailRole, ImageModel.UserRoles.DateTimeRole),
            )


class ThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        resources = Config.fotocopSettings.resources
        self.dummyImage = QtGui.QPixmap(f"{resources}/dummy-image.png")
        self.sessionRequired = False

    def paint(self, painter, option, index):
        imageName = index.data(QtCore.Qt.DisplayRole)
        imageSession = index.data(ImageModel.UserRoles.SessionRole)
        imageIsSelected = index.data(QtCore.Qt.CheckStateRole) == QtCore.Qt.Checked
        imageThumb, aspectRatio, orientation = index.data(
            ImageModel.UserRoles.ThumbnailRole
        )
        previouslyDownloaded = index.data(ImageModel.UserRoles.PreviouslyDownloadedRole)

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

        if (
            previouslyDownloaded
            and not imageIsSelected
            # and download_status == DownloadStatus.not_downloaded
        ):
            # Add dimming on the image pixmap
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

        state = index.data(QtCore.Qt.CheckStateRole)
        bgdColor = (
            QtGui.QColor("aliceblue")
            if state == QtCore.Qt.Checked
            else QtGui.QColor("lightgray")
        )

        painter.fillRect(cellRect, bgdColor)

        painter.drawPixmap(target, px, source)
        painter.drawText(textRect, QtCore.Qt.AlignCenter, imageName)
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

    zoomLevelChanged = QtCore.pyqtSignal(tlv.ZoomLevel)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._sourceSelection = None

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

        newChk = QtWidgets.QCheckBox()
        newChk.setText("New only")

        selectWidget = QtWidgets.QWidget()
        self.allBtn = QtWidgets.QPushButton("All")
        self.allBtn.setToolTip("Select all images")
        self.allBtn.setStatusTip("Select all images")
        self.noneBtn = QtWidgets.QPushButton("None")
        self.noneBtn.setToolTip("Deselect all images")
        self.noneBtn.setStatusTip("Deselect all images")
        selectLayout = QtWidgets.QHBoxLayout()
        selectLayout.setContentsMargins(0, 0, interToolsSpacing, 0)
        selectLayout.addWidget(self.allBtn)
        selectLayout.addWidget(self.noneBtn)
        selectWidget.setLayout(selectLayout)

        filterWidget = QtWidgets.QWidget()
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

        self.toolbar.addWidget(newChk)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(selectWidget)
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
        self.thumbnailView.markAsDownloadedAct.triggered.connect(
            self.doMarkAsDownloadedAct
        )
        newChk.toggled.connect(self.toggleNewOnly)
        self.allBtn.clicked.connect(lambda: self.setSelected(QtCore.Qt.Checked))
        self.noneBtn.clicked.connect(lambda: self.setSelected(QtCore.Qt.Unchecked))
        self.filterBtn.toggled.connect(self.toggleFilter)
        self.zoomLevelSelector.activated.connect(
            lambda: self.zoomLevelChanged.emit(self.zoomLevelSelector.currentData())
        )
        self.sessionTxt.textEdited.connect(self.checkSession)
        self.sessionTxt.returnPressed.connect(self.applySession)
        self.applySessionBtn.clicked.connect(self.applySession)
        self.removeSessionBtn.clicked.connect(self.removeSession)

        self.allBtn.setEnabled(False)
        self.noneBtn.setEnabled(False)
        self.filterBtn.setChecked(False)
        self.filterBtn.setEnabled(False)
        self.selStatusLbl.hide()
        self.applySessionBtn.setEnabled(False)
        self.removeSessionBtn.setEnabled(False)
        self.zoomLevelSelector.setEnabled(False)

    @QtCore.pyqtSlot(Selection)
    def setSourceSelection(self, selection):
        self._sourceSelection = selection
        self.filterBtn.setChecked(False)
        self.thumbnailView.model().sourceModel().clearImages()
        self.thumbnailView.model().setTimeRangeFilter([TimeRange()])
        self.allBtn.setEnabled(False)
        self.noneBtn.setEnabled(False)
        self.filterBtn.setEnabled(False)
        self.selStatusLbl.hide()
        self.zoomLevelSelector.setEnabled(False)

    @QtCore.pyqtSlot(dict)
    def addImages(self, images):
        images = list(images.values())
        self.thumbnailView.model().sourceModel().addImages(images)
        self.allBtn.setEnabled(True)
        self.noneBtn.setEnabled(True)

    @QtCore.pyqtSlot(str)
    def updateImage(self, imageKey: str):
        self.thumbnailView.model().sourceModel().updateImage(imageKey)

    def setSelected(self, state: QtCore.Qt.CheckState):
        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()
        for i in range(proxy.rowCount()):
            proxyIndex = proxy.index(i, 0)
            model.setData(
                proxy.mapToSource(proxyIndex), state, QtCore.Qt.CheckStateRole
            )

    @QtCore.pyqtSlot(QtCore.QModelIndex, QtCore.QModelIndex, "QVector<int>")
    def onImageModelChanged(
        self,
        _topleft: QtCore.QModelIndex,
        _bottomright: QtCore.QModelIndex,
        roles: List[int],
    ):
        if (
            QtCore.Qt.CheckStateRole in roles
            or ImageModel.UserRoles.PreviouslyDownloadedRole in roles
        ):
            self._updateSelStatus()

    @QtCore.pyqtSlot()
    def doMarkAsDownloadedAct(self) -> None:
        selectedProxyIndexes = self.thumbnailView.selectionModel().selection().indexes()

        if selectedProxyIndexes is None:
            return

        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()
        role = ImageModel.UserRoles.PreviouslyDownloadedRole
        for proxyIndex in selectedProxyIndexes:
            index = proxy.mapToSource(proxyIndex)
            if not index.data(role):
                model.setData(index, True, role)

    @QtCore.pyqtSlot(bool)
    def toggleNewOnly(self, checked: bool):
        self.thumbnailView.model().setIsNewFilterOn(checked)
        self._updateSelStatus()

    @QtCore.pyqtSlot(bool)
    def toggleFilter(self, checked: bool):
        self.thumbnailView.model().setIsDateFilterOn(checked)
        self._updateSelStatus()

    @QtCore.pyqtSlot(tlv.ZoomLevel)
    def onZoomLevelChanged(self, zoomLevel: tlv.ZoomLevel):
        self.zoomLevelSelector.setCurrentText(zoomLevel.name)

    @QtCore.pyqtSlot(str, int)
    def showNodeInfo(self, nodeKey: str, nodeWeight: int):
        mainWindow = QtUtil.getMainWindow()
        if nodeKey:
            mainWindow.showStatusMessage(f"{nodeKey}: {nodeWeight} images")

    @QtCore.pyqtSlot(list)
    def updateTimeRange(self, timeRange: List["TimeRange"]):
        if timeRange:
            self.filterBtn.setChecked(True)
        else:
            self.filterBtn.setChecked(False)
        self.thumbnailView.model().setTimeRangeFilter(timeRange)
        self._updateSelStatus()
        self._selectImages()
        self.sessionTxt.selectAll()
        self.sessionTxt.setFocus()

    @QtCore.pyqtSlot()
    def activateDateFilter(self):
        self.filterBtn.setChecked(False)
        self.filterBtn.setEnabled(True)
        self.selStatusLbl.show()
        self.zoomLevelSelector.setEnabled(True)
        self._updateSelStatus()

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
    def checkSession(self, text: str):
        selectedProxyIndexes = self.thumbnailView.selectionModel().selection().indexes()
        nonEmptySelection = len(selectedProxyIndexes) > 0

        # Session can be applied if non-empty and at least one image is selected.
        ok = text != "" and nonEmptySelection
        self.applySessionBtn.setEnabled(ok)

        # In all cases, indicates the selected images count if not null.
        applyCount = f" ({len(selectedProxyIndexes)})" if nonEmptySelection else ""
        self.applySessionBtn.setText(f"Apply{applyCount}")

    @QtCore.pyqtSlot()
    def applySession(self):
        selectedProxyIndexes = self.thumbnailView.selectionModel().selection().indexes()
        session = self.sessionTxt.text()
        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()
        for proxyIndex in selectedProxyIndexes:
            model.setData(
                proxy.mapToSource(proxyIndex), session, ImageModel.UserRoles.SessionRole
            )
        self.thumbnailView.selectionModel().clearSelection()
        self.sessionTxt.clear()
        self.applySessionBtn.setEnabled(False)

    @QtCore.pyqtSlot()
    def removeSession(self):
        selectedProxyIndexes = self.thumbnailView.selectionModel().selection().indexes()
        proxy = self.thumbnailView.model()
        model = proxy.sourceModel()
        for proxyIndex in selectedProxyIndexes:
            model.setData(
                proxy.mapToSource(proxyIndex), "", ImageModel.UserRoles.SessionRole
            )
        self.thumbnailView.selectionModel().clearSelection()
        self.sessionTxt.clear()
        self.applySessionBtn.setEnabled(False)

    @QtCore.pyqtSlot(bool)
    def requestSession(self, sessionRequired: bool) -> None:
        thumbnailView = self.thumbnailView
        thumbnailView.itemDelegate().sessionRequired = sessionRequired
        thumbnailView.model().sourceModel().sessionRequired = sessionRequired
        thumbnailView.viewport().repaint()

    def _updateSelStatus(self):
        imagesCount = self.thumbnailView.model().sourceModel().rowCount()
        imagesShown = self.thumbnailView.model().rowCount()
        selectedImagesCount = self._sourceSelection.selectedImagesCount
        self.selStatusLbl.setText(
            f"Show {imagesShown} images on {imagesCount}, {selectedImagesCount} are selected"
        )

    def _selectImages(self):
        thumbnailView = self.thumbnailView
        proxy = thumbnailView.model()
        topleft = proxy.index(0, 0)
        bottomright = proxy.index(proxy.rowCount() - 1, 0)
        selection = QtCore.QItemSelection(topleft, bottomright)
        thumbnailView.selectionModel().select(
            selection, QtCore.QItemSelectionModel.Select
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


class ThumbnailView(QtWidgets.QListView):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.possiblyPreserveSelectionPostClick = False

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

        self.contextMenu = QtWidgets.QMenu()
        self.markAsDownloadedAct = self.contextMenu.addAction("Mark as Downloaded")
        self.markAsDownloadedAct.setVisible(True)
        self.markAsDownloadedAct.setEnabled(False)

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

        On some versions of Qt 5 (to be determined), no matter what we do here,
        the delegate's editorEvent will still be triggered.

        Args:
            event: the mouse click event
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
                    self.possiblyPreserveSelectionPostClick = True
                    selected = self.selectionModel().selection()
                    model = self.model()
                    state = model.data(clickedIndex, QtCore.Qt.CheckStateRole)
                    state = (
                        QtCore.Qt.Unchecked
                        if state == QtCore.Qt.Checked
                        else QtCore.Qt.Checked
                    )
                    if (
                        len(selected.indexes()) > 1
                        and clickedIndex in selected.indexes()
                    ):
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
        know about our checkboxes. Therefore, if the user is in fact
        clicking on a checkbox, we need to filter that event.

        On some versions of Qt 5 (to be determined), no matter what we do here,
        the delegate's editorEvent will still be triggered.

        Args:
            event: the mouse click event
        """
        selectedIndexes = self.selectionModel().selection().indexes()
        if len(selectedIndexes) < 1 or event.key() not in (
            QtCore.Qt.Key_Space,
            QtCore.Qt.Key_Select,
        ):
            super().keyPressEvent(event)

        else:
            clickedIndex = self.currentIndex()
            model = self.model()
            state = model.data(clickedIndex, QtCore.Qt.CheckStateRole)
            state = (
                QtCore.Qt.Unchecked if state == QtCore.Qt.Checked else QtCore.Qt.Checked
            )
            for index in selectedIndexes:
                if not index == clickedIndex:
                    model.setData(index, state, QtCore.Qt.CheckStateRole)

            super().keyPressEvent(event)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        # Determine if user can manually mark images as previously downloaded
        notDownloaded = self._oneOrMoreNotDownloaded()
        self.markAsDownloadedAct.setEnabled(notDownloaded)

        globalPos = self.mapToGlobal(event.pos())
        self.contextMenu.popup(globalPos)

    def _oneOrMoreNotDownloaded(self) -> bool:
        selectedIndexes = self.selectedIndexes()

        if selectedIndexes is None:
            return False

        else:
            notDownloaded = False
            for index in selectedIndexes:
                if not index.data(ImageModel.UserRoles.PreviouslyDownloadedRole):
                    notDownloaded = True
                    break
            return notDownloaded


class ThumbnailFilterProxyModel(QtCore.QSortFilterProxyModel):

    _isDateFilterOn: bool = False
    _timeRangeFilter: List["TimeRange"] = [TimeRange()]
    _isNewFilterOn: bool = False

    @classmethod
    def timeRangeFilter(cls) -> List["TimeRange"]:
        return cls._timeRangeFilter

    def setTimeRangeFilter(self, value: List["TimeRange"]):
        if not value:
            value = [TimeRange()]
        ThumbnailFilterProxyModel._timeRangeFilter = value
        self.invalidateFilter()

    @classmethod
    def isDateFilterOn(cls) -> bool:
        return cls._isDateFilterOn

    def setIsDateFilterOn(self, value: bool):
        ThumbnailFilterProxyModel._isDateFilterOn = value
        self.invalidateFilter()

    @classmethod
    def isNewFilterOn(cls) -> bool:
        return cls._isNewFilterOn

    def setIsNewFilterOn(self, value: bool):
        ThumbnailFilterProxyModel._isNewFilterOn = value
        self.invalidateFilter()

    def filterAcceptsRow(
        self, sourceRow: int, sourceParent: QtCore.QModelIndex
    ) -> bool:
        okDate = True

        if self.isDateFilterOn():
            index = self.sourceModel().index(sourceRow, 0, sourceParent)
            dateTime = self.sourceModel().data(index, ImageModel.UserRoles.DateTimeRole)
            if dateTime:
                dateTime = datetime(*dateTime)
                okDate = any(
                    [tr.start <= dateTime <= tr.end for tr in self.timeRangeFilter()]
                )

        isNew = True
        if self.isNewFilterOn():
            index = self.sourceModel().index(sourceRow, 0, sourceParent)
            isNew = not self.sourceModel().data(
                index, ImageModel.UserRoles.PreviouslyDownloadedRole
            )

        return okDate and isNew
