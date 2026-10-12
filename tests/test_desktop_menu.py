"""Desktop menu registration stays within an isolated current-user key."""

import uuid
import winreg
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import shd_desktop.integration.desktop_menu as desktop_menu
desktop_menu.MENU_KEY = rf"Software\SHDDesktop-MenuTest-{uuid.uuid4().hex}"
try:
    assert not desktop_menu.is_enabled()
    desktop_menu.set_enabled(True)
    assert desktop_menu.is_enabled()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, desktop_menu.MENU_KEY) as key:
        assert winreg.QueryValueEx(key, "MUIVerb")[0] == "打开 SHD Desktop"
        assert winreg.QueryValueEx(key, "Position")[0] == "Top"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, desktop_menu.MENU_KEY + r"\command") as key:
        assert winreg.QueryValueEx(key, "")[0] == desktop_menu.menu_command()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, desktop_menu.note_menu_key()) as key:
        assert winreg.QueryValueEx(key, "MUIVerb")[0] == "新建 SHD 便签"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, desktop_menu.note_menu_key() + r"\command") as key:
        assert winreg.QueryValueEx(key, "")[0] == desktop_menu.note_menu_command()
    desktop_menu.set_enabled(False)
    assert not desktop_menu.is_enabled()
    for path in (desktop_menu.MENU_KEY, desktop_menu.note_menu_key()):
        try:
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, path).Close()
        except FileNotFoundError:
            continue
        raise AssertionError(f"menu key was not removed: {path}")
finally:
    desktop_menu.set_enabled(False)

with TemporaryDirectory() as temp:
    executable = Path(temp) / "Runtime" / "SHDDesktopCore.exe"
    executable.parent.mkdir()
    launcher = Path(temp) / "SHDDesktop.exe"
    launcher.touch()
    original_executable = desktop_menu.sys.executable
    original_frozen = getattr(desktop_menu.sys, "frozen", None)
    original_public = os.environ.get("SHD_PUBLIC_EXE")
    try:
        desktop_menu.sys.executable = str(executable)
        desktop_menu.sys.frozen = True
        assert desktop_menu.note_menu_command() == f'"{executable}" --new-note'
        os.environ["SHD_PUBLIC_EXE"] = str(launcher)
        assert desktop_menu.note_menu_command() == f'"{launcher}" --new-note'
        assert desktop_menu.menu_command() == f'"{launcher}" --show-center'
        desktop_menu.set_enabled(True)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, desktop_menu.MENU_KEY) as key:
            assert winreg.QueryValueEx(key, "Icon")[0] == f'"{launcher}"'
        assert desktop_menu.is_enabled()
        desktop_menu.set_enabled(False)
        versioned = Path(temp) / "SHDDesktop-1.0.2.exe"
        versioned.touch()
        os.environ["SHD_PUBLIC_EXE"] = str(versioned)
        assert desktop_menu.note_menu_command() == f'"{versioned}" --new-note'
    finally:
        desktop_menu.sys.executable = original_executable
        if original_public is None:
            os.environ.pop("SHD_PUBLIC_EXE", None)
        else:
            os.environ["SHD_PUBLIC_EXE"] = original_public
        if original_frozen is None:
            del desktop_menu.sys.frozen
        else:
            desktop_menu.sys.frozen = original_frozen
        desktop_menu.set_enabled(False)

print("desktop context menu registration passed")
