from typing import Dict, TYPE_CHECKING

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets

from fotocop.models.sources import Selection
from . import tlv
from .timelinescene import YearScene, MonthScene, DayScene
from .timelineview import TimelineView

if TYPE_CHECKING:
    from .timelinescene import TimelineScene


class TimelineViewer(QtWidgets.QWidget):
    """Displays a chronological view of images count in the selected images' source.

    Three "zoom levels" are available:
        YEAR: for each year, shows images count by month
        MONTH: for each month, shows images count by day
        DAY: for each day, shows images count by hours
    Only years/months/days with images in the images' source are shown.
    Each "zoom level" is a QGraphicsScene and it is displayed by a QGraphicsView.

    Provide an easy way to select a date/time range to be displayed in the ThumbnailView.

    Args:
        parent: the parent widget (the QtMainView QMainWindow).

    Class attributes:
        SCENE_BUILDER: Identify the TimelineScene subclass to instantiate for each
            zoom level.

    Signals:
        zoomed: To propagate the new zoom level of the view to other widgets
            (e.g. ThumbnailViewer).
        hoveredNodeChanged: To propagate the hovered node to other widgets
            (e.g. ThumbnailViewer).

    Attributes:
        _scenes: a dictionary to reference each scene by its corresponding zoom level.
        _view: the TimelineView, subclass of QGraphicsView, displayng the the timeline.
    """

    SCENE_BUILDER = {
        tlv.ZoomLevel.YEAR: YearScene,
        tlv.ZoomLevel.MONTH: MonthScene,
        tlv.ZoomLevel.DAY: DayScene,
    }

    zoomed = QtCore.pyqtSignal(tlv.ZoomLevel)
    hoveredNodeChanged = QtCore.pyqtSignal(str, int)    # key, weight
    timeRangeChanged = QtCore.pyqtSignal(list)          # list of ordered TimeRange

    def __init__(self, parent=None):
        super().__init__(parent)

        # Build an empty scene for each available zoom levels.
        # Propagate the hovered node to other widgets (e.g. ThumbnailViewer).
        self._scenes: Dict[tlv.ZoomLevel, TimelineScene] = dict()
        for zoomLevel in tlv.ZoomLevel:
            scene = TimelineViewer.SCENE_BUILDER[zoomLevel](parent=self)
            scene.hoveredNodeChanged.connect(self.hoveredNodeChanged)
            self._scenes[zoomLevel] = scene

        # Create a view to display the scene corresponding to the current zoom level.
        self._view = TimelineView(parent=self)

        self.setMinimumHeight(tlv.MAX_BAR_HEIGHT + tlv.SCROLL_BAR_HEIGHT)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._view)
        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

        # Force size computation even if the viewer is hidden
        layout.invalidate()
        layout.activate()

        # To propagate the new zoom level of the view to other widgets (e.g. ThumbnailViewer).
        self._view.zoomed.connect(self.zoomed)
        # Adapt the view's scene to those corresponding to the new zoom level.
        self._view.zoomed.connect(self._setScene)

        # Set the timeline view to the scene corresponding to the default zoom level.
        self._setScene(tlv.DEFAULT_ZOOM_LEVEL)

    @QtCore.pyqtSlot(Selection)
    def setTimeline(self, sourceSelection: Selection):
        """Initiate the timeline model of the scene for each zoom level.

        The timeline is the one of the selected images' source (None if no source is
        selected).
        Each scene is cleared and the one corresponding to the current zoom level is
        affected to the timeline view for display (the scene will be populated if
        needed).

        Args:
            sourceSelection: information on the current selected images' source.
        """
        for zoomLevel in tlv.ZoomLevel:
            self._scenes[zoomLevel].setTimeline(sourceSelection.timeline)
        self._clearScenes()
        self._setScene(self.zoomLevel())
        sourceSelection.timeline.selectionModel().timeRangeChanged.connect(
            self.timeRangeChanged
        )

    @QtCore.pyqtSlot()
    def updateTimeline(self):
        """Update the timeline scene for the current zoom level and display it in the view.

        As each scene is cleared before affecting the one corresponding to the current
        zoom level to the timeline view for display, it will be re-populated at each
        update.
        """
        self._clearScenes()
        self._setScene(self.zoomLevel())

    @QtCore.pyqtSlot()
    def finalizeTimeline(self):
        """Last update of the timeline scenes when the timeline model is fully loaded.

        As each scene is cleared before update, they will be re-populated.
        """
        self._clearScenes()
        for zoomLevel in tlv.ZoomLevel:
            self._scenes[zoomLevel].populate()
        print("***** Scenes are loaded")

    @QtCore.pyqtSlot(tlv.ZoomLevel)
    def zoom(self, zoomLevel: tlv.ZoomLevel):
        """Zoom the timelineViewer view from an external widget (e.g. ThumbnailViewer)."""
        self._view.zoom(zoomLevel)

    def zoomLevel(self) -> tlv.ZoomLevel:
        """Returns the current zoom level of the timeline view."""
        return self._view.zoomLevel

    @QtCore.pyqtSlot(tlv.ZoomLevel)
    def _setScene(self, zoomLevel: tlv.ZoomLevel):
        """Set the scene of the timeline view to the one corresponding to zoomLevel.

        Populate the zoom level's scene if not already loaded.
        """
        scene = self._scenes[zoomLevel]
        scene.populate()
        self._view.setScene(scene)

    def _clearScenes(self):
        """Clear scenes for all zoom levels."""
        for zoomLevel in tlv.ZoomLevel:
            self._scenes[zoomLevel].clear()
