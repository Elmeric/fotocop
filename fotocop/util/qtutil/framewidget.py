import PyQt5.QtWidgets as QtWidgets

__all__ = ["QFramedWidget"]


class QFramedWidget(QtWidgets.QWidget):
    """Draw a Frame around the widget in the style of the application.

    Use this instead of using a stylesheet to draw a widget's border.
    """

    def paintEvent(self, *opts):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(QtWidgets.QStyle.PE_Frame, option)
        super().paintEvent(*opts)
