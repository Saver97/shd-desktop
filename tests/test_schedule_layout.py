"""Reading space and event creation regression using an isolated database."""

import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar
from PySide6.QtTest import QTest

from app import ConfigStore, Controller
from shd_desktop.ui.theme import apply_hud, HUD_DEFAULTS


app = QApplication([])
with TemporaryDirectory() as temp:
    controller = Controller(app, ConfigStore(Path(temp)), enable_hotkeys=False)
    center = controller.center
    pane = center.schedule
    now = int(time.time() * 1000)
    for index in range(30):
        controller.events.add(f"任务 {index + 1:02d}  ·  检查今日计划与桌面工作安排", now + index * 3600000)
    pane.refresh()
    center.show()
    app.processEvents()
    view = pane.list
    metrics = {
        "window_height": center.height(),
        "list_viewport_height": view.viewport().height(),
        "row_height": view.visualItemRect(view.item(0)).height(),
        "fully_visible_rows": sum(view.viewport().rect().contains(view.visualItemRect(view.item(i)))
                                  for i in range(view.count())),
    }
    assert metrics["list_viewport_height"] >= center.height() * .70, metrics
    assert metrics["fully_visible_rows"] >= 12, metrics
    assert not pane.editor.isVisible()
    assert not any(button.isEnabled() for button in pane.action_buttons)
    assert len(center.findChildren(QToolBar)) == 1
    center.grab().save(str(Path(__file__).parent / "preview-0.5.12-schedule.png"))

    pane.add_button.click()
    app.processEvents()
    assert pane.editor.isVisible()
    with patch.object(QMessageBox, "warning") as warning:
        pane.add_event()
        assert warning.called and pane.editor.isVisible()
        assert len(controller.events.list()) == 30
    pane.title.setText("新增任务测试")
    pane.remind.setValue(17)
    start = pane.start.dateTime().toMSecsSinceEpoch()
    pane.editor.grab().save(str(Path(__file__).parent / "preview-0.5.12-new-event.png"))
    pane.add_event()
    assert not pane.editor.isVisible()
    event = next(e for e in controller.events.list() if e["title"] == "新增任务测试")
    assert event["start_ms"] == start and event["remind_minutes"] == 17
    view.setCurrentItem(next(view.item(i) for i in range(view.count())
                             if view.item(i).data(256) == event["id"]))
    assert all(button.isEnabled() for button in pane.action_buttons)
    pane.toggle_done()
    assert controller.events.get(event["id"])["done"] == 1
    assert pane.selected_id() == event["id"]
    pane.toggle_done()
    pane.snooze()
    assert controller.events.get(event["id"])["snooze_until"] > now
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
        pane.delete()
    assert controller.events.get(event["id"]) is None
    assert len(controller.events.list()) == 30
    assert not any(button.isEnabled() for button in pane.action_buttons)

    pane.open_editor()
    pane.title.setText("未保存草稿")
    pane.editor.reject()
    assert len(controller.events.list()) == 30
    pane.open_editor()
    assert pane.title.text() == "未保存草稿"
    pane.editor.reject()
    for index in (1, 2, 3, 0):
        center.centralWidget().setCurrentIndex(index)
        app.processEvents()
    center.resize(720, 580)
    apply_hud(app, {**HUD_DEFAULTS, "font_size": 16})
    QTest.qWait(40)
    assert view.viewport().height() >= center.height() * .60, (center.height(), view.viewport().height())
    assert view.visualItemRect(view.item(0)).height() >= 32
    assert center.scene_combo.isVisible()
    assert pane.add_button.isVisible()
    center.grab().save(str(Path(__file__).parent / "preview-0.5.12-schedule-large-font.png"))
    controller.center.music.bridge.close()
    controller.events.close()
    center.hide()
print(json.dumps(metrics))
print("schedule reading space, editor validation, event actions and large font passed")
