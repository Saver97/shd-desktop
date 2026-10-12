"""Desktop note persistence and controller integration, using temporary files."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QCoreApplication, QPoint, QTimer
from PySide6.QtGui import QContextMenuEvent, QFont, QTextCursor
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox

from app import ConfigStore, Controller
from shd_desktop.notes.notes import NoteStore


app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 10))
with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    controller = Controller(app, ConfigStore(root / "config"), [desktop], enable_hotkeys=False)
    note = controller.notes.new_note()
    assert note["color"] == "石墨"
    window = controller.notes.windows[note["id"]]
    window.editor.setPlainText("记住这件事")
    window.save_text()
    assert window.editor_menu is None  # Rich controls load only on first right click.
    point = window.header.rect().center()
    QCoreApplication.sendEvent(window.header, QContextMenuEvent(
        QContextMenuEvent.Mouse, point, window.header.mapToGlobal(point)))
    assert window.editor_menu is not None and window.editor_menu.menu.isVisible()
    edit_menu = window.editor_menu
    assert {"撤销", "剪切", "复制", "粘贴", "粘贴为纯文本", "全选", "查找与替换", "清除格式"} <= {
        action.text().split("\t")[0] for action in edit_menu.menu.actions()}
    edit_menu.menu.grab().save(str(Path(__file__).resolve().parent / "preview-note-editor-menu.png"))
    edit_menu.menu.hide()
    body_point = window.editor.viewport().rect().center()
    QCoreApplication.sendEvent(window.editor.viewport(), QContextMenuEvent(
        QContextMenuEvent.Mouse, body_point,
        window.editor.viewport().mapToGlobal(body_point)))
    assert edit_menu.menu.isVisible()
    edit_menu.menu.hide()
    cursor = window.editor.textCursor()
    cursor.select(QTextCursor.Document)
    window.editor.setTextCursor(cursor)
    edit_menu.toggle_style("bold")
    assert window.editor.textCursor().charFormat().fontWeight() >= QFont.Bold
    window.save_text()
    assert NoteStore(root / "config").get(note["id"])["html"]
    window.set_field("color", "薄荷")
    window.set_field("opacity", 75)
    window.set_field("group", "工作")
    window.set_topmost(True)
    app.processEvents()
    window.grab().save(str(Path(__file__).resolve().parent / "preview-notes.png"))
    window.open_menu()
    app.processEvents()
    menu = next(child for child in window.findChildren(QMenu) if child.isVisible())
    labels = [action.text().split("\t")[0] for action in menu.actions()]
    assert {"新建便签", "提醒…", "复制便签", "总在最前", "锁定便签", "删除便签"} <= set(labels)
    menu.grab().save(str(Path(__file__).resolve().parent / "preview-notes-menu.png"))
    menu.hide()
    window.set_field("locked", True)
    assert window.editor.isReadOnly()
    edit_menu.open(window.mapToGlobal(QPoint(3, 3)), locked=True)
    assert not edit_menu.bold.isEnabled() and not edit_menu.cut_action.isEnabled()
    edit_menu.menu.hide()
    window.set_field("locked", False)
    window.toggle_collapsed()
    assert note["collapsed"] and window.height() == 44
    window.toggle_collapsed()
    assert not note["collapsed"] and window.height() >= 150
    window.resize(410, 320)
    window.save_geometry()
    QTimer.singleShot(0, lambda: next(w for w in app.topLevelWidgets()
                                     if w.windowTitle() == "便签提醒").accept())
    controller.notes.set_alarm(note)
    assert controller.events.get(note["event_id"]) is not None
    controller.notes.update_note(note["id"], title="改名后的便签")
    assert controller.events.get(note["event_id"])["title"] == "便签：改名后的便签"
    window.hide_note()
    saved = NoteStore(root / "config").get(note["id"])
    assert saved["text"] == "记住这件事" and saved["color"] == "薄荷"
    assert saved["opacity"] == 75 and saved["group"] == "工作"
    assert saved["topmost"] and saved["hidden"] and saved["w"] == 410
    controller.show_all()
    assert note["hidden"] and not window.isVisible()
    controller.notes.show_manager(note["id"])
    assert controller.center.tabs.currentWidget() is controller.notes
    assert not controller.notes.isWindow()
    controller.center.grab().save(str(Path(__file__).resolve().parent / "preview-notes-center.png"))
    controller.notes.open_selected()
    assert not note["hidden"] and window.isVisible()
    duplicate = controller.notes.new_note(note)
    assert duplicate["text"] == note["text"] and duplicate["id"] != note["id"]
    assert duplicate["html"] == note["html"]
    duplicate_cursor = controller.notes.windows[duplicate["id"]].editor.textCursor()
    duplicate_cursor.setPosition(1)
    assert duplicate_cursor.charFormat().fontWeight() >= QFont.Bold
    assert "event_id" not in duplicate
    original_question = QMessageBox.question
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
    try:
        controller.notes.delete_note(duplicate)
        assert duplicate["deleted"] and duplicate["hidden"]
        controller.notes.show_trash()
        assert controller.center.tabs.currentWidget() is controller.notes
        assert controller.notes.trash_mode
        controller.notes.list.setCurrentRow(0)
        controller.notes.open_selected()
        assert not duplicate["deleted"]
    finally:
        QMessageBox.question = original_question
    dispatcher = controller.llm.dispatcher
    result = json.loads(dispatcher.execute("create_note", {"title": "ISAC 新建", "text": "原文", "group": "工作"}))
    tool_id = result["id"]
    assert any(n["id"] == tool_id for n in json.loads(dispatcher.execute("list_notes", {})))
    assert "原文" in dispatcher.execute("get_note", {"id": tool_id})
    assert dispatcher.execute("update_note", {"id": tool_id, "text": "改过"}) == "已更新便签"
    assert controller.notes.store.get(tool_id)["text"] == "改过"
    assert dispatcher.execute("delete_note", {"id": tool_id}) == "已移入便签回收区"
    assert controller.notes.store.get(tool_id)["deleted"]
    controller.notes.show_manager()
    controller.notes.show_trash()
    trash_row = next(i for i in range(controller.notes.list.count())
                     if controller.notes.list.item(i).data(256) == tool_id)
    controller.notes.list.setCurrentRow(trash_row)
    assert controller.notes.delete_button.text() == "永久删除"
    assert controller.notes.empty_trash_button.isVisible()
    original_question = QMessageBox.question
    try:
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.No
        controller.notes.delete_selected()
        assert controller.notes.store.get(tool_id) is not None
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
        controller.notes.delete_selected()
        assert controller.notes.store.get(tool_id) is None
        for title in ("待清空一", "待清空二"):
            candidate = controller.notes.new_note()
            controller.notes.update_note(candidate["id"], title=title)
            controller.notes.delete_note(candidate, confirm=False)
        assert sum(bool(n.get("deleted")) for n in controller.notes.store.notes) == 2
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.No
        controller.notes.empty_trash()
        assert sum(bool(n.get("deleted")) for n in controller.notes.store.notes) == 2
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
        controller.notes.empty_trash()
        assert not any(n.get("deleted") for n in controller.notes.store.notes)
        assert not any(n.get("deleted") for n in NoteStore(root / "config").notes)
    finally:
        QMessageBox.question = original_question
    controller.events.close()
    controller.center.music.bridge.close()
    controller._shell_timer.stop()
    controller.reminder_timer.stop()
print("notes persistence, display, duplicate, and trash passed")
