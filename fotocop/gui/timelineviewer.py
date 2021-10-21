from typing import Tuple, Optional, Any, List

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models import settings as Config
from fotocop.models.timeline import Timeline, TimelineNode, NodeKind
from fotocop.models.sources import Selection


class TimelineViewer(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._timeline = None
        scene = FlowChainScene(parent=self)
        self._emptyScene = scene

        resources = Config.fotocopSettings.resources
        # jsonStyle = Config.fotocopSettings.appDirs.user_config_dir / 'flow_chain_style.json'

        # self._style = StyleCollection.fromJson(jsonStyle)
        self._view = FlowChainView(parent=self)
        self._view.setScene(scene)
        self._view.fitToView()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._view)
        layout.setContentsMargins(4, 0, 4, 0)

        self.setLayout(layout)

        # Force size computation even if the viewer is hidden
        layout.invalidate()
        layout.activate()

    @QtCore.pyqtSlot(Selection)
    def onSourceSelected(self, selection):
        self.setTimeline(selection.timeline)

    @QtCore.pyqtSlot(str)
    def updateTimeline(self, imageKey: str):
        pass

    def setTimeline(self, timeline: Timeline):
        if timeline:
            self._timeline = timeline
            scene = FlowChainScene(parent=self)
            scene.populate(timeline)
            self._view.setScene(scene)
            self._view.fitToView()
        else:
            self._timeline = None
            if not self._emptyScene:
                self._emptyScene = FlowChainScene(parent=self)
            scene = self._emptyScene
            self._view.setScene(scene)
            self._view.fitToView()


class FlowChainView(QtWidgets.QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self._zoom = 100
        self._lastPos = None
        self._panning = False

        resources = Config.fotocopSettings.resources

        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setRenderHint(QtGui.QPainter.Antialiasing)

        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)

        self.setCacheMode(QtWidgets.QGraphicsView.CacheBackground)

        self.setBackgroundBrush(QtGui.QColor(53, 53, 53))

        self.clearSelectionAction = QtWidgets.QAction('Clear Selection', self)
        self.clearSelectionAction.setShortcut(QtGui.QKeySequence.Cancel)
        self.addAction(self.clearSelectionAction)

    def setScene(self, scene: QtWidgets.QGraphicsScene):
        super().setScene(scene)
        if scene:
            self.clearSelectionAction.triggered.connect(scene.clearSelection)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Engage panning when left mouse button is preesed

        Memorize the mouse position in the scene when pressed.

        Args:
        ----------
            event: the trapped mouse event
        """
        super().mousePressEvent(event)

        if event.button() == QtCore.Qt.LeftButton:
            self._panning = True
            self._lastPos = self.mapToScene(event.pos())

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Drag the view while moving the mouse with the left button pressed.

        Delegate drag to the base class that delgates to the scene.
        Update the reference point of the scene.

        Args:
            event: the trapped mouse event
        """
        super().mouseMoveEvent(event)

        # if  the mouse is not 'on used' by an item of the scene and if a rubber
        # band is not in action, update the scene's reference point.
        if (
                self.scene().mouseGrabberItem() is None
                and (event.buttons() & QtCore.Qt.LeftButton)    # noqa
                and self._panning
        ):
            # Make sure shift is not being pressed
            if not (event.modifiers() & QtCore.Qt.ShiftModifier):       # noqa
                newPos = self.mapToScene(event.pos())
                delta = self._lastPos - newPos
                self._lastPos = newPos
                if delta:
                    refPoint = self.scene().refPoint
                    refPoint = refPoint + delta

                    refX = refPoint.x()
                    if refX < self.scene().sceneRect().left():
                        refPoint.setX(self.scene().sceneRect().left())
                    elif refX > self.scene().sceneRect().right():
                        refPoint.setX(self.scene().sceneRect().right())

                    refY = refPoint.y()
                    if refY < self.scene().sceneRect().top():
                        refPoint.setY(self.scene().sceneRect().top())
                    elif refY > self.scene().sceneRect().bottom():
                        refPoint.setY(self.scene().sceneRect().bottom())

                    self.scene().refPoint = refPoint

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        super().mouseReleaseEvent(event)

        if event.button() == QtCore.Qt.LeftButton:
            self._panning = False

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        pos = event.pos()
        item = self.itemAt(pos)

        if item and isinstance(item, NodeGraphicsObject):
            refPoint = item.mapToScene(item.boundingRect().center())
            self.scene().refPoint = refPoint
            self.centerOn(refPoint)
        else:
            refPoint = self.mapToScene(pos)
            self.scene().refPoint = refPoint
            self.centerOn(refPoint)

    def wheelEvent(self, event: QtGui.QWheelEvent):
        """Zoom in / out according to the mouse wheel move.

        Args:
            event: the trapped mouse wheel event
        """
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return

        step = 10
        if delta > 0.0:
            # Scale up
            zoom = min(200, self._zoom + step)
        else:
            # Scale down
            zoom = max(5, self._zoom - step)
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

    # def drawBackground(self, painter: QtGui.QPainter, r: QtCore.QRectF):
    #     """Draw a grid over the view background.
    #
    #     Call the base clas to fill 'r' using the view's backgroundBrush.
    #
    #     Args:
    #         painter: the painter to use.
    #         r: the exposed rectangle.
    #     """
    #     super().drawBackground(painter, r)
    #
    #     def drawGrid(gridStep):
    #         tl = r.topLeft()
    #         br = r.bottomRight()
    #         left = math.floor(tl.x() / gridStep - 0.5)
    #         right = math.floor(br.x() / gridStep + 1.0)
    #         bottom = math.floor(tl.y() / gridStep - 0.5)
    #         top = math.floor(br.y() / gridStep + 1.0)
    #
    #         # vertical lines
    #         lines = [
    #             QtCore.QLineF(xi * gridStep, bottom * gridStep, xi * gridStep, top * gridStep)
    #             for xi in range(int(left), int(right) + 1)
    #         ]
    #
    #         # horizontal lines
    #         lines.extend(
    #             [QtCore.QLineF(left * gridStep, yi * gridStep, right * gridStep, yi * gridStep)
    #              for yi in range(int(bottom), int(top) + 1)
    #              ]
    #         )
    #
    #         painter.drawLines(lines)
    #
    #     style = self._style
    #
    #     pfine = QtGui.QPen(style.fineGridColor, 1.0)
    #     painter.setPen(pfine)
    #     drawGrid(15)
    #
    #     p = QtGui.QPen(style.coarseGridColor, 1.0)
    #     painter.setPen(p)
    #     drawGrid(150)

    @QtCore.pyqtSlot(int)
    def zoom(self, value: int):
        self.scene().zoom = value
        self._zoom = value
        unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
        factor = value / 100
        self.scale(factor / unity.width(), factor / unity.height())
        # self.zoomed.emit(value)

    @QtCore.pyqtSlot()
    def fitToView(self):
        unity = self.transform().mapRect(QtCore.QRectF(0, 0, 1, 1))
        self.scale(1 / unity.width(), 1 / unity.height())

        sceneRect = self.scene().sceneRect()
        sceneWidth = sceneRect.width()
        sceneHeight = sceneRect.height()

        viewWidth = self.width()
        viewHeight = self.height()

        try:
            zoomX = (viewWidth / sceneWidth) * 100
            zoomY = (viewHeight / sceneHeight) * 100
            zoom = min(zoomX, zoomY)
        except ZeroDivisionError:
            zoom = 100

        self.zoom(zoom)


