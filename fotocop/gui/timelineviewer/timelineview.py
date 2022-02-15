from typing import List

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.util import qtutil as QtUtil
from fotocop.models.timeline import SelectionFlag, SelectionState
from . import tlv


class TimelineView(QtWidgets.QGraphicsView):

    zoomed = QtCore.pyqtSignal(tlv.ZoomLevel)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.zoomLevel = tlv.DEFAULT_ZOOM_LEVEL

        self._selectionInProgress = False
        self._firstSelectedItem = None
        self._selectionOrigin = QtCore.QPoint()
        self._rubberBand = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self._preselectedItems = list()

        self.setMouseTracking(True)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QtGui.QPainter.Antialiasing)

        self.setAlignment(QtCore.Qt.AlignLeft)
        self.setViewportMargins(0, 0, 0, 0)

        self.setViewportUpdateMode(QtWidgets.QGraphicsView.FullViewportUpdate)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        # self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)

        self.setBackgroundBrush(QtGui.QColor(240, 240, 240))

        self.clearSelectionAction = QtWidgets.QAction("Clear Selection", self)
        self.clearSelectionAction.setShortcut(
            QtGui.QKeySequence(QtCore.Qt.SHIFT + QtCore.Qt.Key_Escape)
        )
        self.addAction(self.clearSelectionAction)

    def setScene(self, scene: QtWidgets.QGraphicsScene):
        super().setScene(scene)
        if scene:
            # Disconnect clearSelectionAction from previous scene if any and reconnect
            # to the new scene.
            QtUtil.reconnect(self.clearSelectionAction.triggered, scene.clearSelection)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        self.fitInView(
            QtCore.QRectF(0, 0, event.size().width(), tlv.MAX_BAR_HEIGHT),
            QtCore.Qt.KeepAspectRatioByExpanding,
        )
        self.ensureVisible(QtCore.QRectF(0, 0, 100, tlv.MAX_BAR_HEIGHT), 0, 0)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            # Start a selection.
            scene = self.scene()
            # Avoid timeline access while being updated
            if scene.isLoaded:
                event.accept()
                posView = event.pos()
                # Translate the selected position to the timeline bottom to favor child
                # selection besides parent.
                posView.setY(tlv.MAX_BAR_HEIGHT)
                item = self.itemAt(posView)
                if item is not None:
                    # A node is under the mouse: enter in selection mode and remember it
                    # and the selection origin in scene coordinates.
                    self._selectionInProgress = True
                    self._firstSelectedItem = item
                    self._selectionOrigin = self.mapToScene(posView).toPoint()
                    # Set the timeline in preselection mode.
                    scene.timeline.setPreselectionMode(isPresel=True)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        # https://stackoverflow.com/questions/4753681/how-to-pan-images-in-qgraphicsview
        # https://www.qtcentre.org/threads/10741-Rubberband-relative-to-QGraphicsScene
        if int(event.buttons()) & QtCore.Qt.LeftButton:
            if self._selectionInProgress:
                # Enter in rubberband selection mode, with preselection state indication
                event.accept()
                controlPressed = event.modifiers() == QtCore.Qt.ControlModifier
                scene = self.scene()
                posView = event.pos()
                # Translate the current position to the timeline top to make the
                # rubberband covering the whole timeline height.
                posView.setY(0)
                rubberRect = QtCore.QRect(
                    self.mapFromScene(self._selectionOrigin),
                    posView
                ).normalized()
                self._rubberBand.setGeometry(rubberRect)

                if not self._rubberBand.isVisible():
                    # Show the rubberband and initialize the preselection according to
                    # the selection mode:
                    #   normal: all selected items, except the first selected one, will
                    #       be deselected
                    #   extended (Control key is pressed): all selected items are kept
                    #       and will be toggled if required by preselection.
                    self._rubberBand.show()
                    if controlPressed:
                        self._preselectedItems = list()
                    else:
                        selection = scene.timeline.selectionModel()
                        self._preselectedItems = [
                            item
                            for item in self.items()
                            if (not item == self._firstSelectedItem and
                                selection.selectionState(item.node.timelineNode) in (
                                    SelectionState.Selected, SelectionState.PartiallySelected
                                )
                                )
                        ]

                else:
                    # Scroll the timeline view if required.
                    if posView.x() > 0.75 * self.width():
                        value = self.horizontalScrollBar().value()
                        self.horizontalScrollBar().setValue(value + 5)
                    elif posView.x() < 0.25 * self.width():
                        value = self.horizontalScrollBar().value()
                        self.horizontalScrollBar().setValue(value - 5)

                    # Retrieves items in the rubberband. A non-leaf item is excluded if
                    # at least one of its children is also in the rubberband.
                    selectedItems = self._getSelectedItemsInRect(rubberRect)

                    # Search items that are new in preselection and items that are no
                    # more in preselection.
                    previousPresel = self._preselectedItems
                    inTimelineNodes = [
                        item.node.timelineNode
                        for item in selectedItems
                        if item not in previousPresel
                    ]
                    outTimelineNodes = [
                        item.node.timelineNode
                        for item in previousPresel
                        if item not in selectedItems
                    ]
                    self._preselectedItems = selectedItems

                    # Update selection state of items that are no more in preselection.
                    if outTimelineNodes:
                        command = SelectionFlag.Toggle if controlPressed else SelectionFlag.Deselect
                        scene.timeline.selectionModel().select(outTimelineNodes, command)
                    # Update selection state of items that are new in preselection.
                    if inTimelineNodes:
                        command = SelectionFlag.Toggle if controlPressed else SelectionFlag.Select
                        scene.timeline.selectionModel().select(inTimelineNodes, command)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        if event.button() == QtCore.Qt.LeftButton:
            if self._selectionInProgress:
                # Selection is done: apply it to the timeline.
                event.accept()
                controlPressed = event.modifiers() == QtCore.Qt.ControlModifier
                scene = self.scene()

                # Quit the timeline preselection mode.
                scene.timeline.setPreselectionMode(isPresel=False)

                # Retrieve selected items
                if self._rubberBand.isVisible():
                    # Rubberband selection: selected items are the ones in the rubberband.
                    selectedItems = self._getSelectedItemsInRect(self._rubberBand.geometry())
                    if not selectedItems:
                        # To handle the rare case where rubberband width is null.
                        selectedItems = [self._firstSelectedItem]
                    # Exit the rubberband selection mode by hiding the rubberband.
                    self._rubberBand.hide()
                else:
                    # Normal selection: selected items is the first selected one.
                    selectedItems = [self._firstSelectedItem]

                # Update selection state of the selected items.
                selectedTimelineNodes = [item.node.timelineNode for item in selectedItems]
                if controlPressed:
                    command = SelectionFlag.Toggle
                else:
                    command = SelectionFlag.ClearAndSelect
                scene.timeline.selectionModel().select(selectedTimelineNodes, command)

                # Exit selection mode
                self._firstSelectedItem = None
                self._selectionInProgress = False

                # print(f"Selected time ranges: {scene.timeline.selectionModel().selectedRanges()}")
        else:
            super().mouseReleaseEvent(event)

    def _getSelectedItemsInRect(self, rect: QtCore.QRect) -> List[QtWidgets.QGraphicsItem]:
        # Retrieves items in rect. A non-leaf item is excluded if at least one of its
        # children is also in the rect.
        selectedItems = self.scene().items(self.mapToScene(rect).boundingRect())
        selectedItems = [
            item for item in selectedItems
            # item is a branch node and none of its children is selected: keep it
            if all([childItem not in selectedItems for childItem in item.childItems()])
        ]
        return selectedItems

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        pos = event.pos()
        item = self.itemAt(pos)

        if item:
            self.centerOn(item.mapToScene(item.boundingRect().center()))
        else:
            self.centerOn(self.mapToScene(pos))

    def wheelEvent(self, event: QtGui.QWheelEvent):
        """Zoom in / out according to the mouse wheel move.

        Args:
            event: the trapped mouse wheel event
        """
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return

        if delta > 0.0:
            # Scale up
            zoom = tlv.ZoomLevel(min(tlv.ZoomLevel.DAY, self.zoomLevel + 1))
        else:
            # Scale down
            zoom = tlv.ZoomLevel(max(tlv.ZoomLevel.YEAR, self.zoomLevel - 1))
        if zoom != self.zoomLevel:
            self.zoom(zoom)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Change the drag mode to a rubber band when Shift key is pressed.

        Args:
            event: the trapped key event
        """
        if event.key() == QtCore.Qt.Key_Shift:
            self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        """Revert the drag mode to scrolling when Shift key is released.

        Args:
            event: the trapped key event
        """
        if event.key() == QtCore.Qt.Key_Shift:
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)

        super().keyReleaseEvent(event)

    @QtCore.pyqtSlot(tlv.ZoomLevel)
    def zoom(self, value: tlv.ZoomLevel):
        if value != self.zoomLevel:
            self.zoomLevel = value
            self.update()
            self.zoomed.emit(value)
