from typing import Tuple, Optional, Any, List, Union
from enum import IntEnum

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models import settings as Config
from fotocop.models.timeline import Timeline, TimelineNode, NodeKind
from fotocop.models.sources import Selection


class ZoomLevel(IntEnum):
    YEAR = 1
    MONTH = 2
    DAY = 3


class TimelineViewer(QtWidgets.QWidget):

    zoomed = QtCore.pyqtSignal(ZoomLevel)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._timeline = None
        scene = FlowChainScene(parent=self)
        self._emptyScene = scene

        self._zoomLevel = ZoomLevel.YEAR

        resources = Config.fotocopSettings.resources
        # jsonStyle = Config.fotocopSettings.appDirs.user_config_dir / 'flow_chain_style.json'

        self.setMinimumHeight(100)

        # self._style = StyleCollection.fromJson(jsonStyle)
        self._view = FlowChainView(parent=self)
        self._view.setScene(scene)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._view)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        # Force size computation even if the viewer is hidden
        layout.invalidate()
        layout.activate()

        self._view.zoomed.connect(self.onZoomLevelChanged)

    @QtCore.pyqtSlot(Selection)
    def onSourceSelected(self, selection):
        self.setTimeline(selection.timeline)

    @QtCore.pyqtSlot(TimelineNode)
    def updateTimeline(self, timeline: Timeline):
        scene = self._view.scene()
        scene.clear()
        # print("Scene cleared")
        scene.populate(timeline)

    @QtCore.pyqtSlot(ZoomLevel)
    def zoom(self, zoomLevel: ZoomLevel):
        if zoomLevel != self._zoomLevel:
            self._zoomLevel = zoomLevel
            self._view.zoom(zoomLevel)

    @QtCore.pyqtSlot(ZoomLevel)
    def onZoomLevelChanged(self, zoomLevel: ZoomLevel):
        if zoomLevel != self._zoomLevel:
            self._zoomLevel = zoomLevel
            self.zoomed.emit(zoomLevel)

    def setTimeline(self, timeline: Timeline):
        if timeline.childCount() > 0:
            self._timeline = timeline
            scene = FlowChainScene(parent=self)
            scene.populate(timeline)
            self._view.setScene(scene)
        else:
            self._timeline = None
            scene = self._emptyScene
            scene.clear()
            self._view.setScene(scene)


class FlowChainView(QtWidgets.QGraphicsView):

    zoomed = QtCore.pyqtSignal(ZoomLevel)

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self._zoom = ZoomLevel.YEAR
        self._lastPos = None
        self._panning = False

        resources = Config.fotocopSettings.resources

        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QtGui.QPainter.Antialiasing)

        self.setAlignment(QtCore.Qt.AlignLeft)
        self.setViewportMargins(0, 0, 0, 0)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)

        self.setBackgroundBrush(QtGui.QColor(240, 240, 240))

        self.clearSelectionAction = QtWidgets.QAction('Clear Selection', self)
        self.clearSelectionAction.setShortcut(QtGui.QKeySequence(QtCore.Qt.SHIFT + QtCore.Qt.Key_Escape))
        # self.clearSelectionAction.setShortcut(QtGui.QKeySequence.Cancel)
        self.addAction(self.clearSelectionAction)

    def setScene(self, scene: QtWidgets.QGraphicsScene):
        super().setScene(scene)
        if scene:
            self.clearSelectionAction.triggered.connect(scene.clearSelection)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        # print(f"View height: {self.height()}")
        # print(f"View viewport height: {self.viewport().height()}")
        self.fitInView(QtCore.QRectF(0, 0, event.size().width(), 100), QtCore.Qt.KeepAspectRatioByExpanding)
        self.ensureVisible(QtCore.QRectF(0, 0, 100, 100), 0, 0)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        pos = event.pos()
        item = self.itemAt(pos)

        if item and isinstance(item, NodeGraphicsObject):
            item.setSelected(False)
            for child in item.childItems():
                child.setSelected(False)
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
            zoom = ZoomLevel(min(ZoomLevel.DAY, self._zoom + 1))
        else:
            # Scale down
            zoom = ZoomLevel(max(ZoomLevel.YEAR, self._zoom - 1))
        if zoom != self._zoom:
            self._zoom = zoom
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

    @QtCore.pyqtSlot(ZoomLevel)
    def zoom(self, value: ZoomLevel):
        self.scene().zoom = value
        self._zoom = value
        self.update()
        print(f"Current zoom factor is: {value.name}")
        self.zoomed.emit(value)