class NodeGeometry:
    def __init__(self, node: 'Node'):
        super().__init__()
        self.width = 100
        self.height = 150
        self.spacing = 20
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


class NodeGraphicsObject(QtWidgets.QGraphicsObject):
    node: 'Node'
    _scene: 'FlowChainScene'

    def __init__(self, scene: 'FlowChainScene', node: 'Node'):
        super().__init__()

        self.node = node

        self._scene = scene
        self._scene.addItem(self)

        self.setFlag(QtWidgets.QGraphicsItem.ItemDoesntPropagateOpacityToChildren, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsFocusable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsScenePositionChanges, True)

        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)

        # effect = QtWidgets.QGraphicsDropShadowEffect()
        # effect.setOffset(4, 4)
        # effect.setBlurRadius(20)
        # effect.setColor(self._style.shadowColor)
        # self.setGraphicsEffect(effect)
        #
        # self.setOpacity(self._style.opacity)
        #
        # self.setAcceptHoverEvents(True)

        self.setZValue(0)

    def boundingRect(self) -> QtCore.QRectF:
        return self.node.geometry.boundingRect

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Make the node visible when hovered.

        Change the cursor to a pointing hand.
        The node will be drawn in hovered representation.
        """
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

        # bring all the colliding nodes to background
        overlap_items = self.collidingItems()
        for item in overlap_items:
            if item.zValue() > 0.0:
                item.setZValue(0.0)

        # bring self node forward
        self.setZValue(1.0)
        self.node.geometry.hovered = True
        self.update()
        event.accept()

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent):
        """Reset the hovered epresentation and cursor to default.
        """
        self.setCursor(QtGui.QCursor())
        self.node.geometry.hovered = False
        self.update()
        event.accept()

    def paint(self,
              painter: QtGui.QPainter,
              option: QtWidgets.QStyleOptionGraphicsItem,
              widget: QtWidgets.QWidget = None):
        node = self.node
        geometry = node.geometry

        painter.setClipRect(option.exposedRect)
        NodeGraphicsObject.drawNodeRect(painter, geometry, self.isSelected())
        NodeGraphicsObject.drawNodeCaption(painter, geometry, node.caption)

    @classmethod
    def drawNodeRect(
            cls,
            painter: QtGui.QPainter,
            geometry: NodeGeometry,
            isSelected: bool):
        """Draw node rect.

        Args:
            painter : the node painter.
            geometry : the node geometry.
            isSelected: True if the node is selected.
        """
        color = (QtGui.QColor(255, 165, 0)
                 if isSelected
                 else QtGui.QColor(255, 255, 255)
                 )
        p = QtGui.QPen(
            color,
            1.5 if geometry.hovered else 1.0
        )
        painter.setPen(p)

        gradient = QtGui.QLinearGradient(
            QtCore.QPointF(0.0, 0.0),
            QtCore.QPointF(2.0, geometry.height)
        )
        gradientColors = (
            (0.0, QtGui.QColor("gray")),
            (0.3, QtGui.QColor(80, 80, 80)),
            (0.7, QtGui.QColor(64, 64, 64)),
            (1.0, QtGui.QColor(58, 58, 58)),
        )
        for at_, color in gradientColors:
            gradient.setColorAt(at_, color)
        painter.setBrush(gradient)

        diam = 8.0
        boundary = QtCore.QRectF(
            -diam,
            -diam,
            2.0 * diam + geometry.width,
            2.0 * diam + geometry.height
        )
        radius = 3.0
        painter.drawRoundedRect(boundary, radius, radius)

    @classmethod
    def drawNodeCaption(
            cls,
            painter: QtGui.QPainter,
            geometry: NodeGeometry,
            caption: Tuple[str, ...]):
        """Draw the node caption.

        Args:
            painter : the node painter.
            geometry : the node geometry.
            caption: the node caption.
        """
        painter.setPen(QtGui.QColor("white"))

        f = painter.font()

        h = 0
        for i, line in enumerate(caption):
            if i == 0:
                f.setBold(True)
            else:
                f.setItalic(True)
            metrics = QtGui.QFontMetrics(f)
            rect = metrics.boundingRect(line)
            position = QtCore.QPointF(
                (geometry.width - rect.width()) / 2.0,
                geometry.spacing / 3.0 + h
            )
            painter.setFont(f)
            painter.drawText(position, line)
            h += rect.height()

        f.setBold(False)
        f.setItalic(False)
        painter.setFont(f)

        diam = 8.0 - 1.0
        painter.drawLine(
            QtCore.QPointF(-diam, h),
            QtCore.QPointF(geometry.width + diam, h)
        )


class Node:
    """Wrap a Flow object into a Node to provide scene interfaces.
    """
    timelineNode: 'TimelineNode'
    geometry: NodeGeometry
    graphics_obj: NodeGraphicsObject

    def __init__(
            self,
            scene: 'FlowChainScene',
            timelineNode: 'TimelineNode'):
        """A single Node in the scene representing a TimelineNode object.

        Args:
            scene: the FlowChainScene object owning the node graphics object.
            timelineNode: The associated TimelineNode object.
        """
        self.timelineNode = timelineNode

        self.geometry = NodeGeometry(self)
        self.graphicsObject = NodeGraphicsObject(scene, self)

        # self.geometry.recalculateSize()

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


class FlowChainScene(QtWidgets.QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        resources = Config.fotocopSettings.resources

        self.nodes = {}

        self.refPoint = QtCore.QPointF()

        self._timeline = None

        self.setItemIndexMethod(QtWidgets.QGraphicsScene.NoIndex)

    def populate(self, timeline):
        self._timeline = timeline

        # Update the scene rect and its reference point.
        bounding = self.itemsBoundingRect()
        self.setSceneRect(bounding)
        self.refPoint = self.sceneRect().center()

    def createNode(self, timelineNode: 'TimelineNode') -> Node:
        """Create a node in the scene representing the given flow.

        The given flow is wrapped in a NodeDataModel to provide a standard
        interface to the Node class.

        Args:
            flow : associated flow model

        Returns:
            the created Node instance
        """
        node = Node(self, timelineNode)
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
