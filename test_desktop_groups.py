"""Virtual panels retain desktop files and restore their attributes on exit."""

from pathlib import Path
from tempfile import TemporaryDirectory

from app import ConfigStore
from desktop_groups import DesktopGroups, HIDE_BITS, file_attributes


class Positions:
    def __init__(self):
        self.restored = []
        self.point = [120, 240]

    def get(self, path):
        return list(self.point)

    def restore(self, positions):
        self.restored.extend(positions)
        return []


with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    icon = desktop / "Game.lnk"
    icon.write_text("shortcut")
    original = file_attributes(icon) & HIDE_BITS
    store = ConfigStore(root / "config")
    first = {"id": "a", "kind": "virtual", "title": "游戏", "items": []}
    second = {"id": "b", "kind": "virtual", "title": "工具", "items": []}
    store.data["panels"] = [first, second]
    positions = Positions()
    groups = DesktopGroups(store, [desktop], positions)

    added, errors = groups.add(first, [icon])
    assert added == [icon.name] and not errors
    assert icon.exists() and file_attributes(icon) & HIDE_BITS == HIDE_BITS
    assert first["items"][0]["position"] == [120, 240]

    added, errors = groups.add(second, [icon])
    assert added == [icon.name] and not errors
    assert not first["items"] and len(second["items"]) == 1
    assert groups.grouped_keys()

    groups.restore_for_exit()
    assert icon.exists() and file_attributes(icon) & HIDE_BITS == original
    assert positions.restored[-1] == (icon, [120, 240])
    positions.point = [480, 560]
    groups.reapply_on_start()
    assert file_attributes(icon) & HIDE_BITS == HIDE_BITS
    assert second["items"][0]["position"] == [480, 560]

    assert groups.restore_panel(second) == []
    assert second["items"] == [] and icon.exists()
    assert file_attributes(icon) & HIDE_BITS == original

print("virtual desktop groups passed")
