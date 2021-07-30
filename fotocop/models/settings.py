"""The FotocopSettings model.

The FotocopSettings model defines the fotocop application settings and make them
accessible through out the application by exposing a fotocopSettings instance.

As a model, it emit a 'modelChanged' signal when one of its attributes changes.
"""
from fotocop.util import settings
from fotocop.util import signal
from fotocop.util import datatypes as dt

__all__ = ['fotocopSettings']


class FotocopSettings(settings.Settings):
    """The FotocopSettings model definition.

    The FotocopSettings model is a specialization of the Settings singleton base
    class. It declares:
        the modelChanged signal to comply with the model interface,
        a set of Setting descriptor corresponding to the DCFS application
            settings,

    Class attributes:
        modelChanged: a signal emitted on session changes.
        defaultDirectory: Path to the default projects directory.
        lastProject: Path to the last open DCFS project.
        logLevel: The global DCFS application log level.
        windowPosition: the last DCFS application windows top left corner.
        windowSize: the last DCFS application windows size.
        itfDialogPosition: the last Interfaces editor top left corner.
        itfDialogSize: the last Interfaces editor size.
        qtScaleFactor: A magnifying factor to increase the DCFS application
            lisibility

    Attributes:
        appDirs (WinAppDirs): A WinAppDirs NamedTuple containing the user app
            directories paths.
        resources (Path): Path to the UI resources directory (images, icons,..).
        settings (List[str]): the list of settings names.
    """

    modelChanged = signal.Signal(name='SettingsChanged')

    defaultDirectory = settings.Setting(defaultValue='F:/Users/Images/Mes Photos/Négatifs')
    lastProject = settings.Setting(defaultValue=None)
    logLevel = settings.Setting(defaultValue=dt.DEFAULT_LOGLEVEL)
    windowPosition = settings.Setting(defaultValue=(200, 250))
    windowSize = settings.Setting(defaultValue=(640, 480))
    qtScaleFactor = settings.Setting(defaultValue='1.1')

    def __init__(self):
        self.appDirs = settings.getAppDirs('fotocop')
        self.resources = self.appDirs.user_data_dir / 'resources'

        super().__init__(self.appDirs.user_data_dir / 'settings')

        self.modelChanged.emit()

    def __repr__(self) -> str:
        """A pretty representation of a FotocopSettings.

        Returns:
            A string with the project path and all its spec items.
        """
        return f'FotocopSettings({self.defaultDirectory}, {self.lastProject},' \
               f'{self.logLevel}, {self.windowPosition},' \
               f'{self.windowSize}, {self.qtScaleFactor})'

    def resetToDefaults(self):
        """Reset all settings to their default value."""
        for setting in self.settings:                                   # noqa
            defaultValue = getattr(FotocopSettings, setting).defaultValue
            setattr(self, setting, defaultValue)


fotocopSettings = FotocopSettings()
