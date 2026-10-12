"""Recovery checks use temporary desktop files and synthetic monitor layouts."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from app import ConfigStore, Controller
from screen_recovery import visible_geometry


primary = QRect(0, 0, 1920, 1080)
secondary = QRect(1920, 0, 1920, 1080)
saved = QRect(2200, 120, 350, 300)
assert visible_geometry(saved, [primary, secondary]) == saved
assert visible_geometry(saved, [primary]) == QRect(1570, 120, 350, 300)
assert visible_geometry(QRect(-9000, -5000, 350, 300), [primary]).topLeft() == primary.topLeft()
assert visible_geometry(saved, [primary, secondary]) == saved

app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    store = ConfigStore(root / "config")
    store.data["panels"] = [{"id": "offscreen", "kind": "folder", "path": str(desktop),
                             "title": "临时分框", "x": 2200, "y": 120, "w": 350,
                             "h": 300, "expanded_h": 300}]
    controller = Controller(app, store, [desktop])
    panel = controller.panels["offscreen"]
    controller._screen_change_timer.stop()
    controller._prepare_screen_change()
    panel.resize(320, 260)
    assert (panel.config["w"], panel.config["h"]) == (350, 300)
    controller._place_windows([primary])
    assert panel.geometry() == QRect(1570, 120, 350, 300)
    assert (panel.config["x"], panel.config["y"]) == (2200, 120)
    controller._place_windows([primary, secondary])
    assert panel.geometry() == saved
    assert (panel.config["x"], panel.config["y"]) == (2200, 120)

    class Explorer:
        def __init__(self):
            self.token = 1
            self.refreshes = 0

        def view_token(self):
            return self.token

        def refresh(self):
            self.refreshes += 1

    explorer = Explorer()
    controller.groups.positions = explorer
    controller._shell_token = 1
    syncs = []
    controller.groups.sync_visibility = lambda recapture=True: syncs.append(recapture) or []
    controller._check_explorer()
    assert not syncs
    explorer.token = None
    controller._check_explorer()
    assert not syncs
    explorer.token = 2
    controller._check_explorer()
    assert syncs == [False] and explorer.refreshes == 1

    marker = controller._session_file
    assert marker.exists()
    controller.groups.restore_for_exit = lambda: ["Explorer unavailable"]
    controller._restore_on_exit()
    controller._clear_session()
    assert marker.exists(), "failed recovery must keep the retry marker"
    controller.groups.restore_for_exit = lambda: []
    controller._restore_on_exit()
    controller._clear_session()
    assert not marker.exists()
    controller._shell_timer.stop()
    controller.reminder_timer.stop()
    controller.events.close()
    controller.center.music.bridge.close()
    for window in (*controller.panels.values(), *controller.widgets.values(),
                   controller.isac_launcher, controller.chat, controller.center,
                   controller.settings):
        window.close()

    store.data["panels"][0]["title"] = "保留的布局"
    store.save()
    store.file.write_text("{broken", encoding="utf-8")
    recovered = ConfigStore(root / "config")
    assert recovered.data["panels"][0]["title"] == "保留的布局"
    assert recovered.first_run is False
    recovered.backup.write_text("{broken", encoding="utf-8")
    try:
        ConfigStore(root / "config")
    except OSError:
        pass
    else:
        raise AssertionError("invalid layout must not be silently overwritten")
    assert store.file.read_text(encoding="utf-8") == "{broken"

print("screen, Explorer, session and layout recovery passed")
