"""Exercise the startup switch in an isolated current-user registry key."""

import uuid
import winreg
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import startup


startup.RUN_KEY = rf"Software\SHDDesktop-StartupTest-{uuid.uuid4().hex}"
try:
    assert not startup.is_enabled()
    startup.set_enabled(True)
    assert startup.is_enabled()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, startup.VALUE_NAME, 0, winreg.REG_SZ,
                          r'"C:\Older\SHDDesktop.exe"')
    assert startup.migrate_enabled()
    assert startup.is_enabled()
    assert not startup.migrate_enabled()
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, startup.VALUE_NAME, 0, winreg.REG_SZ,
                          r'"C:\Other\Unrelated.exe"')
    assert not startup.migrate_enabled()
    assert not startup.is_enabled()
    with TemporaryDirectory() as temp:
        launcher = Path(temp) / "SHDDesktop.exe"
        launcher.touch()
        previous_public = os.environ.get("SHD_PUBLIC_EXE")
        previous_frozen = getattr(startup.sys, "frozen", None)
        try:
            os.environ["SHD_PUBLIC_EXE"] = str(launcher)
            startup.sys.frozen = True
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, startup.VALUE_NAME, 0, winreg.REG_SZ,
                                  r'"C:\Older\SHDDesktop.exe"')
            assert startup.migrate_enabled()
            assert startup.is_enabled()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, startup.RUN_KEY) as key:
                assert winreg.QueryValueEx(key, startup.VALUE_NAME)[0] == f'"{launcher}"'
        finally:
            if previous_public is None:
                os.environ.pop("SHD_PUBLIC_EXE", None)
            else:
                os.environ["SHD_PUBLIC_EXE"] = previous_public
            if previous_frozen is None:
                del startup.sys.frozen
            else:
                startup.sys.frozen = previous_frozen
    startup.set_enabled(False)
    assert not startup.is_enabled()
finally:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, startup.RUN_KEY)
    except FileNotFoundError:
        pass
print("current-user startup switch passed")
