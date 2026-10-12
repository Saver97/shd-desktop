"""Reminder deletion through ISAC and the schedule's multi-select controls."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from center import SchedulePane
from llm import RESPONSES_TOOLS, TOOLS, ToolDispatcher
from services import ScheduleStore
from theme import HUD_DEFAULTS, apply_hud


app = QApplication([])
with TemporaryDirectory() as temp:
    events = ScheduleStore(Path(temp) / "state.db")
    ids = [events.add(f"提醒 {index}", 2_000_000_000_000 + index * 60_000)
           for index in range(4)]
    store = type("Store", (), {"data": {}})()
    dispatcher = ToolDispatcher(events, store, {})
    assert "delete_event" in [tool["function"]["name"] for tool in TOOLS]
    assert "delete_event" in [tool["name"] for tool in RESPONSES_TOOLS]
    assert dispatcher.execute("delete_event", {"id": "missing"}).startswith("未找到")
    assert len(events.list()) == 4
    result = json.loads(dispatcher.execute("delete_event", {"id": ids[0]}))
    assert result["id"] == ids[0] and result["result"] == "已删除"
    assert events.get(ids[0]) is None

    pane = SchedulePane(events)
    pane.show()
    app.processEvents()
    pane.batch_button.click()
    assert pane.batch_button.isChecked()
    assert not pane.action_buttons[0].isVisible()
    assert pane.batch_buttons[0].isVisible()
    pane.resize(720, 580)
    apply_hud(app, {**HUD_DEFAULTS, "font_size": 16})
    app.processEvents()
    for button in pane.batch_buttons:
        assert button.geometry().right() <= pane.width(), (button.text(), button.geometry(), pane.width())
    pane.list.item(0).setSelected(True)
    pane.list.item(2).setSelected(True)
    assert {item.data(Qt.UserRole) for item in pane.list.selectedItems()} == {ids[1], ids[3]}
    pane.refresh()
    assert {item.data(Qt.UserRole) for item in pane.list.selectedItems()} == {ids[1], ids[3]}
    assert pane.batch_buttons[2].text() == "删除选中 (2)"
    with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
        pane.delete_selected()
    assert len(events.list()) == 3
    with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question:
        pane.batch_buttons[2].click()
    assert "2 项" in question.call_args.args[2]
    assert [event["id"] for event in events.list()] == [ids[2]]
    assert not pane.batch_buttons[2].isEnabled()
    pane.batch_buttons[0].click()
    assert len(pane.list.selectedItems()) == 1
    pane.batch_buttons[1].click()
    assert not pane.list.selectedItems()
    pane.batch_button.click()
    assert not pane.batch_button.isChecked()
    assert pane.action_buttons[0].isVisible()
    pane.close()
    events.close()
print("schedule multi-delete and LLM delete tool passed")
