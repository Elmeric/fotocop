import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

__all__ = ["CollapsibleWidget"]


class _TitleFrame(QtWidgets.QFrame):

    clicked = QtCore.pyqtSignal()

    def __init__(self, title: str = "", isCollapsed: bool = False, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(24)
        # self.move(QtCore.QPoint(24, 0))
        self.setStyleSheet("border:1px solid rgb(41, 41, 41); ")

        self._arrow = _Arrow(isCollapsed=isCollapsed)
        self._arrow.setStyleSheet("border:0px")

        self._title = QtWidgets.QLabel(title)
        self._title.setMinimumHeight(24)
        # self._title.move(QtCore.QPoint(24, 0))
        self._title.setStyleSheet("border:0px")

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._arrow)
        layout.addWidget(self._title)

        self.setLayout(layout)

    def collapse(self, isCollapsed: bool):
        self._arrow.setArrow(isCollapsed)

    def mousePressEvent(self, event):
        self.clicked.emit()
        return super().mousePressEvent(event)


class _Arrow(QtWidgets.QFrame):
    _expansedArrow = (
        QtCore.QPointF(7.0, 8.0),
        QtCore.QPointF(17.0, 8.0),
        QtCore.QPointF(12.0, 13.0),
    )
    _collapsedArrow = (
        QtCore.QPointF(8.0, 7.0),
        QtCore.QPointF(13.0, 12.0),
        QtCore.QPointF(8.0, 17.0),
    )

    def __init__(self, isCollapsed: bool = False, parent=None):
        super().__init__(parent)

        self.setMaximumSize(24, 24)

        self._arrow = self._collapsedArrow if isCollapsed else self._expansedArrow

    def setArrow(self, isCollapsed: bool):
        self._arrow = self._collapsedArrow if isCollapsed else self._expansedArrow

    def paintEvent(self, event):
        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setBrush(QtGui.QColor(192, 192, 192))
        painter.setPen(QtGui.QColor(64, 64, 64))
        painter.drawPolygon(*self._arrow)
        painter.end()


class CollapsibleWidget(QtWidgets.QWidget):
    def __init__(self, title: str = None, isCollapsed: bool = True, parent=None):
        super().__init__(parent)

        self._isCollapsed = isCollapsed

        self._titleFrame = _TitleFrame(title=title, isCollapsed=isCollapsed)
        self._titleFrame.clicked.connect(self.toggleCollapsed)

        self._content = QtWidgets.QWidget()
        self._content.setVisible(not isCollapsed)

        self._contentLayout = QtWidgets.QVBoxLayout()

        self._content.setLayout(self._contentLayout)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 0)
        layout.setSpacing(0)
        layout.addWidget(self._titleFrame)
        layout.addWidget(self._content)

        self.setLayout(layout)

    def addWidget(self, widget):
        self._contentLayout.addWidget(widget)

    def addLayout(self, layout):
        self._contentLayout.addLayout(layout)

    def toggleCollapsed(self):
        self._content.setVisible(self._isCollapsed)
        self._isCollapsed = not self._isCollapsed
        self._titleFrame.collapse(self._isCollapsed)
