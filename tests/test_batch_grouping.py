"""Batch grouping saves recovery records before changing file attributes."""

from pathlib import Path
from tempfile import TemporaryDirectory

import shd_desktop.desktop.desktop_groups as desktop_groups
from app import ConfigStore
from shd_desktop.desktop.desktop_groups import DesktopGroups, HIDE_BITS, file_attributes, path_key


class Positions:
    def __init__(self):
        self.refreshes = 0

    def capture_many(self, paths):
        return {path_key(path): [100, 200] for path in paths}

    def refresh(self):
        self.refreshes += 1

    def restore(self, points):
        return []


with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    paths = [desktop / f"item-{index}.txt" for index in range(3)]
    for path in paths:
        path.write_text(path.name)
    store = ConfigStore(root / "config")
    panel = {"id": "batch", "kind": "virtual", "items": []}
    store.data["panels"] = [panel]
    positions = Positions()
    groups = DesktopGroups(store, [desktop], positions)
    original_save = store.save
    store.save = lambda: (_ for _ in ()).throw(OSError("disk unavailable"))
    added, errors = groups.add(panel, paths)
    assert not added and errors and not panel["items"]
    assert all(file_attributes(path) & HIDE_BITS == 0 for path in paths)
    store.save = original_save

    original_visibility = desktop_groups.set_visibility
    def fail_one(path, bits):
        if path == paths[1] and bits is None:
            raise OSError("permission denied")
        return original_visibility(path, bits)
    desktop_groups.set_visibility = fail_one
    try:
        added, errors = groups.add(panel, paths)
    finally:
        desktop_groups.set_visibility = original_visibility
    assert len(added) == 2 and len(errors) == 1
    assert {record["path"] for record in panel["items"]} == {str(paths[0]), str(paths[2])}
    assert file_attributes(paths[1]) & HIDE_BITS == 0
    assert len(ConfigStore(root / "config").data["panels"][0]["items"]) == 2
    assert positions.refreshes == 1
    groups.sync_visibility(recapture=False)
    assert positions.refreshes == 1
    groups.restore_for_exit()
    assert all(file_attributes(path) & HIDE_BITS == 0 for path in paths)

print("batch grouping recovery and no-op refresh passed")
