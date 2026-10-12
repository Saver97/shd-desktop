"""Read and restore Windows desktop icon coordinates through Explorer's folder view."""

from __future__ import annotations

import time
from pathlib import Path

import pythoncom
import pywintypes
import win32com.client
import win32gui
from win32com.shell import shell, shellcon


TOP_LEVEL_BROWSER = pywintypes.IID("{4C96BE40-915C-11CF-99D3-00AA004AE837}")


def _view():
    windows = win32com.client.Dispatch("Shell.Application").Windows()
    dispatch = windows.FindWindowSW(0, None, 8, 0, 1)
    provider = dispatch._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
    browser = provider.QueryService(TOP_LEVEL_BROWSER, shell.IID_IShellBrowser)
    view = browser.QueryActiveShellView().QueryInterface(shell.IID_IFolderView)
    folder = view.GetFolder(shell.IID_IShellFolder)
    return view, folder


def _visible_items(view, folder):
    from desktop_groups import path_key

    result = {}
    for index in range(view.ItemCount(shellcon.SVGIO_ALLVIEW)):
        pidl = view.Item(index)
        path = folder.GetDisplayNameOf((pidl,), shellcon.SHGDN_FORPARSING)
        if Path(path).is_absolute():
            result[path_key(path)] = pidl
    return result


class DesktopPositions:
    def view_token(self) -> int | None:
        """The desktop view handle changes when Explorer rebuilds its window."""
        try:
            found = []

            def inspect(handle, _extra):
                if win32gui.GetClassName(handle) in ("Progman", "WorkerW"):
                    view = win32gui.FindWindowEx(handle, 0, "SHELLDLL_DefView", None)
                    if view:
                        found.append(view)

            win32gui.EnumWindows(inspect, None)
            return found[0] if found else None
        except (OSError, pywintypes.error):
            return None

    def refresh(self) -> None:
        view, _ = _view()
        view.QueryInterface(shell.IID_IShellView).Refresh()

    def get(self, path: Path) -> list[int] | None:
        from desktop_groups import path_key

        return self.capture_many([path]).get(path_key(path))

    def capture_many(self, paths: list[Path]) -> dict[str, list[int]]:
        from desktop_groups import path_key

        view, folder = _view()
        if view.GetAutoArrange():
            raise ValueError("Windows 桌面开启了自动排列，无法保证图标退出后回到原位")
        visible = _visible_items(view, folder)
        return {key: list(view.GetItemPosition(visible[key])) for path in paths
                if (key := path_key(path)) in visible}

    def restore(self, positions: list[tuple[Path, list[int]]]) -> list[str]:
        from desktop_groups import path_key

        pending = {path_key(path): (path, point) for path, point in positions if point}
        for attempt in range(8):
            if not pending:
                break
            try:
                view, folder = _view()
                visible = _visible_items(view, folder)
                for key, (path, point) in list(pending.items()):
                    pidl = visible.get(key)
                    if pidl is None:
                        continue
                    view.SelectAndPositionItem(pidl, tuple(point), shellcon.SVSI_POSITIONITEM)
                    del pending[key]
            except (OSError, pythoncom.com_error):
                pass
            if pending and attempt < 7:
                time.sleep(0.15)
        return [str(path) for path, _ in pending.values()]
