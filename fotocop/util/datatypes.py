"""Global constants, enum and generic classes and types.
"""
import subprocess
import threading
from typing import NamedTuple, Tuple, List
from enum import Enum, auto
from pathlib import Path
#
# Constants used to display status and console messages.
#
DEFAULT_COLOR = (0, 0, 0, 0)
DEFAULT_MSG_STYLE = f"""
    QStatusBar{{padding-left:8px;
    background:rgba{DEFAULT_COLOR};
    color:black;
    font-weight:bold;}}
"""
WARNING_COLOR = (255, 153, 153, 255)
WARNING_MSG_STYLE = f"""
    QStatusBar{{padding-left:8px;
    background:rgba{WARNING_COLOR};
    color:black;
    font-weight:bold;}}
"""
DEFAULT_MSG_DELAY = 2000    # 2 s
WARNING_MSG_DELAY = 5000    # 5 s

BACKGROUND_COLOR = '#F3F8FE'

DEFAULT_PUID_PREFIX = 'DCFS'
DEFAULT_ADAPTER_PREFIX = 'ADP'

#
# Constants defining defaults for optional DCFS Project spec items.
#
DEFAULT_VARIABILITY_MODEL_FILE = 'VariabilityModel.txt'
DEFAULT_DOMAIN_REPOSITORY = 'DOMAIN_ADAPTERS'
DEFAULT_VARCONF_REPOSITORY = 'VariabilityConfigurations'
DEFAULT_PL_REPOSITORY = 'PLs'
DEFAULT_ICD_REPOSITORY = 'ICD'
DEFAULT_OUTPUT_DIR = 'output'
DEFAULT_LOGFILE = 'dcfsBuilder.log'
LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
DEFAULT_LOGLEVEL = 'INFO'
CSV_PARAM_FILE = 'Param'
CSV_ITF_FILE = 'FunctionalInterface'
CSV_A429_FILE = 'A429FunctionalData'
CSV_A664_FILE = 'A664FunctionalData'
CSV_RAM_FILE = 'RAMFunctionalData'
CSV_DIS_FILE = 'DISFunctionalData'
CSV_PROCLIST_FILE = 'ProcessingList'
CSV_PROC_FILE = 'Processing'
CSV_FILES = [CSV_PARAM_FILE, CSV_ITF_FILE, CSV_A429_FILE, CSV_A664_FILE,
             CSV_RAM_FILE, CSV_DIS_FILE, CSV_PROCLIST_FILE, CSV_PROC_FILE]
CSV_DELIMITER = '|'
DEFAULT_DCFS_FILE = 'dcfs.xml'
DCFS_NAMESPACE = 'http://www.thalesgroup.com/data_concentration'
SOURCE_PARAM_ID = 'SOURCE'
RANGE_PARAM_ID = 'RANGE'
INPUTS_TYPE = ('EXTERNAL', 'INTERMEDIATE', 'COMPLEMENTARY', 'TUNABLE_PARAM')
OUTPUTS_TYPE = ('EXTERNAL', 'INTERMEDIATE')
VALIDITY_IDENTS = (
    'Refreshed', 'NO', 'NO_NCD', 'NO_FT', 'NO_NCD_FT', 'NO_NCDonGND',
    'NO_FTonGND', 'NO_NCDonGND_FT', 'NO_NCD_FTonGND', 'NO_NCDonGND_FTonGND'
)
DATA_TYPE = ('integer', 'real', 'bool', 'opaque')
POSITIONS_CONV = {
    'ALL_POSITIONS': 'ALL',
    'OUTER_POSITIONS': 'OUTER',
    'CENTER_POSITIONS': 'CENTER',
    'LEFT_POSITIONS': 'LEFT',
    'RIGHT_POSITIONS': 'RIGHT'
}
DATAHUB_INPUT_ROLE = 'input'
DATAHUB_OUTPUT_ROLE = 'output'
OUTPUT_COPY_PREFIX = 'Copy'





