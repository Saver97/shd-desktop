"""Per-user Windows desktop background context menu registration."""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from shd_desktop.integration.startup import public_executable, startup_command
from shd_desktop.resources import ASSETS


MENU_KEY = r"Software\Classes\DesktopBackground\Shell\SHDDesktop"


def quick_command(action: str) -> str:
    """The public EXE forwards to an existing process before extracting Qt."""
    return f"{startup_command()} --{'new-note' if action == 'note' else 'show-center'}"


def menu_command() -> str:
    return quick_command("center")


def note_menu_key() -> str:
    return MENU_KEY + "NewNote"


def note_menu_command() -> str:
    return quick_command("note")


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY + r"\command") as key:
            command, _ = winreg.QueryValueEx(key, "")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, note_menu_key() + r"\command") as key:
            note_command, _ = winreg.QueryValueEx(key, "")
        return (command.casefold() == menu_command().casefold()
                and note_command.casefold() == note_menu_command().casefold())
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool) -> None:
    if enabled:
        icon = (f'"{public_executable()}"' if getattr(sys, "frozen", False)
                else str(ASSETS / "app.ico"))
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, MENU_KEY, 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "打开 SHD Desktop")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(key, "Position", 0, winreg.REG_SZ, "Top")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, MENU_KEY + r"\command", 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, menu_command())
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, note_menu_key(), 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "新建 SHD 便签")
            winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon)
            winreg.SetValueEx(key, "Position", 0, winreg.REG_SZ, "Top")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, note_menu_key() + r"\command", 0,
                                winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, note_menu_command())
    else:
        for path in (MENU_KEY + r"\command", MENU_KEY,
                     note_menu_key() + r"\command", note_menu_key()):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                pass
