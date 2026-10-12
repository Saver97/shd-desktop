"""Repeatable local benchmark for bulk grouping and panel redraw."""

import time
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPoint, QSize
from PySide6.QtWidgets import QApplication

from app import ConfigStore, FolderPanel, icon_for_item
from desktop_groups import DesktopGroups, path_key


class Positions:
    def capture_many(self, paths):
        return {path_key(path): [100, 200] for path in paths}

    def refresh(self):
        pass

    def restore(self, positions):
        return []


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    suffix = sys.argv[1] if len(sys.argv) > 1 else ".txt"
    paths = [desktop / f"sample-{index:03}{suffix}" for index in range(160)]
    for path in paths:
        if suffix == ".url":
            path.write_text("[InternetShortcut]\nURL=https://example.com\n"
                            f"IconFile={Path(__file__).parent / 'assets' / 'tray.png'}\n")
        else:
            path.write_text("sample")
    store = ConfigStore(root / "config")
    panel_config = {"id": "benchmark", "kind": "virtual", "title": "测试", "items": []}
    store.data["panels"] = [panel_config]
    saves = 0
    original_save = store.save

    def counted_save():
        global saves
        saves += 1
        original_save()

    store.save = counted_save
    groups = DesktopGroups(store, [desktop], Positions())
    try:
        start = time.perf_counter()
        added, errors = groups.add(panel_config, paths)
        grouping_ms = (time.perf_counter() - start) * 1000
        assert len(added) == len(paths) and not errors
        start = time.perf_counter()
        panel = FolderPanel(panel_config, store, lambda _: None, groups)
        create_ms = (time.perf_counter() - start) * 1000
        if "--no-cache" in sys.argv:
            panel._cached_icon = lambda path, key: icon_for_item(path, panel.icon_provider)
        start = time.perf_counter()
        panel.refresh()
        redraw_ms = (time.perf_counter() - start) * 1000
        assert panel.list.count() == len(paths)
        print(f"suffix={suffix} bulk_group_ms={grouping_ms:.1f} saves={saves} "
              f"panel_create_ms={create_ms:.1f} redraw_ms={redraw_ms:.1f}")
        if "--motion" in sys.argv:
            panel.show()
            app.processEvents()
            start = time.perf_counter()
            panel.refresh()
            app.processEvents()
            visible_redraw_ms = (time.perf_counter() - start) * 1000
            start = time.perf_counter()
            for step in range(100):
                panel.drag_to(QPoint(60 + step, 80 + step))
                app.processEvents()
            panel.finish_move()
            drag_ms = (time.perf_counter() - start) * 1000
            start = time.perf_counter()
            for step in range(100):
                panel.resize_to(QSize(350 + step * 3, 420))
                app.processEvents()
            panel.finish_resize()
            app.processEvents()
            resize_ms = (time.perf_counter() - start) * 1000
            print(f"visible_redraw_ms={visible_redraw_ms:.1f} "
                  f"drag_100_steps_ms={drag_ms:.1f} resize_100_steps_ms={resize_ms:.1f}")
        panel.deleteLater()
    finally:
        groups.restore_for_exit()
