from typing import Set, Optional, List, Union, Tuple, TYPE_CHECKING

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models.timeline import SelectionState
from .tlv import MIN_BAR_HEIGHT, MAX_BAR_HEIGHT

if TYPE_CHECKING:
    from fotocop.models.timeline import Timeline, TimelineNode


class TimelineScene(QtWidgets.QGraphicsScene):

    hoveredNodeChanged = QtCore.pyqtSignal(str, int)    # key, weight

    # https://stackoverflow.com/questions/47102224/pyqt-draw-selection-rectangle-over-picture
    # https://stackoverflow.com/questions/44468775/how-to-draw-a-rectangle-and-adjust-its-shape-by-drag-and-drop-in-pyqt5

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        # keep reference of the timeline model.
        self.timeline = None
        self.isLoaded = False

        self._nodes = dict()

        self.setItemIndexMethod(QtWidgets.QGraphicsScene.NoIndex)

        self.setSceneRect(QtCore.QRectF(0, 0, 100, MAX_BAR_HEIGHT))

    @QtCore.pyqtSlot(set, set, set)
    def onSelectionChanged(
            self,
            selected: Set["TimelineNode"],
            partiallySelected: Set["TimelineNode"],
            deselected: Set["TimelineNode"]):

        for timelineNode in selected | partiallySelected | deselected:
            try:
                self._nodes[timelineNode.date].graphicsObject.update()
            except KeyError:
                pass

    @QtCore.pyqtSlot()
    def clearSelection(self):
        # super().clearSelection()
        if self.timeline is not None:
            self.timeline.selectionModel().clearSelection()
        print(f"Selected time ranges: {self.timeline.selectionModel().selectedRanges()}")

    def clear(self):
        self._nodes = dict()
        self.isLoaded = False
        super().clear()

    def setTimeline(self, timeline: Optional["Timeline"]):
        self.timeline = timeline
        if timeline is not None:
            timeline.selectionModel().selectionChanged.connect(
                self.onSelectionChanged
            )

    def populate(self):
        timeline = self.timeline
        if timeline is not None:
            if self.isLoaded:
                print(f"{self.__class__.__name__} is loaded: no need to populate it")
            else:
                self._populate(timeline)
        else:
            print("No timeline defined yet")

    def selectedNodes(self) -> List["Node"]:
        """Get the selected nodes in the scene.

        Returns:
            A list of selected Node objects.
        """
        return [
            item.node
            for item in self.selectedItems()
            if isinstance(item, NodeGraphicsObject)
        ]

    def _populate(self, timeline: "Timeline"):
        return NotImplemented


class YearScene(TimelineScene):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def _populate(self, timeline: "Timeline"):
        self.clear()
        offsetY = 0
        for year in timeline:
            nodeY = BranchNode(self, year)
            self._nodes[year.date] = nodeY

            offsetM = nodeY.geometry.captionHeight
            for month in year:
                nodeM = LeafNode(self, month, nodeY)
                self._nodes[month.date] = nodeM
                nodeM.position = (offsetM, MAX_BAR_HEIGHT - nodeM.geometry.height)
                offsetM += nodeM.geometry.barWidth

            nodeY.position = (offsetY, 0)
            offsetY += (
                nodeY.geometry.captionHeight
                + year.childCount() * nodeY.geometry.barWidth
            )
            self.addItem(nodeY.graphicsObject)

        # Update the scene rect and its reference point.
        bounding = self.itemsBoundingRect()
        self.setSceneRect(0, 0, bounding.width(), MAX_BAR_HEIGHT)

        self.isLoaded = True


class MonthScene(TimelineScene):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def _populate(self, timeline: "Timeline"):
        self.clear()
        offsetM = 0
        for year in timeline:
            for month in year:
                nodeM = BranchNode(self, month)
                self._nodes[month.date] = nodeM

                offsetD = nodeM.geometry.captionHeight
                for day in month:
                    nodeD = LeafNode(self, day, nodeM)
                    self._nodes[day.date] = nodeD
                    nodeD.position = (offsetD, MAX_BAR_HEIGHT - nodeD.geometry.height)
                    offsetD += nodeD.geometry.barWidth

                nodeM.position = (offsetM, 0)
                offsetM += (
                    nodeM.geometry.captionHeight
                    + month.childCount() * nodeM.geometry.barWidth
                )
                self.addItem(nodeM.graphicsObject)

        # Update the scene rect and its reference point.
        bounding = self.itemsBoundingRect()
        self.setSceneRect(0, 0, bounding.width(), MAX_BAR_HEIGHT)

        self.isLoaded = True


