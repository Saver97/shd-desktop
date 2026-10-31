"""Per-user cascading Windows desktop context menu."""
import sys
import winreg
from shd_desktop.integration.startup import public_executable, startup_command
from shd_desktop.resources import ASSETS

MENU_KEY = r"Software\Classes\DesktopBackground\Shell\SHDDesktop"
ACTIONS = (("01Center", "打开终端", "center"), ("02Note", "新建便签", "note"),
           ("03Organize", "一键整理桌面", "organize"))

def quick_command(action):
    flag = {"center":"show-center", "note":"new-note", "organize":"organize-desktop"}[action]
    return f"{startup_command()} --{flag}"

def menu_command():
    return quick_command("center")

def note_menu_key():
    return MENU_KEY + r"\shell\02Note"

def note_menu_command():
    return quick_command("note")

def _remove(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            children = []
            for i in range(winreg.QueryInfoKey(key)[0]):
                children.append(winreg.EnumKey(key, i))
        for child in children:
            _remove(path + "\\" + child)
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
    except FileNotFoundError:
        pass

def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY) as key:
            if winreg.QueryValueEx(key, "SubCommands")[0] != "":
                return False
        for name, _, action in ACTIONS:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_KEY + "\\shell\\" + name + "\\command") as key:
                if winreg.QueryValueEx(key, "")[0].casefold() != quick_command(action).casefold():
                    return False
        return True
    except FileNotFoundError:
        return False

def set_enabled(enabled):
    # Remove only the application's known old entries, never other shell menus.
    _remove(MENU_KEY + "NewNote")
    _remove(MENU_KEY)
    if not enabled:
        return
    icon = f'"{public_executable()}"' if getattr(sys, "frozen", False) else str(ASSETS / "app.ico")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, MENU_KEY) as key:
        for name, value in (("MUIVerb","SHD Desktop"),("SubCommands",""),("Icon",icon),("Position","Top")):
            winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    for name, title, action in ACTIONS:
        path = MENU_KEY + "\\shell\\" + name
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.SetValueEx(key,"MUIVerb",0,winreg.REG_SZ,title)
            winreg.SetValueEx(key,"Icon",0,winreg.REG_SZ,icon)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path + "\\command") as key:
            winreg.SetValueEx(key,"",0,winreg.REG_SZ,quick_command(action))
