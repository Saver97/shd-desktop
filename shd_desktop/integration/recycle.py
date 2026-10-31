"""Recycle panel items, restoring virtual-group attributes on cancellation."""
from pathlib import Path
from win32com.shell import shell, shellcon
from shd_desktop.desktop.desktop_groups import set_visibility


def recycle_items(paths: list[Path], owner_hwnd: int, groups=None, panel=None):
    errors = []
    for path in paths:
        record = next((r for r in groups.records(panel) if r.get("path") == str(path)), None) if groups else None
        try:
            if record and path.exists():
                set_visibility(path, int(record.get("original_bits", 0)))
            result, aborted = shell.SHFileOperation((
                owner_hwnd, shellcon.FO_DELETE, str(path) + "\0\0", None,
                shellcon.FOF_ALLOWUNDO | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_WANTNUKEWARNING, None, None))
            if result:
                errors.append(f"{path.name}：删除失败（{result}）")
            if aborted:
                break
        except Exception as exc:
            errors.append(f"{path.name}：{exc}")
        finally:
            if record:
                try:
                    if path.exists():
                        set_visibility(path, None)
                    else:
                        groups.remove(panel, path)
                except Exception as exc:
                    errors.append(f"{path.name}：分框状态更新失败：{exc}")
    return errors
