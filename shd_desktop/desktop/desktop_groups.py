"""Virtual desktop groups: keep files in place while hiding their shell icons."""

from __future__ import annotations

import os
from pathlib import Path

import win32file
from win32com.shell import shell, shellcon


HIDE_BITS = win32file.FILE_ATTRIBUTE_HIDDEN | win32file.FILE_ATTRIBUTE_SYSTEM


def path_key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def file_attributes(path: Path) -> int:
    return win32file.GetFileAttributes(str(path))


def set_visibility(path: Path, original_bits: int | None) -> bool:
    """None hides; otherwise restore only the two bits this app changes."""
    current = file_attributes(path)
    bits = HIDE_BITS if original_bits is None else original_bits
    updated = (current & ~HIDE_BITS) | bits
    if updated != current:
        win32file.SetFileAttributes(str(path), updated)
        shell.SHChangeNotify(shellcon.SHCNE_ATTRIBUTES, shellcon.SHCNF_PATHW, str(path), None)
        return True
    return False


class DesktopGroups:
    def __init__(self, store, roots: list[Path], positions=None):
        if positions is None:
            from shd_desktop.desktop.desktop_positions import DesktopPositions
            positions = DesktopPositions()
        self.store = store
        self.positions = positions
        self.roots = [Path(root) for root in roots]
        self.root_keys = {path_key(root) for root in self.roots}

    def _refresh_desktop(self) -> None:
        refresh = getattr(self.positions, "refresh", None)
        if refresh:
            try:
                refresh()
            except Exception as exc:
                raise OSError("Explorer 桌面视图暂时不可用") from exc

    def is_desktop_item(self, path: Path) -> bool:
        return path_key(path.parent) in self.root_keys

    def _panels(self):
        return (panel for panel in self.store.data.get("panels", [])
                if isinstance(panel, dict) and panel.get("kind") == "virtual")

    def records(self, panel: dict) -> list[dict]:
        items = panel.setdefault("items", [])
        return items if isinstance(items, list) else []

    def grouped_keys(self) -> set[str]:
        return {path_key(record["path"]) for panel in self._panels()
                if not panel.get("hidden")
                for record in self.records(panel) if isinstance(record, dict) and record.get("path")}

    def owner_id(self, path: Path) -> str | None:
        panel, _ = self._owner(path)
        return panel.get("id") if panel else None

    def sync_visibility(self, recapture: bool = True) -> list[str]:
        """Keep desktop icons visible when their virtual panel is hidden."""
        errors, restored, changed = [], [], False
        batches = []
        for panel in self._panels():
            active = not panel.get("hidden")
            records = [(r, Path(r["path"])) for r in self.records(panel)
                       if isinstance(r, dict) and r.get("path") and Path(r["path"]).exists()]
            batches.append((active, records))
        position_changed = False
        if recapture:
            active_records = [(record, path) for active, records in batches if active
                              for record, path in records]
            if active_records:
                try:
                    capture_many = getattr(self.positions, "capture_many", None)
                    snapshot = (capture_many([path for _, path in active_records]) if capture_many else
                                {path_key(path): self.positions.get(path) for _, path in active_records})
                    for record, path in active_records:
                        point = snapshot.get(path_key(path))
                        if point and record.get("position") != point:
                            record["position"] = point
                            position_changed = True
                except Exception as exc:
                    if "自动排列" not in str(exc):
                        errors.append(f"无法读取桌面图标位置：{exc}")
        for active, records in batches:
            for record, path in records:
                try:
                    updated = set_visibility(path, None if active else int(record.get("original_bits", 0)))
                    changed = changed or updated
                    if not active and updated:
                        restored.append((path, record.get("position")))
                except OSError as exc:
                    errors.append(f"{path.name}：{exc}")
        if changed:
            try:
                self._refresh_desktop()
                if restored:
                    errors.extend(f"{Path(p).name}：位置未恢复" for p in self.positions.restore(restored))
            except OSError as exc:
                errors.append(str(exc))
        if position_changed:
            self.store.save()
        return errors

    def _owner(self, path: Path):
        key = path_key(path)
        for panel in self._panels():
            for record in self.records(panel):
                if isinstance(record, dict) and path_key(record.get("path", "")) == key:
                    return panel, record
        return None, None

    def add(self, target: dict, paths: list[Path],
            snapshot: dict[str, list[int]] | None = None,
            allow_unpositioned: bool = False) -> tuple[list[str], list[str]]:
        added, errors = [], []
        capture_many = getattr(self.positions, "capture_many", None)
        try:
            if snapshot is None:
                snapshot = capture_many(paths) if capture_many else None
        except Exception as exc:
            return [], [f"无法读取桌面图标位置：{exc}"]
        owners = {path_key(record["path"]): (panel, record)
                  for panel in self._panels() for record in self.records(panel)
                  if isinstance(record, dict) and record.get("path")}
        pending = []
        seen = set()
        for path in paths:
            key = path_key(path)
            if key in seen:
                continue
            seen.add(key)
            if not self.is_desktop_item(path) or not path.exists():
                errors.append(f"{path.name}：只支持桌面上的文件或快捷方式")
                continue
            owner, record = owners.get(key, (None, None))
            if owner is target:
                continue
            try:
                if record is None:
                    original = file_attributes(path) & HIDE_BITS
                    position = snapshot.get(key) if snapshot is not None else self.positions.get(path)
                    if position is None and not allow_unpositioned:
                        raise ValueError("无法读取桌面图标位置，未进行分组")
                    stat = path.stat()
                    record = {"path": str(path), "original_bits": original,
                              "file_id": [stat.st_dev, stat.st_ino], "position": position}
                pending.append((path, owner, record))
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}：{exc}")
        if not pending:
            return added, errors
        for _, owner, record in pending:
            if owner is not None:
                self.records(owner).remove(record)
            self.records(target).append(record)
        try:
            # Persist every record before hiding anything. A crash mid-batch
            # can then be recovered by restore_for_exit on the next launch.
            self.store.save()
        except OSError as exc:
            for _, owner, record in reversed(pending):
                self.records(target).remove(record)
                if owner is not None:
                    self.records(owner).append(record)
            return [], errors + [f"无法保存分组，未修改图标：{exc}"]
        failed = []
        visibility_changed = False
        for path, owner, record in pending:
            try:
                visibility_changed = set_visibility(path, None) or visibility_changed
                added.append(path.name)
            except OSError as exc:
                try:
                    already_hidden = file_attributes(path) & HIDE_BITS == HIDE_BITS
                except OSError:
                    already_hidden = False
                if already_hidden:
                    added.append(path.name)
                    visibility_changed = True
                else:
                    failed.append((path, owner, record))
                    errors.append(f"{path.name}：{exc}")
        if failed:
            for _, owner, record in failed:
                self.records(target).remove(record)
                if owner is not None:
                    self.records(owner).append(record)
            try:
                self.store.save()
            except OSError as exc:
                errors.append(f"部分失败记录暂未保存：{exc}")
        if visibility_changed:
            try:
                self._refresh_desktop()
            except OSError as exc:
                errors.append(str(exc))
        return added, errors

    def remove(self, panel: dict, path: Path) -> bool:
        record = next((item for item in self.records(panel)
                       if path_key(item.get("path", "")) == path_key(path)), None)
        if record is None:
            return False
        if path.exists():
            updated = set_visibility(path, int(record.get("original_bits", 0)))
            if updated:
                self._refresh_desktop()
                if self.positions.restore([(path, record.get("position"))]):
                    raise OSError("桌面图标位置尚未恢复，请稍后重试")
        self.records(panel).remove(record)
        self.store.save()
        return True

    def restore_panel(self, panel: dict) -> list[str]:
        errors = []
        restored = []
        for record in list(self.records(panel)):
            path = Path(record["path"])
            try:
                if path.exists():
                    if set_visibility(path, int(record.get("original_bits", 0))):
                        restored.append((path, record.get("position")))
            except OSError as exc:
                errors.append(f"{path.name}：{exc}")
        if restored:
            try:
                self._refresh_desktop()
            except OSError as exc:
                errors.append(str(exc))
        position_errors = set(self.positions.restore(restored))
        for record in list(self.records(panel)):
            path = Path(record["path"])
            if str(path) not in position_errors and not any(e.startswith(f"{path.name}：") for e in errors):
                self.records(panel).remove(record)
            elif str(path) in position_errors:
                errors.append(f"{path.name}：桌面位置尚未恢复")
        self.store.save()
        return errors

    def restore_for_exit(self, force_positions: bool = False) -> list[str]:
        restored, errors = [], []
        for panel in self._panels():
            for record in self.records(panel):
                path = Path(record["path"])
                if path.exists():
                    try:
                        changed = set_visibility(path, int(record.get("original_bits", 0)))
                        if changed or force_positions:
                            restored.append((path, record.get("position")))
                    except OSError as exc:
                        errors.append(f"{path.name}：{exc}")
        if restored:
            try:
                self._refresh_desktop()
                errors.extend(f"{Path(path).name}：位置未恢复" for path in self.positions.restore(restored))
            except OSError as exc:
                errors.append(str(exc))
        return errors

    def reapply_on_start(self) -> list[str]:
        return self.sync_visibility()