class DayScene(TimelineScene):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

    def _populate(self, timeline: "Timeline"):
        self.clear()
        offsetD = 0
        for year in timeline:
            for month in year:
                for day in month:
                    nodeD = BranchNode(self, day)
                    self._nodes[day.date] = nodeD

                    offsetH = nodeD.geometry.captionHeight
                    for hour in day:
                        nodeH = LeafNode(self, hour, nodeD)
                        self._nodes[hour.date] = nodeH
                        nodeH.position = (offsetH, MAX_BAR_HEIGHT - nodeH.geometry.height)
                        offsetH += nodeH.geometry.barWidth

                    nodeD.position = (offsetD, 0)
                    offsetD += (
                        nodeD.geometry.captionHeight
                        + day.childCount() * nodeD.geometry.barWidth
                    )
                    self.addItem(nodeD.graphicsObject)

        # Update the scene rect and its reference point.
        bounding = self.itemsBoundingRect()
        self.setSceneRect(0, 0, bounding.width(), MAX_BAR_HEIGHT)

        self.isLoaded = True


class Node:
    """Wrap a Flow object into a Node to provide scene interfaces."""

    timelineNode: "TimelineNode"
    graphics_obj: "NodeGraphicsObject"

    def __init__(
        self,
        scene: "TimelineScene",
        timelineNode: "TimelineNode",
        parent: "Node" = None,
    ):
        """A single Node in the scene representing a TimelineNode object.

        Args:
            scene: the TimelineScene object owning the node graphics object.
            timelineNode: The associated TimelineNode object.
        """
        self.timelineNode = timelineNode
        self.parent = parent

        self.geometry = None
        self.graphicsObject = None

    @property
    def id(self) -> str:
        """Node unique identifier (its flow req id)."""
        return self.timelineNode.key

    def __hash__(self) -> int:
        return id(self.timelineNode.key)

    def __eq__(self, node: "Node") -> bool:
        try:
            return node.id == self.id and self.timelineNode.key is node.timelineNode.key
        except AttributeError:
            return False

    @property
    def caption(self) -> str:
        return self.timelineNode.asText

    @property
    def tooltip(self) -> str:
        return f"{self.timelineNode.asText} ({self.timelineNode.weight})"

    @property
    def color(self):
        return QtGui.QColor()

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


class BranchNode(Node):

    geometry: "BranchNodeGeometry"

    def __init__(
        self,
        scene: "TimelineScene",
        timelineNode: "TimelineNode",
        parent: "BranchNode" = None,
    ):
        """A single Node in the scene representing a TimelineNode object.

        Args:
            scene: the TimelineScene object owning the node graphics object.
            timelineNode: The associated TimelineNode object.
        """
        super().__init__(scene, timelineNode, parent)

        self.geometry = BranchNodeGeometry(self)
        self.graphicsObject = BranchNodeGraphicsObject(scene, self, parent)

        self.geometry.recalculateSize()

    @property
    def color(self):
        selection = self.graphicsObject.scene().timeline.selectionModel()
        if selection.selectionState(self.timelineNode) == SelectionState.PartiallySelected:
        # if self.timelineNode.selectionState() == SelectionState.PartiallySelected:
            return QtGui.QColor("lightskyblue").lighter(140)

        return QtGui.QColor(220, 220, 220)


class LeafNode(Node):

    geometry: "LeafNodeGeometry"

    def __init__(
        self,
        scene: "TimelineScene",
        timelineNode: "TimelineNode",
        parent: "BranchNode" = None,
    ):
        """A single Node in the scene representing a TimelineNode object.

        Args:
            scene: the TimelineScene object owning the node graphics object.
            timelineNode: The associated TimelineNode object.
        """
        super().__init__(scene, timelineNode, parent)

        self.geometry = LeafNodeGeometry(self)
        self.graphicsObject = LeafNodeGraphicsObject(scene, self, parent)

        self.geometry.recalculateSize()

    @property
    def color(self):
        selection = self.graphicsObject.scene().timeline.selectionModel()
        state = selection.selectionState(self.timelineNode)
        # state = self.timelineNode.selectionState()

        if state == SelectionState.PartiallySelected:
            return QtGui.QColor("lightskyblue").lighter(120)

        if state == SelectionState.Selected:
            return QtGui.QColor("deepskyblue")

        return QtGui.QColor(190, 190, 190)


class NodeGeometry:
    def __init__(self, node: "Node"):
        super().__init__()
        self.width = 100
        self.height = MAX_BAR_HEIGHT
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
        """The node bounding rect, including its ports (addon)"""
        return QtCore.QRectF(0, 0, self.width, self.height)

    @property
    def captionHeight(self) -> int:
        return (
            self._boldFontMetrics.boundingRect(self._node.caption).height()
            + 2 * self.spacing
        )

    @property
    def captionWidth(self) -> int:
        return self._boldFontMetrics.boundingRect(self._node.caption).width()


class BranchNodeGeometry(NodeGeometry):
    def recalculateSize(self):
        timelineNode = self._node.timelineNode
        self.width = self.captionHeight + timelineNode.childCount() * self.barWidth
        self.height = MAX_BAR_HEIGHT