def makeAbsolute(path: Path, rootPath: Path) -> Path:
    """Make a 'relative to rootpath' path absolute.

    Args:
        path: a path relative to rootPath.
        rootPath: the rootPath of the project.

    Returns:
        An absolute path from rootPath
    """
    if not path.is_absolute():
        path = rootPath / path
    return path


def rmtree(root: Path):
    """Recursively delete a directory and all its content.

    Args:
        root: the Path of the directory to delete.
    """
    for p in root.iterdir():
        if p.is_dir():
            rmtree(p)
        else:
            p.unlink()
    root.rmdir()


def _copy(self: Path, target: Path):
    """Copy 'self' file into 'target'.

    Args:
        self: Path to an existing file.
        target: Path of the file's copy.

    Raises:
        AssertionError if 'self' is not an existing file.
    """
    import shutil
    assert self.is_file()
    shutil.copy(str(self), str(target))  # str() only there for Python < (3, 6)


# Monkey patch of pathlib.Path to add a copy method
Path.copy = _copy


def _copytree(self, target):
    """Copy 'self' directory into 'target'.

    Args:
        self: Path to an existing directory.
        target: Path of the directory's copy.

    Raises:
        AssertionError if 'self' is not an existing directory.
    """
    import shutil
    assert self.is_dir()
    shutil.copytree(str(self), str(target))  # str() only there for Python < (3, 6)


# Monkey patch of pathlib.Path to add a copytree method
Path.copytree = _copytree


def dictOfDictUnion(d1, *others):
    """A convenient function to aggregate several Dict of Dict.

    The first dict'keys are the same for all dict of dict to aggregate.

    Args:
        d1: a Dict of Dict object.
        others: others optional Dict of Dict (may be None).

    Returns:
        the aggregated Dict of Dict.
    """
    if not others or others == (None,):
        return d1

    d2, *others = others
    d = dict()
    for key in d1.keys():
        d[key] = dict(d1[key], **d2[key])

    return dictOfDictUnion(d, *others)


def isGitInstalled() -> bool:
    """Convenient function to check if Git is installed on the running platform.

    Returns:
        True if Git is installed, False otherwise
    """
    try:
        subprocess.check_call(
            ['git', '--version'],
            timeout=5,  # seconds
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return False
    except subprocess.CalledProcessError:
        return False
    except OSError:
        return False
    return True


def runCommand(command: List[str], cwd: Path = None) -> Tuple[str, str]:
    output = ''
    error = ''
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            encoding='utf-8',
            cwd=cwd)
    except OSError as e:
        error = f'Could not run command: {" ".join(command)} {e}'
        return output, error
    else:
        if completed.returncode == 0:
            output = completed.stdout
        else:
            error = completed.stderr
        return output, error


class ExternalCommandError(Exception):
    pass


class ExternalCommand:
    """Enables to run subprocess commands in a different thread with TIMEOUT.

    Based on jcollado's solution:
    http://stackoverflow.com/questions/1191374/subprocess-with-timeout/4825933#4825933
    """
    command = None
    process = None
    status = None
    output, error = '', ''

    def __init__(self, command: List[str], cwd: Path = None):
        self.command = [c for c in command if c]
        self.workingDir = cwd

    def __repr__(self) -> str:
        return ' '.join(self.command)

    def run(self, timeout:int = None, **kwargs) -> str:
        """Run an external command process.

        The command process is started on a dedicated thread. It is killed after
        'timeout' if not finished.

        Returns:
            the command output on its stdOut channel.
        Raises:
            ExternalCommandError: if the command exitCode is not 0 or command
                reports an error strin on its stdErr channel or if the command
                shall be killed after 'timeout'.
        """
        def target(**kw):
            try:
                self.process = subprocess.Popen(self.command, **kw)
                self.output, self.error = self.process.communicate()
                self.status = self.process.returncode
            except OSError as e:
                self.error = f'Could not run command: {" ".join(self.command)} {e}'
                self.status = -1

        # default stdout and stderr
        if 'stdout' not in kwargs:
            kwargs['stdout'] = subprocess.PIPE
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
        if 'encoding' not in kwargs:
            kwargs['encoding'] = 'utf-8'
        if self.workingDir and 'cwd' not in kwargs:
            kwargs['cwd'] = self.workingDir

        # thread
        thread = threading.Thread(target=target, kwargs=kwargs)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            if self.process:
                self.process.terminate()
            thread.join()
            self.error = f'Command too long, aborted after {timeout}s: {" ".join(self.command)}'
            self.status = -1
        # if self.status != 0 or self.error:
        if self.status != 0:
            raise ExternalCommandError(f'[{self.status}] {self.output}\n{self.error}')
        if self.error:
            output = f'{self.output}\n{self.error}'
        else:
            output = self.output
        return output


