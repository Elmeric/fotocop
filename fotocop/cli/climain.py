"""Entry point for the Command Line version of fotocop.
"""
import fotocop.__about__ as __about__
from fotocop.util import waiting

__all__ = ['CliMain']


def _showEndMessage(logFile: str, msg: str, success: bool):
    """Shows a success / error meessage and the logFile if it exists.

    Args:
        logFile: filename of the log file
        msg : message to show
        success: True if the builder process succeeds, False otherwise
    """
    if not success:
        if logFile:
            import webbrowser
            webbrowser.open(f'{logFile}')
    print('\n', end='')
    print(msg)
    print('='*len(msg.split('\n')[-1]))


def CliMain(projectPath: str,
            vcName: str,
            logLevel: str) -> int:
    """Main Command Line Interface entry point.

    Loads the project, initializes a session with the given variability
    configuration and log level and runs it.

    Args:
        projectPath: abslotute path to the project directory.
        vcName: name of a Product Line variability configuration.
        logLevel: logger level.

    Returns:
        0 for success.
    """
    msgVersion = f'DCFS Builder {__about__.__version__}'
    print(msgVersion)
    print('=' * len(msgVersion), '\n')

    # # Initialize a DCFS project from the given path.
    # # Abort on invalid project spec.
    # cmdReport, project = projectCreator.getProject(projectPath)
    # if cmdReport.status is not dt.CommandStatus.COMPLETED:
    #     _showEndMessage(
    #         logFile='',
    #         msg=cmdReport.reason,
    #         success=False
    #     )
    #     return 1
    # # The variability configuration shall exist in the project spec.
    # if vcName not in project.variabilityConfigurations:
    #     _showEndMessage(
    #         logFile='',
    #         msg=f'Unknown variability configuration: {vcName}',
    #         success=False
    #     )
    #     return 1
    #
    # # Initialize a builder session.
    # session = Session(project)
    #
    # # Initialize the session logger with given log level
    # logFile = project.logFile
    # session.selectLogLevel(logLevel)
    # logger = session.logger
    # logger.info('Starting builder...')
    #
    # # Initialize the session with the given variability configuration.
    # cmdReport = session.selectVarConf(vcName)
    # if cmdReport.status is not dt.CommandStatus.COMPLETED:
    #     logger.fatal(cmdReport.reason)
    #     _showEndMessage(
    #         logFile=logFile,
    #         msg=cmdReport.reason,
    #         success=False
    #     )
    #     return 1
    #
    # # Start he builder with a console animation.
    # spin = waiting.SpinCursor(msg="Building...", minspin=5, speed=5)
    # spin.start()
    # cmdReport = session.run()
    # spin.join()
    #
    # # Show result
    # _showEndMessage(
    #     logFile=logFile,
    #     msg=cmdReport.reason,
    #     success=cmdReport.status is dt.CommandStatus.COMPLETED
    # )
    return 0