class NodeGeometry:

    MIN_BAR_HEIGHT = 20

    def __init__(self, node: 'Node', offset: int):
        super().__init__()
        self.offset = offset
        self.width = 100
        self.height = 100
        self.barWidth = 15
        self.spacing = 5
        self.hovered = False

        self._node = node

        f = QtGui.QFont()
        self._fontMetrics = QtGui.QFontMetrics(f)

        f.setBold(True)
        self._boldFontMetrics = QtGui.QFontMetrics(f)

    @property
    def size(self) -> QtCore.QSizeF:
        return QtCore.QSizeF(self.width, self.height)

    @property
    def boundingRect(self) -> QtCore.QRectF:
        """The node bounding rect, including its ports (addon)
        """
        return QtCore.QRectF(
            0,
            0,
            self.width,
            self.height
        )

    @property
    def captionHeight(self) -> int:
        return self._boldFontMetrics.boundingRect(self._node.caption).height() + 2*self.spacing

    @property
    def captionWidth(self) -> int:
        return self._boldFontMetrics.boundingRect(self._node.caption).width()

    def recalculateSize(self, lod: float):
        timelineNode = self._node.timelineNode
        kind = timelineNode.kind

        if kind == NodeKind.YEAR:
            self.width = self.captionHeight + timelineNode.childCount() * self.barWidth
            self.height = 100

        elif kind == NodeKind.MONTH:
            parent = timelineNode.parent
            weightScale = (100 - NodeGeometry.MIN_BAR_HEIGHT) / parent.parent.maxGrandChildrenWeight
            self.width = self.barWidth
            self.height = NodeGeometry.MIN_BAR_HEIGHT + timelineNode.weight * weightScale
            self._node.graphicsObject.setPos(self.offset, 100 - self.height)

        else:
            self._node.graphicsObject.hide()


class NodeGraphicsObject(QtWidgets.QGraphicsObject):
    node: 'Node'
    _scene: 'FlowChainScene'

    def __init__(self, scene: "FlowChainScene", node: "Node", parent: "Node" = None):
        if parent is not None:
            parent = parent.graphicsObject
        super().__init__(parent)

        self.node = node

        self._scene = scene

        self.setFlag(QtWidgets.QGraphicsItem.ItemDoesntPropagateOpacityToChildren, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsScenePositionChanges, True)

        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

        self.setAcceptHoverEvents(True)

        self.setZValue(0)

        self.setToolTip(node.id)

    def boundingRect(self) -> QtCore.QRectF:
        return self.node.geometry.boundingRect

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Make the node highlighted when hovered.

        Change the cursor to a pointing hand.
        The node will be drawn in hovered representation.
        """
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        node = self.node
        if node.kind == NodeKind.MONTH:
            node.geometry.hovered = True
            self.update()
        event.accept()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Reset the hovered epresentation and cursor to default.
        """
        self.setCursor(QtGui.QCursor())
        node = self.node
        if node.kind == NodeKind.MONTH:
            node.geometry.hovered = False
            self.update()
        event.accept()

    def paint(self,
              painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: QtWidgets.QWidget = None):
        node = self.node
        geometry = node.geometry
        geometry.recalculateSize(option.levelOfDetailFromTransform(painter.worldTransform()))

        painter.setClipRect(option.exposedRect)
        NodeGraphicsObject.drawNodeRect(painter, geometry, self.node.color, self.isSelected())
        if node.kind == NodeKind.YEAR:
            NodeGraphicsObject.drawNodeCaption(painter, geometry, node.id)

    @classmethod
    def drawNodeRect(
            cls,
            painter: QtGui.QPainter,
            geometry: NodeGeometry,
            nodeColor: QtGui.QColor,
            isSelected: bool):
        """Draw node rect.

        Args:
            painter : the node painter.
            geometry : the node geometry.
            nodeColor: the node color.
            isSelected: True if the node is selected.
        """
        color = QtGui.QColor("deepskyblue") if isSelected else nodeColor
        color = color.darker(150) if geometry.hovered else color

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)

        painter.drawRect(QtCore.QRectF(0, 0, geometry.width, geometry.height))

    @classmethod
    def drawNodeCaption(
            cls,
            painter: QtGui.QPainter,
            geometry: NodeGeometry,
            caption: str):
        """Draw the node caption.

        Args:
            painter : the node painter.
            geometry : the node geometry.
            caption: the node caption.
        """
        # caption box geometry
        cbWitdth = geometry.captionHeight
        cbHeight = geometry.height
        painter.setPen(QtGui.QColor(64, 64, 64))

        f = painter.font()
        f.setBold(True)
        metrics = QtGui.QFontMetrics(f)
        rect = metrics.boundingRect(caption)
        # caption geometry
        cWidth = rect.width()
        cHeight = rect.height()

        # Change reference system to the caption box center with x axis up and y axis right
        center = QtCore.QPointF(
            cbWitdth / 2.0,
            cbHeight / 2.0
        )
        painter.translate(center)
        painter.rotate(-90)

        # caption position (bottom left corner) in the new reference system
        position = QtCore.QPointF(
            -cWidth / 2.0,
            cHeight / 3.0   # should be 2.0 but caption is not centered in its bounding rect
        )
        # o = QtCore.QPointF(0, 0)
        # oX = QtCore.QPointF(20, 0)
        # oY = QtCore.QPointF(0, 20)
        painter.setFont(f)
        painter.drawText(position, caption)
        # painter.drawLine(o, oX)
        # painter.drawLine(o, oY)


