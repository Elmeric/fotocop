"""The FotocopSettings model.

The FotocopSettings model defines the fotocop application settings and make them
accessible throughout the application by exposing a fotocopSettings instance.
"""
from typing import TYPE_CHECKING
from pathlib import Path

from win32com.shell import shell, shellcon  # noqa

from fotocop.util import settings
from fotocop.util.settings import Setting
from fotocop.models import naming

if TYPE_CHECKING:
    from fotocop.util.settings import WinAppDirs

__all__ = ["fotocopSettings"]


class FotocopSettings(settings.Settings):
    """The FotocopSettings model definition.

    The FotocopSettings model is a specialization of the Settings singleton base
    class. It declares:
        a set of Setting descriptor corresponding to the Fotocop application
            settings,

    Class attributes:
        lastSource: key and info (kind, id, path and subDirs) on the last opened
            images' source.
        lastDestination: path to the last selected images' destination.
        lastImageNamingTemplate: key of the last selected images' naming template.
        lastDestinationNamingTemplate: key of the last selected images' destination
            naming template.
        lastNamingExtension: the last selected images' extension format.
        logLevel: The global Fotocop application log level.
        windowPosition: the last Fotocop application windows top left corner.
        windowSize: the last Fotocop application windows size.
        qtScaleFactor: A magnifying factor to increase the Fotocop application
            lisibility

    Attributes:
        appDirs: A WinAppDirs NamedTuple containing the user app
            directories paths.
        resources: Path to the UI resources directory (images, icons,..).
    """
    appDirs: "WinAppDirs"
    resources: Path

    _DEFAULT_LOGLEVEL = "INFO"

    lastSource: Setting = settings.Setting(defaultValue=("UNKNOWN", None, None, None))
    lastDestination: Setting = settings.Setting(
        defaultValue=shell.SHGetFolderPath(0, shellcon.CSIDL_MYPICTURES, None, 0)
    )
    lastImageNamingTemplate: Setting = settings.Setting(
        defaultValue=naming.NamingTemplates.defaultImageNamingTemplate
    )
    lastDestinationNamingTemplate: Setting = settings.Setting(
        defaultValue=naming.NamingTemplates.defaultDestinationNamingTemplate
    )
    lastNamingExtension: Setting = settings.Setting(
        defaultValue=naming.Case.LOWERCASE.name
    )
    logLevel: Setting = settings.Setting(defaultValue=_DEFAULT_LOGLEVEL)
    windowPosition: Setting = settings.Setting(defaultValue=(0, 0))
    windowSize: Setting = settings.Setting(defaultValue=(1600, 800))
    qtScaleFactor: Setting = settings.Setting(defaultValue="1.0")

    def __init__(self) -> None:
        # Retrieve or create the user directories for the application.
        appDirs = settings.getAppDirs("fotocop")

        super().__init__(appDirs.user_data_dir / "settings")

        self.appDirs = appDirs
        self.resources = Path(__file__).resolve().parent.parent.parent / "resources"

    def __repr__(self) -> str:
        """A pretty representation of a FotocopSettings.

        Returns:
            A string with the project path and all its spec items.
        """
        return (
            f"FotocopSettings({self.lastSource}, {self.lastDestination}, "
            f"{self.lastImageNamingTemplate}, {self.lastDestinationNamingTemplate}, "
            f"{self.lastNamingExtension}, {self.logLevel}, {self.windowPosition}, "
            f"{self.windowSize}, {self.qtScaleFactor})"
        )

    def resetToDefaults(self) -> None:
        """Reset all settings to their default value."""
        for setting in self.allKeys():
            defaultValue = getattr(FotocopSettings, setting).defaultValue
            setattr(self, setting, defaultValue)


fotocopSettings = FotocopSettings()
