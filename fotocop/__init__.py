"""Fotocop is a tool to copy images from a movable support such as a SD Card
onto your local HDD.

Images can be renamed according to a user-defined pattern and using EXIF data.

Requires Python >= 3.6.1

Usage:
    Graphic User Interface: ''python -m fotocop''
    Command Line: ''python -m fotocop -h'' for usage description.
"""
__all__ = ['run_main']

import sys
import logging
import argparse

from fotocop.cli import climain as cli
from fotocop.gui import guimain as gui


def _configureParser(parser: argparse.ArgumentParser):
    """Configure an arguments parser from the the standard argparse module.

    Args:
        parser: the argparse parser to configure
    """
    parser.prog = 'python -m fotocop'
    parser.description = 'Copy and rename images from your SD-Card.'

    parser.add_argument(
        '-p',
        '--pattern',
        dest='pattern',
        nargs=1,
        default='YYYYmmDD-HHMMSS',
        # required=True,
        help='pattern to rename images.')

    parser.add_argument(
        '-l',
        '--log',
        dest='loglevel',
        type=str.upper,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        default='INFO',
        help='set the logger level (default is INFO).')


def run_main():
    """Program entry point.

    If launch without arguments, the Graphical User Interface is started,
    otherwise, the Command Line Interface version is used.

    Handles exceptions not trapped earlier.
    """
    if len(sys.argv) > 1:
        # When command line arguments in sys.argv, parse them and launch the cli.
        parser = argparse.ArgumentParser()
        _configureParser(parser)
        args = parser.parse_args()
        kwargs = dict()
        kwargs['pattern'] = args.pattern[0]
        kwargs['logLevel'] = args.loglevel
        main = cli.CliMain
    else:
        # When no command line arguments, launch the gui
        kwargs = dict()
        main = gui.QtMain

    try:
        sys.exit(main(**kwargs))
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.fatal('Fatal error!', exc_info=True)
        sys.stderr.write(f'\nfotocop - {str(e)}\n\n')
        sys.exit(1)


if __name__ == '__main__':
    run_main()