class CommandStatus(Enum):
    """Authorized status of a command in its command report.

    REJECTED: the command cannot be satisfied.
    IN_PROGRESS: the command is running.
    COMPLETED : The command has terminated with success.
    FAILED: The command has terminated with errors.
    """
    REJECTED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()


class CommandReport(NamedTuple):
    """To be returned by any model's commands.

    Class attributes:
        status: the command status as defined above.
        reason: a message to explicit the status.
    """
    status: CommandStatus
    reason: str = None

    def __add__(self, other):
        if not isinstance(other, CommandReport):
            raise TypeError(
                f'Can only concatenate CommandReport'
                f' (not {other.__class__.__name__}) to CommandReport'
            )

        if other.status == self.status:
            status = self.status
        elif self.status in (CommandStatus.REJECTED, CommandStatus.FAILED):
            status = self.status
        elif other.status in (CommandStatus.REJECTED, CommandStatus.FAILED):
            status = other.status
        elif self.status is CommandStatus.IN_PROGRESS or other.status is CommandStatus.IN_PROGRESS:
            status = CommandStatus.IN_PROGRESS
        else:
            status = CommandStatus.COMPLETED

        reason = f'{self.reason}\n{other.reason}'

        return CommandReport(status, reason)

    def __repr__(self) -> str:
        reason = f', {self.reason}' if self.reason else ''
        return f'CommandReport({self.status.name}{reason})'


class MsgSeverity(Enum):
    """Severity of a message to be display in a status bar or console.

    INFO: for information only.
    WARNING: Reclaims user attention.
    """
    INFO = auto()
    WARNING = auto()


class ProjectChange(Enum):
    """Reason of a ModelChanged signal for a DCFS Project.

    NEW: the project path has changed.
    UPDATE: the current project spec has changed,
    VARMOD: the current project variability model has changed.
    SAVE:  the current project spec has been saved.
    SESSION: the current project session has changed
    VARCONF: the current project variability configurations list has changed
    """
    NEW = auto()
    UPDATE = auto()
    VARMOD = auto()
    SAVE = auto()
    SESSION = auto()
    VARCONF = auto()


class ProjectItemKind(Enum):
    """Kind of project's items showed in the Project browser."""
    UNDEFINED = auto()
    ROOT = auto()
    PROJECT = auto()
    VARMOD = auto()
    DOMAIN_REPO = auto()
    DOMAIN_ADAPTER = auto()
    ADAPTER_VARIANT = auto()
    VARCONF_REPO = auto()
    VARCONF = auto()
    SPECIFIC_REPO = auto()
    SPECIFIC_ADAPTER = auto()
    EXCLUDED_ADAPTERS = auto()
    EXCLUDED_ADAPTER = auto()


class DcfsDataKind(Enum):
    """Kind of DCFS data's items."""
    PARAM = auto()  # A param for Dcfs data parameterization.
    ITF = auto()    # A functional interface.
    TUN = auto()    # A tunable parameter.
    ITD = auto()    # An intermediate data.
    A429 = auto()   # An A429 functional data.
    A664 = auto()   # An A664 functional data.
    RAM = auto()    # A RAM functional data.
    DIS = auto()    # A discrete functional data.
    PRC = auto()    # A processing.
    DTH = auto()    # A datahub.


# Map a Dcfs data kind literal to its name in the DCFS.
DCFS_DATA_KIND_MAP = {
    DcfsDataKind.ITF: 'EXTERNAL',
    DcfsDataKind.TUN: 'TUNABLE_PARAM',
    DcfsDataKind.ITD: 'INTERMEDIATE'
}

