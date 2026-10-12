"""Current-user Windows startup registration for the desktop app."""

from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SHDDesktop"


def public_executable() -> Path:
    """Return the distributable launcher when running from its cached core."""
    if getattr(sys, "frozen", False):
        supplied = os.getenv("SHD_PUBLIC_EXE")
        if supplied:
            launcher = Path(supplied).resolve()
            if launcher.name.casefold() == "shddesktop.exe" and launcher.is_file():
                return launcher
    return Path(sys.executable).resolve()


def startup_command() -> str:
    executable = public_executable()
    if getattr(sys, "frozen", False):
        return f'"{executable}"'
    pythonw = executable.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else executable}" "{Path(__file__).resolve().parent / "app.py"}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            saved, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return saved.casefold() == startup_command().casefold()
    except FileNotFoundError:
        return False


def migrate_enabled() -> bool:
    """Keep a user's existing autostart choice when the EXE moves on upgrade."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            saved, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    if saved.casefold() == startup_command().casefold():
        return False
    if not (saved.startswith('"') and saved.endswith('"')
            and Path(saved[1:-1]).name.casefold() == "shddesktop.exe"):
        return False
    set_enabled(True)
    return True


def set_enabled(enabled: bool) -> None:
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
