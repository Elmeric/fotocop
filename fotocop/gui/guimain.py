"""Entry point for the GUI version of fotocop.
"""
import sys
import os
import logging
from pathlib import Path

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

import fotocop.__about__ as __about__
from fotocop.util.logutil import LogConfig
from fotocop.util import qtutil as QtUtil

# Models
from fotocop.models import settings as Config
from fotocop.models.sources import SourceManager
from fotocop.models.downloader import Downloader

# Views
from .fileexplorer import FileSystemModel, FileSystemDelegate, FileSystemFilter
from .sourceselector import SourceSelector
from .thumbnailviewer import ThumbnailViewer
from .timelineviewer import TimelineViewer
from .renamepanel import RenamePanel
from .destinationpanel import DestinationPanel

__all__ = ["QtMain"]

logger = logging.getLogger(__name__)


class QtMainView(QtWidgets.QMainWindow):
    """The fotocop main view.

    The Main view is composed of:
        The source selector:  browse and select an images' source.
        The thumbnail viewer: show images from the selected source.
        The timeline viewer: select a time range to filter the thumbnails.
        The toolbar: propose acces to fotocop setings and help.
        The status bar: display information and warning messages.

    Args:
        sourceManager: reference to the images' sources manager.
        splash: reference to the splash screen to show the main view initialization
            progress.
        *args, **kwargs: Any other positional and keyword argument are passed to
            the parent QMainWindow.

    Attributes:
        _sourceManager: reference to the images' sources manager.
        _splash: reference to the splash screen to show the main view initialization
            progress.
        _status: reference to the Main window status bar.
    """

    def __init__(self, sourceManager: SourceManager, splash, *args, **kwargs):
        super().__init__(*args, **kwargs)

        splash.setProgress(10, "Create Gui objects...")

        self._splash = splash

        resources = Config.fotocopSettings.resources
        selectIcon = QtGui.QIcon(f"{resources}/select.png")

        # Initialize the app's views. Init order fixed to comply with the editors' dependencies.
        fsModel = FileSystemModel()
        fsDelegate = FileSystemDelegate()
        fsFilter = FileSystemFilter()
        fsFilter.setSourceModel(fsModel)
        # fsModel = QtWidgets.QFileSystemModel()
        # fsModel.setRootPath("")
        # fsModel.setOption(QtWidgets.QFileSystemModel.DontUseCustomDirectoryIcons)
        # fsModel.setOption(QtWidgets.QFileSystemModel.DontWatchForChanges)
        # fsModel.setFilter(QtCore.QDir.NoDotAndDotDot | QtCore.QDir.AllDirs)
        self._sourceManager = sourceManager
        sourceSelector = SourceSelector(sourceManager, fsModel, fsFilter, fsDelegate)

        # https://stackoverflow.com/questions/42673010/how-to-correctly-load-images-asynchronously-in-pyqt5
        thumbnailViewer = ThumbnailViewer()

        timelineViewer = TimelineViewer(parent=self)

        self._downloader = Downloader()
        renamePanel = RenamePanel(downloader=self._downloader, parent=self)
        destinationPanel = DestinationPanel(
            downloader=self._downloader,
            fsModel=fsModel,
            fsFilter=fsFilter,
            fsDelegate=fsDelegate,
            parent=self
        )

        self._sourceManager.sourceEnumerated.connect(sourceSelector.displaySources)
        self._sourceManager.sourceSelected.connect(sourceSelector.displaySelectedSource)
        self._sourceManager.sourceSelected.connect(thumbnailViewer.setSourceSelection)
        self._sourceManager.sourceSelected.connect(timelineViewer.setTimeline)
        self._sourceManager.sourceSelected.connect(self._downloader.setSourceSelection)
        self._sourceManager.imagesBatchLoaded.connect(thumbnailViewer.addImages)
        self._sourceManager.thumbnailLoaded.connect(thumbnailViewer.updateImage)
        self._sourceManager.datetimeLoaded.connect(timelineViewer.updateTimeline)
        self._sourceManager.timelineBuilt.connect(timelineViewer.finalizeTimeline)
        self._sourceManager.timelineBuilt.connect(thumbnailViewer.activateDateFilter)
        self._sourceManager.timelineBuilt.connect(self._downloader.updateImageSample)
        self._downloader.imageSampleChanged.connect(renamePanel.updateImageSample)
        self._downloader.destinationSelected.connect(destinationPanel.destinationSelected)
        thumbnailViewer.zoomLevelChanged.connect(timelineViewer.zoom)
        timelineViewer.zoomed.connect(thumbnailViewer.onZoomLevelChanged)
        timelineViewer.hoveredNodeChanged.connect(thumbnailViewer.showNodeInfo)
        timelineViewer.timeRangeChanged.connect(thumbnailViewer.updateTimeRange)

        splash.setProgress(30)

        # Build the main view layout.
        centerVertSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        centerVertSplitter.setChildrenCollapsible(False)
        centerVertSplitter.setHandleWidth(3)
        centerVertSplitter.addWidget(thumbnailViewer)
        centerVertSplitter.addWidget(timelineViewer)
        centerVertSplitter.setStretchFactor(0, 5)
        centerVertSplitter.setStretchFactor(1, 1)
        centerVertSplitter.setOpaqueResize(False)

        rightWidget = QtWidgets.QWidget()
        rightLayout = QtWidgets.QVBoxLayout()
        rightLayout.setContentsMargins(5, 0, 0, 5)
        rightLayout.setSpacing(0)
        rightLayout.addWidget(renamePanel)
        rightLayout.addWidget(destinationPanel)
        rightWidget.setLayout(rightLayout)

        leftWidget = QtWidgets.QWidget()
        leftLayout = QtWidgets.QVBoxLayout()
        leftLayout.setContentsMargins(0, 0, 5, 5)
        leftLayout.addWidget(sourceSelector)
        leftWidget.setLayout(leftLayout)

        horzSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horzSplitter.setChildrenCollapsible(False)
        horzSplitter.setHandleWidth(3)
        horzSplitter.addWidget(leftWidget)
        horzSplitter.addWidget(centerVertSplitter)
        horzSplitter.addWidget(rightWidget)
        horzSplitter.setStretchFactor(0, 1)
        horzSplitter.setStretchFactor(1, 3)
        horzSplitter.setStretchFactor(2, 1)
        horzSplitter.setOpaqueResize(False)

        self.setCentralWidget(horzSplitter)

        # Build actions used in toolbars.
        helpAboutAction = QtUtil.createAction(
            self,
            "&About",
            slot=self.helpAbout,
            tip="About the application",
            shortcut="Ctrl+?",
            icon=f"{resources}/info.png",
        )
        settingsAction = QtUtil.createAction(
            self,
            "Se&ttings",
            slot=self.adjustSettings,
            shortcut="Ctrl+Alt+S",
            icon=f"{resources}/settings.png",
            tip="Adjust application settings",
        )
        QtWidgets.QShortcut(QtGui.QKeySequence("CTRL+Q"), self, self.close)  # noqa

        # To right-align the help toolbar.
        spacer = QtWidgets.QWidget(self)
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )

        # Build the main toolbars.
        helpToolbar = self.addToolBar("Help tools")
        helpToolbar.addWidget(spacer)
        helpToolbar.addAction(settingsAction)
        helpToolbar.addSeparator()
        helpToolbar.addAction(helpAboutAction)

        # Build the status bar.
        actionProgressBar = QtUtil.BackgroundProgressBar()
        actionProgressBar.hide()
        self._sourceManager.backgroundActionStarted.connect(actionProgressBar.showActionProgress)
        self._sourceManager.backgroundActionProgressChanged.connect(actionProgressBar.setActionProgressValue)
        self._sourceManager.backgroundActionCompleted.connect(actionProgressBar.hideActionProgress)

        self._status = QtUtil.StatusBar()
        self.setStatusBar(self._status)
        self._status.addPermanentWidget(actionProgressBar)

        # Enumerate images sources
        splash.setProgress(50, "Enumerating images sources...")
        self._sourceManager.enumerateSources()

        # Finalize the main window initialization once it is built.
        QtCore.QTimer.singleShot(0, self.initUI)

    def initUI(self):
        """Intialize the main window to its last position.

        Called on an immediate timer once the main windows is built.
        """
        self._splash.setProgress(70, "Load user settings")

        settings = Config.fotocopSettings

        self.move(settings.windowPosition[0], settings.windowPosition[1])
        self.resize(settings.windowSize[0], settings.windowSize[1])

        self._sourceManager.selectLastSource(settings.lastSource)
        self._downloader.selectDestination(Path(settings.lastDestination))

        self._splash.setProgress(100)

    def showStatusMessage(self, msg: str, isWarning: bool = False, delay: int = None):
        """Convenient function to display a status message.

        Encapsulate the displayMessage method of the customized statusBar.

        Args:
            msg: the message string to display.
            isWarning: True when the message is a warning
                (displayed in WARNING_MSG_STYLE for a longer default time).
            delay: the time to keep the message displayed
                (default is 5s for an information and 2s for a warning).
        """
        self._status.displayMessage(msg, isWarning, delay)

    def okToContinue(self) -> bool:
        """Authorize app exit, project creation or loading.

        Ask for confirmation if the project is valid and has pending changes.

        Returns:
            True if action is authorized, False otherwise.
        """
        # if self.project and self.project.isValid and self.project.isDirty:
        #     reply = QtWidgets.QMessageBox.question(
        #         self,  # noqa
        #         f"{QtWidgets.qApp.applicationName()} - Unsaved Changes",
        #         "Save project changes?",
        #         (
        #             QtWidgets.QMessageBox.Yes
        #             | QtWidgets.QMessageBox.No
        #             | QtWidgets.QMessageBox.Cancel
        #         ),
        #     )  # noqa
        #     if reply == QtWidgets.QMessageBox.Cancel:
        #         return False
        #     elif reply == QtWidgets.QMessageBox.Yes:
        #         return self.saveProject()
        return True

    @QtCore.pyqtSlot()
    def adjustSettings(self):
        # TODO: Create a settings dialog.
        """Show the Fotocop settings dialog.

        If dialog is accepted, the settings changes are saved.
        """
        pass
        # form = SettingsView(parent=self)
        # if form.exec_():
        #     Config.fotocopSettings.save()

    @QtCore.pyqtSlot()
    def helpAbout(self):
        """Show the Fotocop 'About' dialog."""
        pass
        resources = Config.fotocopSettings.resources
        appName = __about__.__title__
        QtWidgets.QMessageBox.about(
            self,  # noqa
            f"{appName} - About",
            f"""
            <p><b>{appName}</b> {__about__.__version__}</p>
            <p>{__about__.__summary__}.</p>
            <br>
            <p>
            Designed and develop by {__about__.__author__}
            ({__about__.__email__})
            </p>
            <p>
            Under {__about__.__license__} license - {__about__.__copyright__}
            </p>
            <br>
            <p>
            Powered by
            <a href="https://www.python.org/">
            <img style="vertical-align:middle" src="{resources}/pythonlogo.svg" alt="Powered by Python" height="32"></a>
             and
            <a href="https://www.qt.io/">
            <img style="vertical-align:middle" src="{resources}/qtlogo.svg" alt="Powered by Qt" height="32"></a>
            </p>
            <p>
            Icons selection from icons8.com <a href="https://icons8.com">
            <img style="vertical-align:middle" src="{resources}/icons8.png" alt="icons8.com" height="32"></a>
            </p>
            """,
        )  # noqa

    def keyPressEvent(self, e: QtGui.QKeyEvent):
        """Trap the Escape key to close the application.

        Reimplement the parent QMainWindow event handler to trap the Escape key
        pressed event. Other key pressed event are passed to the parent.

        Args:
            e: keyboard's key pressed event
        """
        if e.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Trap the main window close request to allow saving pending changes.

        If action is confirmed, save the application settings.

        Args:
            event: the window close request
        """
        if self.okToContinue():
            Config.fotocopSettings.windowPosition = (
                self.frameGeometry().x(),
                self.frameGeometry().y(),
            )
            Config.fotocopSettings.windowSize = (
                self.geometry().width(),
                self.geometry().height(),
            )

            try:
                Config.fotocopSettings.save()
            except Config.settings.SettingsError:
                reply = QtWidgets.QMessageBox.question(
                    self,  # noqa
                    f"{QtWidgets.qApp.applicationName()} - Exit confirmation",
                    f"Cannot save the settings file {Config.fotocopSettings.settingsFile}: quit anyway?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                )  # noqa
                if reply == QtWidgets.QMessageBox.No:
                    # reject dialog close event
                    event.ignore()
            # Saving fotocopSettings OK or reply = QMessageBox.Yes: accept dialog close event
            else:
                self._sourceManager.close()
        else:
            event.ignore()


def QtMain():
    """Main Graphical Interface entry point.

    Retrieves settings, initiatizes the whole application logging. Then initializes
    a Qt Application and the application main view.
    Display a splash screen during application initialization and start the
    Qt main loop.
    """
    # Retrieve the fotocop app settings.
    settings = Config.fotocopSettings
    resources = settings.resources

    logFile = settings.appDirs.user_log_dir / "fotocop.log"
    logConfig = LogConfig(
        logFile,
        settings.logLevel,
        logOnConsole=True,
    )
    logConfig.initLogging()

    logger.info("Fotocop is starting...")

    # QT_SCALE_FACTOR environment variable allow to zoom the HMI for better.
    # readability
    if "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = settings.qtScaleFactor

    # Initialize the Application, apply a custom style, set the app's icon and
    # increase the default font size.
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle(QtUtil.MyAppStyle())
    app.setStyleSheet("QSplitter::handle { background-color: gray }")
    app.setApplicationName("Fotocop")
    app.setAttribute(QtCore.Qt.AA_DisableWindowContextHelpButton)  # noqa
    app.setWindowIcon(QtGui.QIcon(f"{resources}/fotocop.svg"))
    f = app.font()
    fSize = f.pointSize()
    f.setPointSize(fSize + 2)
    app.setFont(f)

    # Initialize the images sources manager.
    sourceManager = SourceManager()

    # Build and show the splash screen.
    splash = QtUtil.SplashScreen(
        f"{resources}/splashscreen600.png",
        __about__.__version__,
        QtCore.Qt.WindowStaysOnTopHint
    )
    splash.show()

    # Build and show the main view after the splash screen delay.
    mainView = QtMainView(sourceManager, splash)
    splash.finish(mainView)
    mainView.show()

    # Start the Qt main loop.
    app.exec_()

    logger.info("Fotocop is closing...")

    logConfig.stopLogging()


if __name__ == "__main__":
    QtMain()
