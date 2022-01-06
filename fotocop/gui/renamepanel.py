from typing import TYPE_CHECKING, Optional

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

from fotocop.models.naming import ORIGINAL_CASE, UPPERCASE, LOWERCASE
from .nameseditor import ImageNamingTemplateEditor

if TYPE_CHECKING:
    from fotocop.models.sources import Image
    from fotocop.models.naming import NamingTemplates
    from fotocop.models.downloader import Downloader

EDIT_TEMPLATE = "Custom..."

MediumGray = '#5d5b59'

ThumbnailBackgroundName = MediumGray


def minPanelWidth() -> int:
    """
    Minimum width of panels on left and right side of main window.

    Derived from standard font size.

    :return: size in pixels
    """

    return int(QtGui.QFontMetrics(QtGui.QFont()).height() * 13.5)


class QFramedWidget(QtWidgets.QWidget):
    """
    Draw a Frame around the widget in the style of the application.

    Use this instead of using a stylesheet to draw a widget's border.
    """

    def paintEvent(self, *opts):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(QtWidgets.QStyle.PE_Frame, option)
        super().paintEvent(*opts)


class QPanelView(QtWidgets.QWidget):
    """
    A header bar with a child widget.
    """

    def __init__(self, label: str,
                 headerColor: Optional[QtGui.QColor]=None,
                 headerFontColor: Optional[QtGui.QColor]=None,
                 parent: QtWidgets.QWidget=None) -> None:

        super().__init__(parent)

        self.header = QtWidgets.QWidget(self)
        if headerColor is not None:
            headerStyle = """QWidget { background-color: %s; }""" % headerColor.name()
            self.header.setStyleSheet(headerStyle)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.MinimumExpanding, QtWidgets.QSizePolicy.Fixed)

        self.label = QtWidgets.QLabel(label.upper())
        if headerFontColor is not None:
            headerFontStyle =  "QLabel {color: %s;}" % headerFontColor.name()
            self.label.setStyleSheet(headerFontStyle)

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(5, 2, 5, 2)
        self.headerLayout.addWidget(self.label)
        self.headerLayout.addStretch()
        self.header.setLayout(self.headerLayout)

        self.headerWidget = None
        self.content = None

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

        if self.content is not None:
            self.layout().removeWidget(self.content)
        self.content = widget
        self.layout().addWidget(self.content)

    def addHeaderWidget(self, widget: QtWidgets.QWidget) -> None:
        """Add a widget to the header bar, on the right side.

        Any previous widget will be removed.

        Args:
            widget: widget to add
        """
        if self.headerWidget is not None:
            self.headerLayout.removeWidget(self.headerWidget)
        self.headerWidget = widget
        self.headerLayout.addWidget(widget)

    def text(self) -> str:
        """Return the text of the label."""
        return self.label.text()

    def setText(self, text: str) -> None:
        """Set the text of the label."""
        self.label.setText(text)

    def minimumSize(self) -> QtCore.QSize:
        print("MinimumSize")
        if self.content is None:
            font_height = QtGui.QFontMetrics(QtGui.QFont).height()
            width = minPanelWidth()
            height = font_height * 2
        else:
            width = self.content.minimumWidth()
            height = self.content.minimumHeight()
        return QtCore.QSize(width, self.header.height() + height)


class RenameWidget(QFramedWidget):

    templateSelected = QtCore.pyqtSignal(str)
    extensionSelected = QtCore.pyqtSignal(str)

    def __init__(self, templates: "NamingTemplates", parent=None):
        super().__init__(parent)
        self.templates = templates

        self.setBackgroundRole(QtGui.QPalette.Base)
        self.setAutoFillBackground(True)
        # self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

        self.templateCmb = QtWidgets.QComboBox()
        self.extensionCmb = QtWidgets.QComboBox()
        self.exampleLbl = QtWidgets.QLabel("Example")

        layout = QtWidgets.QFormLayout()
        self.setLayout(layout)

        layout.addRow('Preset:', self.templateCmb)
        layout.addRow('Extension:', self.extensionCmb)
        layout.addRow('Example:', self.exampleLbl)

        self.templateCmb.currentIndexChanged.connect(self.selectTemplate)
        self.extensionCmb.currentIndexChanged.connect(self.selectExtension)

        self.extensionCmb.addItem(ORIGINAL_CASE, ORIGINAL_CASE)
        self.extensionCmb.addItem(UPPERCASE, UPPERCASE)
        self.extensionCmb.addItem(LOWERCASE, LOWERCASE)
        self.extensionCmb.setCurrentIndex(2)    # lowercase

        self.updateTemplateCmb()

    def updateTemplateCmb(self):
        with QtCore.QSignalBlocker(self.templateCmb):
            self.templateCmb.clear()
            builtins = self.templates.listBuiltinImageNamingTemplates()
            for template in builtins:
                self.templateCmb.addItem(template.name, template.key)
            self.templateCmb.insertSeparator(len(builtins))
            customs = self.templates.listImageNamingTemplates()
            for template in customs:
                self.templateCmb.addItem(template.name, template.key)
            self.templateCmb.addItem(EDIT_TEMPLATE, EDIT_TEMPLATE)

    @QtCore.pyqtSlot(int)
    def selectTemplate(self, _index: int):
        template = self.templateCmb.currentData()

        if template == EDIT_TEMPLATE:
            print(EDIT_TEMPLATE)
            dialog = ImageNamingTemplateEditor(self.templates, parent=self)

            templateName = ''
            if dialog.exec():
                templateName = dialog.templateName

            # Regardless of whether the user clicked OK or cancel, refresh the rename
            # combo box entries.
            if templateName:
                self.updateTemplateCmb()
                self.templateCmb.setCurrentText(templateName)
        else:
            self.templateSelected.emit(template)

    @QtCore.pyqtSlot(int)
    def selectExtension(self, _index: int):
        extensionKind = self.extensionCmb.currentData()
        self.extensionSelected.emit(extensionKind)


class RenamePanel(QtWidgets.QScrollArea):
    """
    Renaming preferences widget, for photos, videos, and general
    renaming options.
    """

    def __init__(self, downloader: "Downloader",  parent) -> None:
        super().__init__(parent)

        self.downloader = downloader

        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setWidgetResizable(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        # self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)

        self.photoRenamePanel = QPanelView(
            label='Photo Renaming', headerColor=QtGui.QColor(ThumbnailBackgroundName),
            headerFontColor=QtGui.QColor(QtCore.Qt.white)
        )
        self.photoRenameWidget = RenameWidget(
            templates= downloader.namingTemplates,
            parent=self
        )
        self.photoRenamePanel.addWidget(self.photoRenameWidget)

        # b = QtWidgets.QPushButton("B")
        # self.photoRenamePanel.addHeaderWidget(b)

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)
        layout.addWidget(self.photoRenamePanel)
        layout.addStretch()
        self.setWidget(widget)

        self.photoRenameWidget.templateSelected.connect(downloader.setImageNamingTemplate)
        self.photoRenameWidget.extensionSelected.connect(downloader.setExtension)

    def updateImageSample(self, image: "Image"):
        name = self.downloader.renameImage(image)
        self.photoRenameWidget.exampleLbl.setText(name)
