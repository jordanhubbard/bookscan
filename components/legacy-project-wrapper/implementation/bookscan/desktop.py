"""Packaged icon and per-user Linux desktop integration."""
import os
from pathlib import Path
import shutil
import sys

ICON_PATH = Path(__file__).parent / 'assets' / 'bookscan.png'


def desktop_exec_argument(value):
    """Quote a literal argument for desktop-entry string and Exec parsing."""
    if any(character in value for character in '\n\r\x00'):
        raise ValueError('Desktop launcher paths must be single-line values')
    escaped = ''.join('\\' + char if char in '\\"`$' else char for char in value)
    return '"' + escaped.replace('\\', '\\\\').replace('%', '%%') + '"'


def install_desktop(data_home=None, executable=None):
    if not sys.platform.startswith('linux'):
        raise OSError('Desktop launcher installation is currently supported on Linux')
    data_home = Path(data_home or os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share').expanduser().absolute()
    interpreter = str(Path(executable or sys.executable).absolute())
    if '=' in interpreter:
        raise ValueError('Desktop launcher executable paths cannot contain an equals sign')
    icon = data_home / 'pixmaps' / 'bookscan.png'
    if any(character in str(icon) for character in '\n\r\x00'):
        raise ValueError('Desktop launcher paths must be single-line values')
    desktop = data_home / 'applications' / 'bookscan.desktop'
    icon.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON_PATH, icon)
    icon_value = str(icon).replace('\\', '\\\\')
    desktop.write_text(
        '[Desktop Entry]\n'
        'Type=Application\n'
        'Name=BookScan\n'
        'Comment=Scan, edit, and organize book pages\n'
        f'Exec={desktop_exec_argument(interpreter)} -m bookscan\n'
        f'Icon={icon_value}\n'
        'Terminal=false\n'
        'Categories=Graphics;Scanning;\n'
        'Keywords=book;scan;camera;document;PDF;\n'
        'StartupNotify=true\n', encoding='utf-8')
    return desktop
