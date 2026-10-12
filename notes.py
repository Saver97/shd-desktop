"""Local desktop notes for SHD Desktop."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QDateTime, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QMouseEvent, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout,
    QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSizeGrip, QSystemTrayIcon,
    QVBoxLayout, QWidget,
)


COLORS = {
    "琥珀": ("#F3D883", "#191814"),
    "浅黄": ("#FFF7A0", "#252116"),
    "薄荷": ("#BCE8D6", "#172820"),
    "天空": ("#BEDDF2", "#172430"),
    "紫雾": ("#DAD1EE", "#282135"),
    "石墨": ("#292D32", "#F1F1F1"),
}
DEFAULT_COLOR = "石墨"


class NoteStore:
    def __init__(self, root: Path):
        self.path = root / "notes.json"
        self.backup = root / "notes.backup.json"
        self.notes: list[dict] = []
        for path in (self.path, self.backup):
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, list):
                    raise ValueError("invalid note data")
                self.notes = [item for item in data if isinstance(item, dict) and item.get("id")]
                break
            except (OSError, ValueError):
                continue
        else:
            if self.path.exists() or self.backup.exists():
                raise OSError(f"便签数据损坏，原文件已保留：{self.path}")

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(self.notes, ensure_ascii=False, indent=2)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(serialized, encoding="utf-8")
        os.replace(temp, self.path)
        try:
            backup_temp = self.backup.with_suffix(".tmp")
            backup_temp.write_text(serialized, encoding="utf-8")
            os.replace(backup_temp, self.backup)
        except OSError:
            pass

    def get(self, note_id: str) -> dict | None:
        return next((note for note in self.notes if note.get("id") == note_id), None)

    def create(self, *, source: dict | None = None, position: QPoint | None = None) -> dict:
        count = sum(not n.get("deleted") for n in self.notes)
        note = {
            "id": uuid.uuid4().hex, "title": "新便签", "text": "", "color": DEFAULT_COLOR,
            "opacity": 96, "x": 130 + 32 * (count % 9), "y": 130 + 32 * (count % 9),
            "w": 330, "h": 260, "hidden": False, "topmost": False,
            "locked": False, "starred": False, "group": "未分类", "deleted": False,
        }
        if source:
            for key in ("title", "text", "color", "opacity", "w", "h", "topmost", "group"):
                note[key] = source.get(key, note[key])
            note["x"] = int(source.get("x", note["x"])) + 28
            note["y"] = int(source.get("y", note["y"])) + 28
        if position:
            note["x"], note["y"] = position.x(), position.y()
        self.notes.append(note)
        self.save()
        return note


class NoteHeader(QLabel):
    def __init__(self, window: "NoteWindow"):
        super().__init__(window)
        self.window = window
        self.origin: QPoint | None = None
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and not self.window.note.get("locked"):
            self.origin = event.globalPosition().toPoint() - self.window.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.origin is not None and event.buttons() & Qt.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.origin)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.origin is not None:
            self.origin = None
            self.setCursor(Qt.OpenHandCursor)
            self.window.save_geometry()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.window.rename()


class NoteWindow(QWidget):
    def __init__(self, manager: "NotesManager", note: dict):
        super().__init__()
        self.manager = manager
        self.note = note
        self.setObjectName("ShdNote")
        self.setMinimumSize(220, 150)
        self._saving = False
        self._screen_relocating = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(350)
        self._save_timer.timeout.connect(self.save_text)
        self._set_window_flags()
        self.setGeometry(note.get("x", 130), note.get("y", 130),
                         max(220, note.get("w", 330)), max(150, note.get("h", 260)))
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 9, 7)
        root.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        self.header = NoteHeader(self)
        self.header.setObjectName("NoteHeader")
        title_row.addWidget(self.header, 1)
        self.menu_button = QPushButton("⋯")
        self.menu_button.setObjectName("NoteMenuButton")
        self.menu_button.setFixedSize(27, 25)
        self.menu_button.clicked.connect(self.open_menu)
        title_row.addWidget(self.menu_button)
        self.hide_button = QPushButton("×")
        self.hide_button.setObjectName("NoteHideButton")
        self.hide_button.setFixedSize(27, 25)
        self.hide_button.setToolTip("隐藏便签，可从便签管理找回")
        self.hide_button.clicked.connect(self.hide_note)
        title_row.addWidget(self.hide_button)
        root.addLayout(title_row)
        self.editor = QPlainTextEdit(self)
        self.editor.setObjectName("NoteEditor")
        self.editor.setFrameStyle(0)
        self.editor.setPlainText(str(note.get("text", "")))
        self.editor.textChanged.connect(self._save_timer.start)
        root.addWidget(self.editor, 1)
        footer = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setObjectName("NoteHint")
        footer.addWidget(self.hint, 1)
        self.grip = QSizeGrip(self)
        footer.addWidget(self.grip)
        root.addLayout(footer)
        self.shortcuts = []
        for sequence, callback in (("Alt+N", manager.new_note), ("F2", self.rename),
                                   ("Alt+A", lambda: manager.set_alarm(self.note)),
                                   ("Alt+D", lambda: manager.new_note(self.note)),
                                   ("Alt+T", lambda: self.set_topmost(not self.note.get("topmost"))),
                                   ("Alt+L", lambda: self.set_field("locked", not self.note.get("locked"))),
                                   ("Alt+M", self.toggle_collapsed), ("Alt+Delete", lambda: manager.delete_note(self.note))):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        if note.get("collapsed"):
            self._apply_collapsed(True)
        self.refresh()

    def _set_window_flags(self) -> None:
        flags = Qt.Tool | Qt.FramelessWindowHint
        flags |= Qt.WindowStaysOnTopHint if self.note.get("topmost") else Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def refresh(self) -> None:
        name = self.note.get("color", DEFAULT_COLOR)
        background, foreground = COLORS.get(name, COLORS[DEFAULT_COLOR])
        self.setWindowTitle(self.note.get("title", "新便签"))
        self.header.setText(("★  " if self.note.get("starred") else "") + self.windowTitle())
        self.editor.setReadOnly(bool(self.note.get("locked")))
        self.grip.setVisible(not self.note.get("locked") and not self.note.get("collapsed"))
        reminder = self.manager.events.get(self.note.get("event_id", "")) if self.note.get("event_id") else None
        status = "已锁定" if self.note.get("locked") else ("置顶" if self.note.get("topmost") else "桌面便签")
        if reminder:
            stamp = datetime.fromtimestamp(reminder["start_ms"] / 1000).strftime("%m-%d %H:%M")
            status += f"  ·  提醒 {stamp}"
        self.hint.setText(status)
        self.setStyleSheet(f"""
            QWidget#ShdNote {{ color: {foreground}; }}
            QLabel#NoteHeader {{ color: {foreground}; font-size: 13px; font-weight: 600; }}
            QLabel#NoteHint {{ color: {foreground}; font-size: 10px; }}
            QPlainTextEdit#NoteEditor {{ color: {foreground}; background: transparent;
                border: 0; font-size: 13px; selection-background-color: #F48A35;
                selection-color: #171717; }}
            QPushButton#NoteMenuButton, QPushButton#NoteHideButton {{ color: {foreground};
                background: transparent; border: 0; font-size: 18px; padding: 0; }}
            QPushButton#NoteMenuButton:hover, QPushButton#NoteHideButton:hover {{
                background: {background}; border: 1px solid {foreground}; }}
        """)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        background = QColor(COLORS.get(self.note.get("color"), COLORS[DEFAULT_COLOR])[0])
        background.setAlpha(round(max(35, min(100, int(self.note.get("opacity", 96)))) * 255 / 100))
        painter.fillRect(self.rect().adjusted(1, 1, -1, -1), background)
        painter.fillRect(1, 0, 4, self.height(), QColor("#F48A35"))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible() and not self.note.get("locked"):
            self.save_geometry(deferred=True)

    def save_geometry(self, deferred: bool = False) -> None:
        if self._saving:
            return
        if self._screen_relocating:
            return
        rect = self.geometry()
        self.note.update(x=rect.x(), y=rect.y(), w=rect.width(), h=rect.height())
        if deferred:
            self._save_timer.start()
        else:
            self.manager.store.save()

    def save_text(self) -> None:
        self.note["text"] = self.editor.toPlainText()
        self.manager.store.save()
        self.manager.refresh_list()

    def hide_note(self) -> None:
        self._save_timer.stop()
        self.save_text()
        self.save_geometry()
        self.note["hidden"] = True
        self.manager.store.save()
        self.hide()
        self.manager.refresh_list()

    def _apply_collapsed(self, collapsed: bool) -> None:
        self._saving = True
        try:
            if collapsed:
                if not self.note.get("collapsed"):
                    self.note["expanded_h"] = max(150, self.height())
                self.setMinimumHeight(44)
                self.setMaximumHeight(44)
                self.resize(self.width(), 44)
            else:
                self.setMaximumHeight(16777215)
                self.setMinimumHeight(150)
                self.resize(self.width(), max(150, int(self.note.get("expanded_h", 260))))
            self.editor.setVisible(not collapsed)
            self.hint.setVisible(not collapsed)
            self.grip.setVisible(not collapsed and not self.note.get("locked"))
        finally:
            self._saving = False

    def toggle_collapsed(self) -> None:
        collapsed = not self.note.get("collapsed", False)
        self._apply_collapsed(collapsed)
        self.note["collapsed"] = collapsed
        self.save_geometry()

    def closeEvent(self, event) -> None:
        self.hide_note()
        event.ignore()

    def rename(self) -> None:
        if self.note.get("locked"):
            return
        title, ok = QInputDialog.getText(self, "便签标题", "标题", text=self.note.get("title", ""))
        if ok and title.strip():
            self.note["title"] = title.strip()
            self.manager.changed(self.note)

    def open_menu(self) -> None:
        self._save_timer.stop()
        self.save_text()
        menu = QMenu(self)
        menu.addAction("新建便签\tAlt+N", self.manager.new_note)
        colors = menu.addMenu("颜色")
        for name in COLORS:
            action = colors.addAction(name, lambda checked=False, value=name: self.set_field("color", value))
            action.setCheckable(True)
            action.setChecked(self.note.get("color") == name)
        opacity = menu.addMenu("透明度")
        for value in (100, 90, 75, 60, 40):
            action = opacity.addAction(f"{value}%", lambda checked=False, number=value: self.set_field("opacity", number))
            action.setCheckable(True)
            action.setChecked(self.note.get("opacity") == value)
        size = menu.addMenu("尺寸")
        for label, dimensions in (("小", (260, 190)), ("标准", (330, 260)), ("大", (440, 350))):
            size.addAction(label, lambda checked=False, dims=dimensions: self.resize(*dims))
        menu.addAction("提醒…", lambda: self.manager.set_alarm(self.note))
        rename = menu.addAction("编辑标题\tF2", self.rename)
        star = menu.addAction("取消收藏" if self.note.get("starred") else "收藏",
                              lambda: self.set_field("starred", not self.note.get("starred")))
        rename.setEnabled(not self.note.get("locked"))
        menu.addSeparator()
        menu.addAction("复制便签", lambda: self.manager.new_note(self.note))
        menu.addAction("在便签管理中定位", lambda: self.manager.show_manager(self.note["id"]))
        menu.addAction("导出文本…", self.export_text)
        top = menu.addAction("总在最前", lambda: self.set_topmost(not self.note.get("topmost")))
        top.setCheckable(True)
        top.setChecked(bool(self.note.get("topmost")))
        lock = menu.addAction("锁定便签", lambda: self.set_field("locked", not self.note.get("locked")))
        lock.setCheckable(True)
        lock.setChecked(bool(self.note.get("locked")))
        menu.addAction("展开" if self.note.get("collapsed") else "收起", self.toggle_collapsed)
        menu.addAction("隐藏", self.hide_note)
        move = menu.addMenu("移动到分组")
        groups = sorted({n.get("group", "未分类") for n in self.manager.store.notes if not n.get("deleted")}
                        | {"未分类"})
        for group in groups:
            action = move.addAction(group, lambda checked=False, value=group: self.set_field("group", value))
            action.setCheckable(True)
            action.setChecked(group == self.note.get("group", "未分类"))
        move.addSeparator()
        move.addAction("新建分组…", self.new_group)
        menu.addAction("删除便签", lambda: self.manager.delete_note(self.note))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def new_group(self) -> None:
        name, ok = QInputDialog.getText(self, "新建便签分组", "分组名称")
        if ok and name.strip():
            self.set_field("group", name.strip()[:50])

    def export_text(self) -> None:
        suggested = self.note.get("title", "新便签").replace("/", "_").replace("\\", "_") + ".txt"
        path, _filter = QFileDialog.getSaveFileName(self, "导出便签", suggested, "文本文件 (*.txt)")
        if path:
            try:
                Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "导出失败", str(exc))

    def set_topmost(self, value: bool) -> None:
        self.note["topmost"] = value
        self._set_window_flags()
        self.show()
        self.manager.changed(self.note)

    def set_field(self, key: str, value) -> None:
        self.note[key] = value
        self.manager.changed(self.note)


class NotesManager(QWidget):
    def __init__(self, root: Path, events, tray):
        super().__init__()
        self.store = NoteStore(root)
        self.events = events
        self.tray = tray
        self.windows: dict[str, NoteWindow] = {}
        self.present_in_center = None
        self.setWindowTitle("SHD Desktop · 便签管理")
        self.resize(500, 490)
        self.setMinimumSize(390, 320)
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        label = QLabel("便签  //  NOTES")
        label.setStyleSheet("color:#F48A35;font-size:16px;font-weight:600")
        heading.addWidget(label)
        heading.addStretch()
        self.empty_trash_button = QPushButton("清空回收区")
        self.empty_trash_button.clicked.connect(self.empty_trash)
        heading.addWidget(self.empty_trash_button)
        self.trash_button = QPushButton("回收区")
        self.trash_button.clicked.connect(self.show_trash)
        heading.addWidget(self.trash_button)
        new_button = QPushButton("＋ 新建便签")
        new_button.clicked.connect(self.new_note)
        heading.addWidget(new_button)
        layout.addLayout(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题、内容或分组")
        self.search.textChanged.connect(self.refresh_list)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.list.itemSelectionChanged.connect(self._refresh_actions)
        layout.addWidget(self.list, 1)
        actions = QHBoxLayout()
        for title, callback in (("打开", self.open_selected), ("显示全部", self.show_all),
                                ("删除", self.delete_selected)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
            if title == "打开":
                self.open_button = button
            if title == "显示全部":
                self.show_all_button = button
            if title == "删除":
                self.delete_button = button
        layout.addLayout(actions)
        self.trash_mode = False
        self.refresh_list()
        for note in self.store.notes:
            if not note.get("deleted"):
                window = self._window(note)
                if not note.get("hidden"):
                    window.show()

    def _window(self, note: dict) -> NoteWindow:
        note_id = note["id"]
        if note_id not in self.windows:
            self.windows[note_id] = NoteWindow(self, note)
        return self.windows[note_id]

    def new_note(self, source: dict | None = None) -> dict:
        if not isinstance(source, dict):
            source = None
        if source and source.get("id") in self.windows:
            window = self.windows[source["id"]]
            window._save_timer.stop()
            window.save_text()
        note = self.store.create(source=source)
        window = self._window(note)
        window.show()
        window.raise_()
        window.editor.setFocus()
        self.refresh_list()
        return note

    def changed(self, note: dict) -> None:
        event_id = note.get("event_id")
        if event_id:
            event = self.events.get(event_id)
            title = f"便签：{note.get('title', '新便签')}"
            if event and event["title"] != title:
                self.events.rename(event_id, title)
        self.store.save()
        window = self.windows.get(note["id"])
        if window:
            window.refresh()
        self.refresh_list()

    def refresh_list(self) -> None:
        if not hasattr(self, "list"):
            return
        selected = self.selected_id()
        query = self.search.text().strip().casefold()
        self.list.clear()
        notes = [n for n in self.store.notes if bool(n.get("deleted")) == self.trash_mode]
        notes.sort(key=lambda n: (not n.get("starred", False), n.get("group", ""), n.get("title", "")))
        for note in notes:
            haystack = f"{note.get('title', '')} {note.get('text', '')} {note.get('group', '')}".casefold()
            if query and query not in haystack:
                continue
            prefix = "★ " if note.get("starred") else ""
            state = " · 已隐藏" if note.get("hidden") and not self.trash_mode else ""
            item = QListWidgetItem(f"{prefix}{note.get('title', '新便签')}  /  {note.get('group', '未分类')}{state}")
            item.setData(Qt.UserRole, note["id"])
            excerpt = str(note.get("text", "")).replace("\n", " ")[:160]
            item.setToolTip(excerpt)
            self.list.addItem(item)
            if note["id"] == selected:
                self.list.setCurrentItem(item)
        self._refresh_actions()

    def _refresh_actions(self) -> None:
        if not hasattr(self, "open_button"):
            return
        selected = self.selected_id() is not None
        trash_count = sum(bool(note.get("deleted")) for note in self.store.notes)
        self.trash_button.setText("返回便签" if self.trash_mode else f"回收区 ({trash_count})")
        self.empty_trash_button.setVisible(self.trash_mode)
        self.empty_trash_button.setEnabled(self.trash_mode and trash_count > 0)
        self.open_button.setText("恢复" if self.trash_mode else "打开")
        self.open_button.setEnabled(selected)
        self.delete_button.setText("永久删除" if self.trash_mode else "删除")
        self.delete_button.setEnabled(selected)
        self.show_all_button.setVisible(not self.trash_mode)

    def selected_id(self) -> str | None:
        item = self.list.currentItem() if hasattr(self, "list") else None
        return item.data(Qt.UserRole) if item else None

    def show_manager(self, note_id: str | None = None) -> None:
        self.trash_mode = False
        self.trash_button.setText("回收区")
        if note_id:
            self.search.clear()
        self.refresh_list()
        if note_id:
            for index in range(self.list.count()):
                item = self.list.item(index)
                if item.data(Qt.UserRole) == note_id:
                    self.list.setCurrentItem(item)
                    self.list.scrollToItem(item)
                    break
        self._present()

    def _present(self) -> None:
        if self.present_in_center:
            self.present_in_center()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def open_selected(self) -> None:
        note = self.store.get(self.selected_id() or "")
        if not note:
            return
        if note.get("deleted"):
            if QMessageBox.question(self, "恢复便签", f"恢复“{note.get('title', '新便签')}”？") != QMessageBox.Yes:
                return
            note["deleted"] = False
        note["hidden"] = False
        self.store.save()
        window = self._window(note)
        window.show()
        window.raise_()
        window.activateWindow()
        self.refresh_list()

    def show_all(self) -> None:
        for note in self.store.notes:
            if note.get("deleted"):
                continue
            note["hidden"] = False
            self._window(note).show()
        self.store.save()
        self.refresh_list()

    def show_trash(self) -> None:
        self.trash_mode = not self.trash_mode
        self.trash_button.setText("返回便签" if self.trash_mode else "回收区")
        self.refresh_list()
        self._present()

    def delete_selected(self) -> None:
        note = self.store.get(self.selected_id() or "")
        if note:
            if note.get("deleted"):
                self.purge_note(note)
            else:
                self.delete_note(note)

    def purge_note(self, note: dict) -> None:
        if not note.get("deleted"):
            return
        if QMessageBox.question(self, "永久删除便签",
                                f"永久删除“{note.get('title', '新便签')}”？此操作无法恢复。") != QMessageBox.Yes:
            return
        self._purge_deleted([note])

    def empty_trash(self) -> None:
        deleted = [note for note in self.store.notes if note.get("deleted")]
        if not deleted:
            return
        if QMessageBox.question(self, "清空便签回收区",
                                f"永久删除回收区中的 {len(deleted)} 张便签？此操作无法恢复。") != QMessageBox.Yes:
            return
        self._purge_deleted(deleted)

    def _purge_deleted(self, notes: list[dict]) -> None:
        ids = {note["id"] for note in notes if note.get("deleted")}
        if not ids:
            return
        for note in notes:
            if note["id"] not in ids:
                continue
            window = self.windows.pop(note["id"], None)
            if window:
                window._save_timer.stop()
                window.hide()
                window.deleteLater()
            event_id = note.get("event_id")
            if event_id and self.events.get(event_id):
                self.events.delete(event_id)
        self.store.notes[:] = [note for note in self.store.notes if note["id"] not in ids]
        self.store.save()
        self.refresh_list()

    def delete_note(self, note: dict, confirm: bool = True) -> None:
        if note.get("locked"):
            if confirm:
                QMessageBox.information(self, "便签已锁定", "请先解锁便签。")
            return
        if confirm and QMessageBox.question(self, "删除便签", f"将“{note.get('title', '新便签')}”移入回收区？") != QMessageBox.Yes:
            return
        window = self.windows.get(note["id"])
        if window:
            window._save_timer.stop()
            window.save_text()
            window.hide()
        note["deleted"] = True
        note["hidden"] = True
        event_id = note.pop("event_id", None)
        if event_id and self.events.get(event_id):
            self.events.delete(event_id)
        self.store.save()
        self.refresh_list()

    def set_alarm(self, note: dict) -> None:
        current = self.events.get(note.get("event_id", "")) if note.get("event_id") else None
        dialog = QDialog(self)
        dialog.setWindowTitle("便签提醒")
        form = QFormLayout(dialog)
        picker = QDateTimeEdit()
        picker.setCalendarPopup(True)
        picker.setDisplayFormat("yyyy-MM-dd HH:mm")
        picker.setDateTime(QDateTime.fromMSecsSinceEpoch(current["start_ms"]) if current
                           else QDateTime.currentDateTime().addSecs(3600))
        form.addRow("提醒时间", picker)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        remove = QPushButton("取消提醒")
        remove.setEnabled(current is not None)
        buttons.addButton(remove, QDialogButtonBox.ActionRole)
        remove.clicked.connect(lambda: dialog.done(2))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        result = dialog.exec()
        if result == 2:
            if current:
                self.events.delete(current["id"])
            note.pop("event_id", None)
        elif result == QDialog.Accepted:
            when = picker.dateTime().toMSecsSinceEpoch()
            if when <= QDateTime.currentMSecsSinceEpoch():
                QMessageBox.warning(self, "提醒时间", "请选择将来的时间。")
                return
            if current:
                self.events.delete(current["id"])
            note["event_id"] = self.events.add(f"便签：{note.get('title', '新便签')}", when, 0)
        else:
            return
        self.changed(note)
        self.tray.showMessage("SHD · 便签", "提醒已更新", QSystemTrayIcon.Information, 2500)

    def flush(self) -> None:
        for window in self.windows.values():
            if window._save_timer.isActive():
                window._save_timer.stop()
                window.save_text()
            if window.isVisible():
                window.save_geometry()

    def update_note(self, note_id: str, *, title: str | None = None,
                    text: str | None = None, group: str | None = None) -> dict:
        note = self.store.get(note_id)
        if not note or note.get("deleted"):
            raise ValueError("未找到便签 ID")
        if note.get("locked"):
            raise ValueError("便签已锁定")
        if title is not None:
            if not title.strip():
                raise ValueError("标题不能为空")
            note["title"] = title.strip()[:100]
        if group is not None:
            note["group"] = group.strip()[:50] or "未分类"
        if text is not None:
            note["text"] = text
            window = self.windows.get(note_id)
            if window:
                window._save_timer.stop()
                window.editor.setPlainText(text)
                window._save_timer.stop()
        self.changed(note)
        return note