class LeafNodeGeometry(NodeGeometry):
    def recalculateSize(self):
        timelineNode = self._node.timelineNode
        rootNode = timelineNode.root
        weightScale = (
            (MAX_BAR_HEIGHT - MIN_BAR_HEIGHT)
            / rootNode.maxWeightByDepth[timelineNode.depth - 1]
        )
        self.width = self.barWidth
        self.height = MIN_BAR_HEIGHT + timelineNode.weight * weightScale


class NodeGraphicsObject(QtWidgets.QGraphicsObject):
    node: "Node"
    _scene: "TimelineScene"

    def __init__(self, scene: "TimelineScene", node: "Node", parent: "Node" = None):
        if parent is not None:
            parent = parent.graphicsObject
        super().__init__(parent)

        self.node = node

        self._scene = scene

        self.setFlag(QtWidgets.QGraphicsItem.ItemDoesntPropagateOpacityToChildren, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsScenePositionChanges, True)

        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

        self.setAcceptHoverEvents(True)

        self.setZValue(0)

        self.setToolTip(node.tooltip)

    def boundingRect(self) -> QtCore.QRectF:
        return self.node.geometry.boundingRect


class BranchNodeGraphicsObject(NodeGraphicsObject):
    def __init__(self, scene: "TimelineScene", node: "Node", parent: "Node" = None):
        super().__init__(scene, node, parent)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Change the cursor to a pointing hand."""
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        node = self.node
        self.scene().hoveredNodeChanged.emit(node.caption, node.timelineNode.weight)
        event.accept()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Reset cursor to default."""
        self.setCursor(QtGui.QCursor())
        self.scene().hoveredNodeChanged.emit("", 0)
        event.accept()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: QtWidgets.QWidget = None,
    ):
        # print(f"Painting {self.node.timelineNode.date}")
        node = self.node
        geometry = node.geometry
        geometry.recalculateSize()

        painter.setClipRect(option.exposedRect)
        self.drawNodeRect(painter, geometry, self.node.color)
        self.drawNodeCaption(painter, geometry, node.caption)

    @classmethod
    def drawNodeRect(
        cls,
        painter: QtGui.QPainter,
        geometry: NodeGeometry,
        nodeColor: QtGui.QColor,
    ):
        """Draw node rect.

        Args:
            painter : the node painter.
            geometry : the node geometry.
            nodeColor: the node color.
        """
        color = nodeColor.darker(150) if geometry.hovered else nodeColor

        painter.setPen(QtGui.QColor(128, 128, 128))
        painter.setBrush(color)

        painter.drawRect(QtCore.QRectF(0, 0, geometry.width, geometry.height))

    @classmethod
    def drawNodeCaption(
        cls, painter: QtGui.QPainter, geometry: NodeGeometry, caption: str
    ):
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
        center = QtCore.QPointF(cbWitdth / 2.0, cbHeight / 2.0)
        painter.translate(center)
        painter.rotate(-90)

        # caption position (bottom left corner) in the new reference system
        position = QtCore.QPointF(
            -cWidth / 2.0,
            cHeight / 3.0,  # should be 2.0 but caption is not centered in its bounding rect
        )
        painter.setFont(f)
        painter.drawText(position, caption)


class LeafNodeGraphicsObject(NodeGraphicsObject):
    def __init__(self, scene: "TimelineScene", node: "Node", parent: "Node" = None):
        super().__init__(scene, node, parent)

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Make the node highlighted when hovered.

        Change the cursor to a pointing hand.
        The node will be drawn in hovered representation.
        """
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        node = self.node
        node.geometry.hovered = True
        self.update()
        self.scene().hoveredNodeChanged.emit(node.caption, node.timelineNode.weight)
        event.accept()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Reset the hovered representation and cursor to default."""
        self.setCursor(QtGui.QCursor())
        node = self.node
        node.geometry.hovered = False
        self.update()
        self.scene().hoveredNodeChanged.emit(node.parent.caption, node.parent.timelineNode.weight)
        event.accept()

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: QtWidgets.QWidget = None,
    ):
        # print(f"Painting {self.node.timelineNode.date}")
        node = self.node
        geometry = node.geometry
        geometry.recalculateSize()

        painter.setClipRect(option.exposedRect)
        self.drawNodeRect(painter, geometry, self.node.color)

    @classmethod
    def drawNodeRect(
        cls,
        painter: QtGui.QPainter,
        geometry: NodeGeometry,
        nodeColor: QtGui.QColor,
    ):
        """Draw node rect.

        Args:
            painter : the node painter.
            geometry : the node geometry.
            nodeColor: the node color.
        """
        color = nodeColor.darker(150) if geometry.hovered else nodeColor

        painter.setPen(QtGui.QColor(128, 128, 128))
        painter.setBrush(color)

        painter.drawRect(QtCore.QRectF(0, 0, geometry.width, geometry.height))