class Node:
    """Wrap a Flow object into a Node to provide scene interfaces.
    """
    timelineNode: 'TimelineNode'
    geometry: NodeGeometry
    graphics_obj: NodeGraphicsObject

    def __init__(
            self,
            scene: 'FlowChainScene',
            timelineNode: 'TimelineNode',
            offset: int,
            parent: "Node" = None):
        """A single Node in the scene representing a TimelineNode object.

        Args:
            scene: the FlowChainScene object owning the node graphics object.
            timelineNode: The associated TimelineNode object.
        """
        self.timelineNode = timelineNode
        self.parent = parent

        self.geometry = NodeGeometry(self, offset)
        self.graphicsObject = NodeGraphicsObject(scene, self, parent)

        self.geometry.recalculateSize(lod=1.0)

    @property
    def id(self) -> str:
        """Node unique identifier (its flow req id).
        """
        return self.timelineNode.key

    def __hash__(self) -> int:
        return id(self.timelineNode.key)

    def __eq__(self, node: 'Node') -> bool:
        try:
            return node.id == self.id and self.timelineNode.key is node.timelineNode.key
        except AttributeError:
            return False

    @property
    def caption(self) -> str:
        return self.timelineNode.key

    @property
    def size(self) -> QtCore.QSizeF:
        return self.geometry.size

    @property
    def position(self) -> QtCore.QPointF:
        return self.graphicsObject.pos()

    @position.setter
    def position(self, pos: Union[QtCore.QPointF, Tuple[float, float]]):
        if not isinstance(pos, QtCore.QPointF):
            px, py = pos
            pos = QtCore.QPointF(px, py)

        self.graphicsObject.setPos(pos)

    @property
    def kind(self) -> NodeKind:
        return self.timelineNode.kind

    @property
    def color(self):
        if self.timelineNode.kind == NodeKind.YEAR:
            return QtGui.QColor(220, 220, 220)
        return QtGui.QColor(190, 190, 190)

    @property
    def zoomLevel(self):
        nodeGO = self.graphicsObject
        scene = nodeGO.scene()
        if scene is not None:
            return scene.zoom
        return ZoomLevel.YEAR

class FlowChainScene(QtWidgets.QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        resources = Config.fotocopSettings.resources

        self.nodes = dict()
        self.zoom = ZoomLevel.YEAR

        self.setItemIndexMethod(QtWidgets.QGraphicsScene.NoIndex)

        self.setSceneRect(QtCore.QRectF(0, 0, 100, 100))

        self.selectionChanged.connect(self.onSelectionChanged)

    def populate(self, timeline):
        offset = 0
        for year in timeline:
            nodeY = self.createNode(year)
            nodeY.position = (offset, 0)
            offset += nodeY.size.width()

            offsetM = nodeY.geometry.captionHeight
            for month in year:
                nodeM = self.createNode(month, nodeY, offsetM)
                offsetM += nodeM.geometry.barWidth

                offsetD = nodeM.geometry.captionHeight
                for day in month:
                    nodeD = self.createNode(day, nodeM, offsetD)
                    offsetD += nodeD.geometry.barWidth

                    offsetH = nodeD.geometry.captionHeight
                    for hour in day:
                        nodeH = self.createNode(hour, nodeD, offsetH)
                        offsetH += nodeH.geometry.barWidth

            self.addItem(nodeY.graphicsObject)

        # Update the scene rect and its reference point.
        bounding = self.itemsBoundingRect()
        self.setSceneRect(0, 0, bounding.width(), 100)
        # print(f"Scene bounding rect is: {bounding}")

    def clear(self):
        self.nodes = dict()
        super().clear()

    def createNode(self, timelineNode: 'TimelineNode', parent: Node = None, offset: int = 0) -> Node:
        """Create a node in the scene representing the given flow.

        The given flow is wrapped in a NodeDataModel to provide a standard
        interface to the Node class.

        Args:
            timelineNode : associated timelineNode model
            parent:

        Returns:
            the created Node instance
        """
        node = Node(self, timelineNode, offset, parent)
        self.nodes[node.id] = node
        return node

    def selectedNodes(self) -> List[Node]:
        """Get the selected nodes in the scene.

        Returns:
            A list of selected Node objects.
        """
        return [
            item.node for item in self.selectedItems()
            if isinstance(item, NodeGraphicsObject)
        ]
    @QtCore.pyqtSlot()
    def onSelectionChanged(self):
        for node in self.selectedNodes():
            if node.kind == NodeKind.YEAR:
                node.graphicsObject.setSelected(False)
                for child in node.graphicsObject.childItems():
                    child.setSelected(True)
