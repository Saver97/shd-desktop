"""Show the file's Windows Shell context menu inside a folder panel."""

from __future__ import annotations

import os
from pathlib import Path


RESTORE_COMMAND = 0x7FFF


def show_file_menu(paths: list[Path], owner_hwnd: int, x: int, y: int,
                   *, allow_restore: bool = False) -> bool | None:
    """Show the native menu; return True for restore, False for a Shell command.

    Shell folders accept a multi-file selection only when every child has the
    same parent. Callers pass just the clicked item for mixed-parent selections.
    A canceled menu returns None so the panel avoids an expensive refresh.
    """
    if os.name != "nt" or not paths:
        return None
    import win32api
    import win32con
    import win32gui
    from win32com.shell import shell, shellcon

    parent = os.path.normcase(os.path.abspath(str(paths[0].parent)))
    if any(os.path.normcase(os.path.abspath(str(path.parent))) != parent for path in paths):
        raise ValueError("Windows 右键菜单要求所选文件位于同一目录")

    desktop = shell.SHGetDesktopFolder()
    children = []
    folder_pidl = None
    for path in paths:
        pidl = shell.SHParseDisplayName(str(path), 0)[0]
        if not pidl:
            raise OSError(f"无法读取文件的 Windows Shell 标识：{path}")
        if folder_pidl is None:
            folder_pidl = pidl[:-1]
        children.append([pidl[-1]])
    folder = desktop.BindToObject(folder_pidl, None, shell.IID_IShellFolder)
    context = folder.GetUIObjectOf(owner_hwnd, children, shell.IID_IContextMenu)[1]
    popup = win32gui.CreatePopupMenu()
    first_command = 1
    try:
        flags = shellcon.CMF_NORMAL | shellcon.CMF_CANRENAME
        if win32api.GetKeyState(win32con.VK_SHIFT) < 0:
            flags |= shellcon.CMF_EXTENDEDVERBS
        context.QueryContextMenu(popup, 0, first_command, RESTORE_COMMAND - 1, flags)
        if allow_restore:
            win32gui.AppendMenu(popup, win32con.MF_SEPARATOR, 0, "")
            win32gui.AppendMenu(popup, win32con.MF_STRING, RESTORE_COMMAND,
                                "移出分框，恢复桌面图标")
        command = win32gui.TrackPopupMenu(
            popup, win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY | win32con.TPM_RIGHTBUTTON,
            x, y, 0, owner_hwnd, None)
        if command == RESTORE_COMMAND:
            return True
        if first_command <= command < RESTORE_COMMAND:
            # PyIContextMenu takes the eight CMINVOKECOMMANDINFO fields.
            context.InvokeCommand((0, owner_hwnd, command - first_command,
                                   None, None, win32con.SW_SHOWNORMAL, 0, 0))
            return False
        return None
    finally:
        win32gui.DestroyMenu(popup)
