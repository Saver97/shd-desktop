"""Gestures coalesce writes; previews roll back; search keeps original paths."""

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import shd_desktop.ui.quick_find as quick_find
from app import ConfigStore, Controller
from shd_desktop.ui.theme import HUD_DEFAULTS, current_hud, hud_background


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    files = root / "files"
    files.mkdir()
    (files / "Game.lnk").write_text("shortcut")
    (files / "文档.txt").write_text("document")
    store = ConfigStore(root / "config")
    store.data["panels"] = [{"id": "one", "path": str(files), "title": "工作",
                              "collapsed": True, "hidden": True, "w": 480,
                              "h": 55, "expanded_h": 330}]
    controller = Controller(app, store, [files], enable_hotkeys=False)
    controller.chat.show()
    app.processEvents()
    store.save()
    saves = []
    original_save = store.save

    def counted_save():
        saves.append(True)
        original_save()

    store.save = counted_save
    started = time.perf_counter()
    for offset in range(100):
        controller.chat.move(550 + offset, 150 + offset)
        controller.chat.resize(500 + offset, 500)
        controller.widgets["weather"].resize(320 + offset, 180)
    app.processEvents()
    assert not saves, saves
    QTest.qWait(350)
    assert len(saves) == 1, saves
    print(f"100 chat moves/resizes and card resizes: {len(saves)} disk write; {time.perf_counter()-started:.3f}s incl. debounce")
    assert json.loads(store.file.read_text(encoding='utf-8'))['chat_window']['x'] == 649
    controller.chat.move(720, 250)
    assert store.geometry_timer().isActive()
    controller.chat.hide()
    assert not store.geometry_timer().isActive()
    assert ConfigStore(store.file.parent).data["chat_window"]["x"] == 720

    controller.open_appearance()
    dialog = controller.appearance_window
    dialog.sliders["opacity"].setValue(90)
    dialog.sliders["font_size"].setValue(16)
    dialog.sliders["icon_size"].setValue(64)
    QTest.qWait(150)
    assert current_hud() == {"opacity": 90, "font_size": 16, "icon_size": 64}
    assert hud_background().alpha() == 229
    assert controller.panels['one'].list.iconSize().width() == 64
    assert controller.panels['one'].header.font().pixelSize() == 24
    assert 'hud' not in store.data, 'preview must not be saved'
    dialog.reject()
    assert current_hud() == HUD_DEFAULTS
    assert controller.panels['one'].list.iconSize().width() == 40
    controller.open_appearance()
    dialog = controller.appearance_window
    dialog.sliders["opacity"].setValue(88)
    dialog.enabled.setChecked(False)
    dialog.save()
    assert ConfigStore(store.file.parent).data["hud"]["opacity"] == 88
    controller.open_appearance()
    dialog = controller.appearance_window
    dialog.reset_defaults()
    dialog.enabled.setChecked(False)
    dialog.save()
    assert current_hud() == HUD_DEFAULTS

    controller.open_search()
    search = controller.search_window
    search.query.setText("GAME 工作")
    search.filter()
    assert search.results.count() == 1
    assert search.selected()["name"] == "Game"
    assert search.selected()["path"] == str(files / "Game.lnk")
    search.locate_selected()
    panel = controller.panels['one']
    assert panel.isVisible() and not panel.config['hidden'] and not panel.config['collapsed']
    assert panel.list.currentItem().data(Qt.UserRole) == str(files / "Game.lnk")
    assert panel.list.currentItem().isSelected()
    panel.list.item(0).setSelected(True)
    panel.list.item(1).setSelected(True)
    panel.refresh()
    assert len(panel.list.selectedItems()) == 2, "refresh must preserve multiple selection"
    opened = []
    original_open = quick_find.os.startfile
    quick_find.os.startfile = lambda path: opened.append(path)
    try:
        search.show_search()
        # Return before the filter timer fires must open the newly typed match.
        search.query.setText("文档")
        search.open_selected()
        assert opened == [str(files / "文档.txt")]
        assert (files / "文档.txt").exists() and (files / "Game.lnk").exists()
        search.show_search()
        search.query.setText("文档")
        search.filter()
        (files / "文档.txt").unlink()
        search.open_selected()
        assert len(opened) == 1 and '移动或删除' in search.status.text()
    finally:
        quick_find.os.startfile = original_open
    controller.open_appearance()
    controller.chat.show()
    search.show_search()
    QTest.qWait(100)
    controller.appearance_window.grab().save(str(Path(__file__).parent/'preview-0.5.11-appearance.png'))
    search.grab().save(str(Path(__file__).parent/'preview-0.5.11-search.png'))
    panel.grab().save(str(Path(__file__).parent/'preview-0.5.11-panel.png'))
    controller.appearance_window.reject()
    controller.search_hotkey.close()
    controller._screen_change_timer.stop()
    controller._shell_timer.stop()
    controller.reminder_timer.stop()
    controller.center.music.bridge.close()
    controller.events.close()
    for window in app.topLevelWidgets():
        window.close()
    store.save()
print("HUD preview/cancel/default/persistence, cross-panel lookup and original-path opening passed")
