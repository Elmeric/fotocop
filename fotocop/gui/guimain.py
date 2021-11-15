"""Entry point for the GUI version of fotocop.
"""
import sys
import os
import logging
import time

import PyQt5.QtCore as QtCore
import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui

import fotocop.__about__ as __about__
from fotocop.util.logutil import LogConfig
from fotocop.util import datatypes as dt
from fotocop.util import qtutil as QtUtil

# Models
from fotocop.models import settings as Config
from fotocop.models.sources import SourceManager

# Views
from .sourceselector import SourceSelector
from .thumbnailviewer import ThumbnailViewer
from .timelineviewer import TimelineViewer


__all__ = ["QtMain"]

logger = logging.getLogger(__name__)


class QtMainView(QtWidgets.QMainWindow):
    """The fotocop main view.

    The Main view is composed of:
        The project browser:  browse and edit a project content.
        The adapter editor: browse and edit adapter's flows.
        The interface editor: browse and edit interfaces abd data used as
            adapter's input / ouput.
        The toolbars: the global toolbars (project, edit, session, help) are
            complemented with dynamic toolbars provided by the project browser,
            adapter editor and interface editor.
        The status bar: display information and warning messages.
        The console view: keep a message history and show them on demand

    Args:
        version: application version.
        *args, **kwargs: Any other positional and keyword argument are passed to
            the parent QMainWindow.

    Attributes:
        version (str): application version.
        project (Project): reference to the project model.
        globalActions (GlobalActionHelper): registry and methods hosting the
            edit actions (cut, copy paste and delete) global to the app's views.
        projectBrowser (ProjectBrowser): reference to the project browser.
        adapterEditor (AdapterEditor): reference to the adapter editor.
        interfaceEditor (InterfacesEditor): reference to the interface editor.
        msgHistory (MessageHistory): reference to the messages history model.
        consoleView (ConsoleView): reference to the messages history view.
        isConsoleVisible (bool): the messages history view show/hide state.
        projectSaveAction (QAction): action associated to the save
            toolbar button.
        startAction (QAction): action that start the DCFS XML file generation
            for the selected variability configuration.
        workingVarConfSelector (QCombobow): reference to the current variabiity
            configuration selector.
        consoleButton (QToolButton): button to show/hide the console view.
        status (QStatusBar): reference to the Main window status bar.
    """

    def __init__(self, sourceManager, splash, logConfig, *args, **kwargs):
        super().__init__(*args, **kwargs)

        splash.setProgress(10, "Create Gui objects...")

        self.splash = splash

        resources = Config.fotocopSettings.resources
        selectIcon = QtGui.QIcon(f"{resources}/select.png")

        # Initialize the app's views. Init order to comply with the editors' dependencies.
        self.sourceManager = sourceManager
        # self.sourceManager = SourceManager()
        self.sourceSelector = SourceSelector(self.sourceManager)
        self.destSelector = QtUtil.DirectorySelector(
            label="Destination folder:",
            placeHolder="Path to the destination folder",
            selectIcon=selectIcon,
            tip=f"Select the destination folder. Absolute path or path"
            f" relative to {Config.fotocopSettings.defaultDirectory}",
            directoryGetter=lambda: str(Config.fotocopSettings.defaultDirectory),
            shallExist=True,
            defaultPath="",
            parent=self,
        )
        # https://stackoverflow.com/questions/42673010/how-to-correctly-load-images-asynchronously-in-pyqt5
        self.thumbnailViewer = ThumbnailViewer()

        self.timelineViewer = TimelineViewer()

        self.sourceManager.sourceSelected.connect(self.sourceSelector.displaySelectedSource)
        self.sourceManager.sourceSelected.connect(self.thumbnailViewer.clearImages)
        self.sourceManager.sourceSelected.connect(self.timelineViewer.setTimeline)
        self.sourceManager.imagesBatchLoaded.connect(self.thumbnailViewer.addImages)
        self.sourceManager.thumbnailLoaded.connect(self.thumbnailViewer.updateImage)
        self.sourceManager.datetimeLoaded.connect(self.timelineViewer.updateTimeline)
        self.sourceManager.timelineBuilt.connect(self.timelineViewer.finalizeTimeline)
        self.thumbnailViewer.zoomLevelChanged.connect(self.timelineViewer.zoom)
        self.timelineViewer.zoomed.connect(self.thumbnailViewer.onZoomLevelChanged)

        splash.setProgress(30)

        # Build the main view layout.
        vertSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        vertSplitter.setChildrenCollapsible(False)
        vertSplitter.setHandleWidth(2)
        vertSplitter.addWidget(self.thumbnailViewer)
        vertSplitter.addWidget(self.timelineViewer)
        vertSplitter.setStretchFactor(0, 5)
        vertSplitter.setStretchFactor(1, 1)
        vertSplitter.setOpaqueResize(False)

        horzSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        horzSplitter.setChildrenCollapsible(False)
        horzSplitter.setHandleWidth(2)
        horzSplitter.addWidget(self.sourceSelector)
        horzSplitter.addWidget(vertSplitter)
        horzSplitter.addWidget(self.destSelector)
        horzSplitter.setStretchFactor(0, 1)
        horzSplitter.setStretchFactor(1, 3)
        horzSplitter.setStretchFactor(2, 1)
        horzSplitter.setOpaqueResize(False)

        self.setCentralWidget(horzSplitter)

        # resources = Config.fotocopSettings.resources

        # Build actions used in toolbars.
        # projectNewAction = QtUtil.createAction(
        #     self, '&New...', slot=self.newProject,
        #     shortcut=QtGui.QKeySequence.New, icon=f'{resources}/filenew.png',
        #     tip='Create a new DCFS project')
        # projectOpenAction = QtUtil.createAction(
        #     self, "&Open...", slot=self.openProject,
        #     shortcut=QtGui.QKeySequence.Open, icon=f'{resources}/fileopen.png',
        #     tip="Open an existing DCFS project")
        # self.projectSaveAction = QtUtil.createAction(
        #     self, "&Save", slot=self.saveProject,
        #     shortcut=QtGui.QKeySequence.Save, icon=f'{resources}/filesave.png',
        #     tip="Save the DCFS project")
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
        # showConsoleAction = QtUtil.createAction(
        #     self, "Show", slot=self.toggleConsole,
        #     shortcut="Alt+C", tip="Show last messages")
        # self.startAction = QtUtil.createAction(
        #     self, "Start", slot=self.startBuilder,
        #     shortcut="CTRL+G", icon=QtGui.QIcon(f'{resources}/start.png'),
        #     tip="Generate DCFS XML file")
        QtWidgets.QShortcut(QtGui.QKeySequence("CTRL+Q"), self, self.close)  # noqa

        # The session toolbar content:
        iconSize = QtCore.QSize(40, 40)

        # workingVarConfLabel = QtWidgets.QLabel()
        # workingVarConfLabel.setPixmap(QtGui.QPixmap(f'{resources}/work.png'))
        # self.workingVarConfSelector = QtWidgets.QComboBox()
        # self.workingVarConfSelector.setSizeAdjustPolicy(
        #     QtWidgets.QComboBox.AdjustToContents
        # )
        # self.workingVarConfSelector.setToolTip('Select working variability configuration')
        # self.workingVarConfSelector.setStatusTip('Select a working variability configuration')
        # self.workingVarConfSelector.currentTextChanged.connect(self.selectVarConf)

        # To right-align the help toolbar.
        spacer = QtWidgets.QWidget(self)
        spacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )

        # Build the main toolbars in the right order.
        # projectToolbar = self.addToolBar("Project tools")
        # projectToolbar.setIconSize(iconSize)
        # projectToolbar.addActions(
        #     (projectNewAction, projectOpenAction, self.projectSaveAction)
        # )
        #
        # editToolbar = self.addToolBar("Edit tools")
        # editToolbar.setIconSize(iconSize)
        # editToolbar.addActions(self.globalActions.actions)
        #
        # self.addToolBar(self.projectBrowser.toolbarStack.toolbar())
        # self.addToolBar(self.adapterEditor.flowsTbStack.toolbar())
        # self.addToolBar(self.adapterEditor.flowIoTbStack.toolbar())
        # self.addToolBar(self.vcsController.toolbar())
        #
        # sessionToolbar = self.addToolBar("Session tools")
        # sessionToolbar.setIconSize(iconSize)
        # sessionToolbar.addWidget(workingVarConfLabel)
        # sessionToolbar.addWidget(self.workingVarConfSelector)
        # sessionToolbar.addAction(self.startAction)

        helpToolbar = self.addToolBar("Help tools")
        # helpToolbar.setIconSize(iconSize)
        helpToolbar.addWidget(spacer)
        helpToolbar.addAction(settingsAction)
        helpToolbar.addSeparator()
        helpToolbar.addAction(helpAboutAction)

        # Build the status bar.
        actionProgressBar = QtUtil.BackgroundProgressBar()
        actionProgressBar.hide()
        self.sourceManager.backgroundActionStarted.connect(actionProgressBar.showActionProgress)
        self.sourceManager.backgroundActionProgressChanged.connect(actionProgressBar.setActionProgressValue)
        self.sourceManager.backgroundActionCompleted.connect(actionProgressBar.hideActionProgress)

        self.status = self.statusBar()
        self.status.setSizeGripEnabled(False)
        self.status.addPermanentWidget(actionProgressBar)
        self.status.setStyleSheet(dt.DEFAULT_MSG_STYLE)
        self.status.messageChanged.connect(self.onStatusChanged)

        splash.setProgress(50, "Enumerating images sources...")
        self.sourceManager.enumerateSources()

        QtCore.QTimer.singleShot(0, self.initUI)

    def initUI(self):
        """Intialize the main window to its last position.

        Called on an immediate timer once the main windows is built.
        """
        self.splash.setProgress(70, "Load user settings")

        settings = Config.fotocopSettings

        self.move(settings.windowPosition[0], settings.windowPosition[1])
        self.resize(settings.windowSize[0], settings.windowSize[1])

        self.splash.setProgress(100)

    @QtCore.pyqtSlot(str)
    def onStatusChanged(self, msg: str):
        """Reset the status bar to the default style.

        If there are no arguments (the message is being removed), change the
        status message bar to its default style.

        Args:
            msg: the new temporary status message. Empty string when the
                message has been removed.
        """
        if not msg:
            self.status.setStyleSheet(dt.DEFAULT_MSG_STYLE)

    def showMessage(self, msg: str, isWarning: bool = False, delay: int = None):
        """Convenient function to display a status message.

        Display a temporary message in the status bar with the right
        style.

        Args:
            msg: the message string to display.
            isWarning: True when the message is a warning
                (displayed in WARNING_MSG_STYLE for a longer default time).
            delay: the time to keep the message displayed
                (default is 5s for an information and 2s for a warning).

        """
        if isWarning:
            self.status.setStyleSheet(dt.WARNING_MSG_STYLE)
        else:
            self.status.setStyleSheet(dt.DEFAULT_MSG_STYLE)
        if not delay:
            delay = dt.WARNING_MSG_DELAY if isWarning else dt.DEFAULT_MSG_DELAY
        self.status.showMessage(msg, delay)

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
        """Show the DCFS settings dialog.

        If dialog is accepted, the settings changes are saved.
        """
        pass
        # form = SettingsView(parent=self)
        # if form.exec_():
        #     Config.fotocopSettings.save()

    @QtCore.pyqtSlot()
    def helpAbout(self):
        """Show the DCFS 'About' dialog."""
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
        """Trap the Escape key to close the close the application.

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

            # selection = self.sourceManager.selection
            # source = selection.source
            # if source:
            #     kind = selection.kind
            #     if kind == SourceType.DRIVE:
            #         name = source.id
            #         path = source.selectedPath
            #         subDirs = source.subDirs
            #     elif kind == SourceType.DEVICE:
            #         name = source.name
            #         path = subDirs = None
            #     else:
            #         name = path = subDirs = None
            # else:
            #     kind = SourceType.UNKNOWN
            #     name = path = subDirs = None
            # Config.fotocopSettings.lastSource = (name, kind.name, path, subDirs)

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
            # else:
            #     self.closeProject()
            self.sourceManager.close()
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

    sourceManager = SourceManager()

    # Build and show the splash screen.
    # Use QIcon to render so we get the high DPI version automatically
    size = QtCore.QSize(600, 400)
    pixmap = QtUtil.scaledIcon(f"{resources}/splashscreen600.png", size).pixmap(size)
    splash = QtUtil.SplashScreen(pixmap, __about__.__version__, QtCore.Qt.WindowStaysOnTopHint)
    splash.show()

    # Build and show the main view after the splash screen delay.
    mainView = QtMainView(sourceManager, splash, logConfig)
    splash.finish(mainView)
    mainView.show()

    # Start the Qt main loop.
    app.exec_()

    logger.info("Fotocop is closing...")

    logConfig.stopLogging()


if __name__ == "__main__":
    QtMain()
