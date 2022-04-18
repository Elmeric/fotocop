from typing import Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui


def minPanelWidth() -> int:
    """Minimum width of panels on left and right side of main window.

    Derived from standard font size.

    Returns: size in pixels.
    """

    return int(QtGui.QFontMetrics(QtGui.QFont()).height() * 13.5)


class QPanelView(QtWidgets.QWidget):
    """A header bar with a child widget.
    """

    def __init__(
            self,
            label: str,
            headerColor: Optional[QtGui.QColor] = None,
            headerFontColor: Optional[QtGui.QColor] = None,
            parent: QtWidgets.QWidget = None
    ):

        super().__init__(parent)

        self.header = QtWidgets.QWidget(self)
        self.header.setMinimumHeight(32)
        if headerColor is not None:
            headerStyle = f"""QWidget {{ background-color: {headerColor.name()}; }}"""
            self.header.setStyleSheet(headerStyle)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        self.label = QtWidgets.QLabel(label.upper())
        if headerFontColor is not None:
            headerFontStyle = f"QLabel {{color: {headerFontColor.name()};}}"
            self.label.setStyleSheet(headerFontStyle)

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(5, 2, 5, 2)
        self.headerLayout.addWidget(self.label)
        self.headerLayout.addStretch()
        self.header.setLayout(self.headerLayout)

        self._headerWidget = None
        self._content = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        self.setLayout(layout)

    def addWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the Panel View.

        Any previous widget will be removed.

        Args:
            widget: widget to add
        """

        if self._content is not None:
            self.layout().removeWidget(self._content)

        self._content = widget

        self.layout().addWidget(self._content)

    def addHeaderWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the header bar, on the right side.

        Any previous widget will be removed.

        Args:
            widget: widget to add
        """
        if self._headerWidget is not None:
            self.headerLayout.removeWidget(self._headerWidget)

        self._headerWidget = widget

        self.headerLayout.addWidget(widget)

    def text(self) -> str:
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text: str) -> None:
        """Set the text of the label."""
        self.label.setText(text)
