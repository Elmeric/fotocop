"""The FotocopSettings model.

The FotocopSettings model defines the fotocop application settings and make them
accessible throughout the application by exposing a fotocopSettings instance.
"""
from fotocop.util import settings

__all__ = ['fotocopSettings']


class FotocopSettings(settings.Settings):
    """The FotocopSettings model definition.

    The FotocopSettings model is a specialization of the Settings singleton base
    class. It declares:
        a set of Setting descriptor corresponding to the Fotocop application
            settings,

    Class attributes:
        defaultDirectory: Path to the default projects directory.
        lastSource: key and info on the last open images' source.
        logLevel: The global Fotocop application log level.
        windowPosition: the last Fotocop application windows top left corner.
        windowSize: the last Fotocop application windows size.
        qtScaleFactor: A magnifying factor to increase the Fotocop application
            lisibility

    Attributes:
        appDirs (WinAppDirs): A WinAppDirs NamedTuple containing the user app
            directories paths.
        resources (Path): Path to the UI resources directory (images, icons,..).
        settings (List[str]): the list of settings names (inherited from Settings).
    """

    DEFAULT_LOGLEVEL = "INFO"

    defaultDirectory = settings.Setting(defaultValue='F:/Users/Images/Mes Photos/Négatifs')
    lastSource = settings.Setting(defaultValue=None)
    logLevel = settings.Setting(defaultValue=DEFAULT_LOGLEVEL)
    windowPosition = settings.Setting(defaultValue=(200, 250))
    windowSize = settings.Setting(defaultValue=(640, 480))
    qtScaleFactor = settings.Setting(defaultValue='1.1')

    def __init__(self):
        self.appDirs = settings.getAppDirs('fotocop')
        self.resources = self.appDirs.user_data_dir / 'resources'

        super().__init__(self.appDirs.user_data_dir / 'settings')

    def __repr__(self) -> str:
        """A pretty representation of a FotocopSettings.

        Returns:
            A string with the project path and all its spec items.
        """
        return f'FotocopSettings({self.defaultDirectory}, {self.lastSource},' \
               f'{self.logLevel}, {self.windowPosition},' \
               f'{self.windowSize}, {self.qtScaleFactor})'

    def resetToDefaults(self):
        """Reset all settings to their default value."""
        for setting in self.settings:                                   # noqa
            defaultValue = getattr(FotocopSettings, setting).defaultValue
            setattr(self, setting, defaultValue)


fotocopSettings = FotocopSettings()
