# https://abdus.dev/posts/python-monitor-usb/

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Callable, List

import win32api, win32con, win32gui
import wmi

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@dataclass
class Drive:
    letter: str
    label: str
    drive_type: str

    @property
    def is_removable(self) -> bool:
        return self.drive_type == 'Removable Disk'


class DeviceListener:
    """
    Listens to Win32 `WM_DEVICECHANGE` messages
    and trigger a callback when a device has been plugged in or out

    See: https://docs.microsoft.com/en-us/windows/win32/devio/wm-devicechange
    """
    WM_DEVICECHANGE_EVENTS = {
        0x0019: ('DBT_CONFIGCHANGECANCELED', 'A request to change the current configuration (dock or undock) has been canceled.'),
        0x0018: ('DBT_CONFIGCHANGED', 'The current configuration has changed, due to a dock or undock.'),
        0x8006: ('DBT_CUSTOMEVENT', 'A custom event has occurred.'),
        0x8000: ('DBT_DEVICEARRIVAL', 'A device or piece of media has been inserted and is now available.'),
        0x8001: ('DBT_DEVICEQUERYREMOVE', 'Permission is requested to remove a device or piece of media. Any application can deny this request and cancel the removal.'),
        0x8002: ('DBT_DEVICEQUERYREMOVEFAILED', 'A request to remove a device or piece of media has been canceled.'),
        0x8004: ('DBT_DEVICEREMOVECOMPLETE', 'A device or piece of media has been removed.'),
        0x8003: ('DBT_DEVICEREMOVEPENDING', 'A device or piece of media is about to be removed. Cannot be denied.'),
        0x8005: ('DBT_DEVICETYPESPECIFIC', 'A device-specific event has occurred.'),
        0x0007: ('DBT_DEVNODES_CHANGED', 'A device has been added to or removed from the system.'),
        0x0017: ('DBT_QUERYCHANGECONFIG', 'Permission is requested to change the current configuration (dock or undock).'),
        0xFFFF: ('DBT_USERDEFINED', 'The meaning of this message is user-defined.'),
    }

    def __init__(self, on_change: Callable[[List[Drive]], None]):
        self.on_change = on_change

    def _create_window(self):
        """
        Create a window for listening to messages
        https://docs.microsoft.com/en-us/windows/win32/learnwin32/creating-a-window#creating-the-window

        See also: https://docs.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-createwindoww

        :return: window hwnd
        """
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._on_message
        # wc.lpfnWndProc = {win32con.WM_DEVICECHANGE:self._on_message}
        wc.lpszClassName = self.__class__.__name__
        wc.hInstance = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(class_atom, self.__class__.__name__, 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None)

    def start(self):
        logger.info(f'Listening to drive changes')
        hwnd = self._create_window()
        logger.debug(f'Created listener window with hwnd={hwnd:x}')
        logger.debug(f'Listening to messages')
        win32gui.PumpMessages()

    def _on_message(self, hwnd: int, msg: int, wparam: int, lparam: int):
        if msg != win32con.WM_DEVICECHANGE:
            print('Get msg:', msg)
            return 0
        event, description = self.WM_DEVICECHANGE_EVENTS[wparam]
        logger.debug(f'Received message: {event} = {description}')
        if event in ('DBT_DEVICEREMOVECOMPLETE', 'DBT_DEVICEARRIVAL'):
            logger.info('A device has been plugged in (or out)')
            self.on_change(self.list_drives())
        return 0

    @staticmethod
    def list_drives() -> List[Drive]:
        """
        Get a list of drives using WMI
        :return: list of drives
        """
        c = wmi.WMI()
        devices = list()
        device = dict()
        for disk in c.Win32_LogicalDisk():
            if disk.DriveType in (2, 3, 4) and disk.FileSystem:
                device['deviceid'] = disk.DeviceId
                device['volumename'] = disk.VolumeName
                device['drivetype'] = disk.DriveType
                devices.append(device)

        # proc = subprocess.run(
        #     args=[
        #         'powershell',
        #         '-noprofile',
        #         '-command',
        #         'Get-WmiObject -Class Win32_LogicalDisk | Select-Object deviceid,volumename,drivetype | ConvertTo-Json'
        #     ],
        #     text=True,
        #     stdout=subprocess.PIPE
        # )
        # if proc.returncode != 0 or not proc.stdout.strip():
        #     logger.error('Failed to enumerate drives')
        #     return []
        # devices = json.loads(proc.stdout)

        drive_types = {
            0: 'Unknown',
            1: 'No Root Directory',
            2: 'Removable Disk',
            3: 'Local Disk',
            4: 'Network Drive',
            5: 'Compact Disc',
            6: 'RAM Disk',
        }

        return [Drive(
            letter=d['deviceid'],
            label=d['volumename'],
            drive_type=drive_types[d['drivetype']]
        ) for d in devices]


def on_devices_changed(drives: List[Drive]):
    removable_drives = [d for d in drives if d.is_removable]
    logger.debug(f'Connected removable drives: {removable_drives}')
    for drive in removable_drives:
        backup(drive)


def backup(drive: Drive):
    if drive.label != 'ABDUS':
        return
    logger.info('Backup drive has been plugged in')
    logger.info(f'Backing up {drive.letter}')


if __name__ == '__main__':
    listener = DeviceListener(on_change=on_devices_changed)
    listener.start()