ITF_TO_DCFS_DATA_KIND = {
    'EXTERNAL': DcfsDataKind.ITF,
    'INTERMEDIATE': DcfsDataKind.ITD,
    'COMPLEMENTARY': DcfsDataKind.ITD,
    'TUNABLE_PARAM': DcfsDataKind.TUN
}

# Map a media name in DCFS to its Dcfs data kind literal.
MEDIA_TO_DCFS_DATA_KIND = {
    'A429': DcfsDataKind.A429,
    'RAM': DcfsDataKind.RAM,
    'A664p3': DcfsDataKind.A664,
    'A664p7': DcfsDataKind.A664,
    'DISCRETE': DcfsDataKind.DIS
}


MEDIA_COLOR = {
    'A429': 'darkGreen',
    'RAM': 'darkslateblue',
    'A664': 'darkCyan',
    'A664p3': 'darkCyan',
    'A664p7': 'darkCyan',
    'DISCRETE': 'darkorange',
    'OTHER': 'black',
    'ERROR': 'firebrick'
}


class DcfsDataScope(Enum):
    """Scope of DCFS data's items.

    LOCAL:  Local to the adapter or variant.
    FAMILY: Global to all variants of a domain adapter or to all specific
            adapters of a variability configuration.
    GLOBAL: Global to all the project adapters and variants.
    """
    LOCAL = auto()
    FAMILY = auto()
    GLOBAL = auto()


class Position(Enum):
    """Available positions of a partition."""
    OL = auto()
    OR = auto()
    CU = auto()
    CD = auto()


class PositionGroup(Enum):
    """Available groups of positions.

    Use to restrict a flow to a set of positions.
    """
    ALL = auto()
    OUTER = auto()
    CENTER = auto()
    LEFT = auto()
    RIGHT = auto()


# By default, a flow is defined for all positions.
DEFAULT_POSITIONS_GROUP = PositionGroup.ALL.name


class Media(Enum):
    """Available media in SD-ACICD."""
    A429 = 1
    RAM = 2
    A664p3 = 3
    A664p7 = 4
    DISCRETE = 5


class MediaFilter(Enum):
    """Available SD-ACICD media filtering options in the IcdBrowser."""
    ALL = 0
    A429 = 1
    RAM = 2
    A664p3 = 3
    A664p7 = 4
    DISCRETE = 5


class Direction(Enum):
    """Available interface directions in SD-ACICD."""
    IN = 1
    OUT = 2


class DirFilter(Enum):
    """Available SD-ACICD direction filtering options in the IcdBrowser."""
    ALL = 0
    IN = 1
    OUT = 2


class IcdDataType(Enum):
    """Available data types in SD-ACICD."""
    FLOAT = auto()
    DOUBLE = auto()
    INTEGER = auto()
    BOOLEAN = auto()
    OPAQUE_VAR = auto()
    OPAQUE_FIX = auto()
    ENUMERATE = auto()
    STRING = auto()


class Partition(Enum):
    """Available partitions of a DCFS project."""
    IO_A = auto()
    IO_C = auto()


class ParamKind(Enum):
    """Available kind of parameters.

    ENUM:   The param will be replaced by the enum members.
    SOURCE: The param will be replaced integer in range 1 to N.
    RANGE:  The param will be replaced integer in range P to Q.
    """
    ENUM = auto()
    SOURCE = auto()
    RANGE = auto()


class FlowIoKind(Enum):
    """Available kind of flow input/output."""
    INPUT = auto()
    OUTPUT = auto()
    OUT_COPY = auto()


class ClipboardAction(Enum):
    """Identify the action that put data in the clipboard.

    COPY:   The clipboard content shall be copied, keeping the source data.
    MOVE:   The clipboard content shall be moved, removing the source data.
    """
    COPY = auto()
    MOVE = auto()


class PortType(str, Enum):
    none = 'none'
    input = 'input'
    output = 'output'


# Types definitions
DcfsDataKey = Tuple[DcfsDataScope, DcfsDataKind, str]
