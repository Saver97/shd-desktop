"""Rich-text context menu shared by every surface of a desktop note."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QTextCharFormat, QTextCursor, QTextListFormat
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QFontComboBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QSpinBox, QTextEdit,
    QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)


class NoteEditorMenu:
    def __init__(self, parent: QWidget, editor: QTextEdit):
        self.parent = parent
        self.editor = editor
        self.locked = False
        self.find_text = ""
        self.menu = QMenu(parent)
        self.menu.setObjectName("NoteEditorContextMenu")
        self.menu.setStyleSheet("""
            QMenu#NoteEditorContextMenu { background: #242A31; color: #F4F5F6;
                border: 1px solid #697480; border-radius: 7px; padding: 6px; }
            QMenu#NoteEditorContextMenu::item { background: transparent; color: #F4F5F6;
                padding: 8px 24px 8px 12px; }
            QMenu#NoteEditorContextMenu::item:selected { background: #495561;
                color: #FFFFFF; }
            QMenu#NoteEditorContextMenu::item:disabled { color: #A8B0B9; }
            QMenu#NoteEditorContextMenu::separator { height: 1px;
                background: #52606B; margin: 6px 10px; }
            QMenu#NoteEditorContextMenu QToolButton,
            QMenu#NoteEditorContextMenu QSpinBox,
            QMenu#NoteEditorContextMenu QFontComboBox { background: #303944;
                color: #F4F5F6; border: 1px solid #697480; border-radius: 4px;
                padding: 2px; min-height: 25px; }
            QMenu#NoteEditorContextMenu QToolButton:hover { background: #52616E;
                border-color: #E99549; }
            QMenu#NoteEditorContextMenu QToolButton:checked { background: #744522;
                color: #FFFFFF; border-color: #F1A15A; }
            QMenu#NoteEditorContextMenu QToolButton:disabled { color: #A8B0B9; }
            QMenu#NoteEditorContextMenu QLabel { color: #D5DEE6; }
        """)
        self.font_family = QFontComboBox()
        self.font_family.setMinimumWidth(152)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 72)
        self.font_size.setSuffix(" pt")
        self.font_size.setFixedWidth(65)
        self.text_color = self._button("A", "文字颜色", self.choose_text_color)
        self.highlight = self._button("▰", "文字底色", self.choose_highlight)
        self._row(None, self.font_family, self.font_size, self.text_color, self.highlight)
        self.font_family.currentFontChanged.connect(lambda font: self.set_font_family(font.family()))
        self.font_size.valueChanged.connect(self.set_font_size)

        self.bold = self._button("B", "加粗", lambda: self.toggle_style("bold"), checkable=True)
        self.italic = self._button("I", "斜体", lambda: self.toggle_style("italic"), checkable=True)
        self.underline = self._button("U", "下划线", lambda: self.toggle_style("underline"), checkable=True)
        self.strike = self._button("S̶", "删除线", lambda: self.toggle_style("strike"), checkable=True)
        self._row("样式", self.bold, self.italic, self.underline, self.strike)

        self.left = self._button("≡", "左对齐", lambda: self.align(Qt.AlignLeft))
        self.center = self._button("☷", "居中", lambda: self.align(Qt.AlignHCenter))
        self.right = self._button("≡", "右对齐", lambda: self.align(Qt.AlignRight))
        self.indent_less = self._button("⇤", "减少缩进", lambda: self.indent(-1))
        self.indent_more = self._button("⇥", "增加缩进", lambda: self.indent(1))
        self.bullets = self._button("☷", "项目符号", lambda: self.make_list(QTextListFormat.ListDisc))
        self.numbers = self._button("1.", "编号列表", lambda: self.make_list(QTextListFormat.ListDecimal))
        self._row("段落", self.left, self.center, self.right,
                  self.indent_less, self.indent_more, self.bullets, self.numbers)

        self.todo = self._button("☐", "插入待办复选框", lambda: self.editor.insertPlainText("☐ "))
        self.link = self._button("🔗", "插入链接", self.insert_link)
        self.date = self._button("◷", "插入当前日期时间", self.insert_date)
        self._row("插入", self.todo, self.link, self.date)
        self.edit_buttons = (self.text_color, self.highlight, self.bold, self.italic,
                             self.underline, self.strike, self.left, self.center,
                             self.right, self.indent_less, self.indent_more,
                             self.bullets, self.numbers, self.todo, self.link, self.date)

        self.menu.addSeparator()
        self.undo_action = self.menu.addAction("撤销\tCtrl+Z", self.editor.undo)
        self.redo_action = self.menu.addAction("重做\tCtrl+Y", self.editor.redo)
        self.menu.addSeparator()
        self.cut_action = self.menu.addAction("剪切\tCtrl+X", self.editor.cut)
        self.copy_action = self.menu.addAction("复制\tCtrl+C", self.editor.copy)
        self.paste_action = self.menu.addAction("粘贴\tCtrl+V", self.editor.paste)
        self.plain_paste_action = self.menu.addAction("粘贴为纯文本\tCtrl+Shift+V", self.paste_plain)
        self.delete_action = self.menu.addAction("删除\tDel", self.delete_selection)
        self.menu.addSeparator()
        self.select_action = self.menu.addAction("全选\tCtrl+A", self.editor.selectAll)
        find = self.menu.addMenu("查找与替换")
        find.addAction("查找…", self.find_dialog)
        find.addAction("查找下一个", self.find_next)
        find.addAction("替换…", self.replace_dialog)
        self.clear_action = self.menu.addAction("清除格式", self.clear_format)

    def _button(self, label: str, tooltip: str, callback, *, checkable: bool = False) -> QToolButton:
        button = QToolButton(self.menu)
        button.setText(label)
        button.setToolTip(tooltip)
        button.setCheckable(checkable)
        button.setFixedWidth(27)
        button.clicked.connect(callback)
        return button

    def _row(self, title: str | None, *controls: QWidget) -> None:
        row = QWidget(self.menu)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        if title:
            label = QLabel(title, row)
            label.setFixedWidth(42)
            layout.addWidget(label)
        for control in controls:
            layout.addWidget(control)
        layout.addStretch(1)
        action = QWidgetAction(self.menu)
        action.setDefaultWidget(row)
        self.menu.addAction(action)

    def open(self, global_pos, *, locked: bool = False) -> None:
        self.locked = locked
        fmt = self.editor.currentCharFormat()
        with QSignalBlocker(self.font_family):
            self.font_family.setCurrentFont(fmt.font())
        with QSignalBlocker(self.font_size):
            self.font_size.setValue(round(fmt.fontPointSize() or self.editor.font().pointSizeF() or 10))
        self.font_family.setEnabled(not locked)
        self.font_size.setEnabled(not locked)
        for button in self.edit_buttons:
            button.setEnabled(not locked)
        for button, value in ((self.bold, fmt.fontWeight() >= QFont.Bold),
                              (self.italic, fmt.fontItalic()),
                              (self.underline, fmt.fontUnderline()),
                              (self.strike, fmt.fontStrikeOut())):
            with QSignalBlocker(button):
                button.setChecked(value)
        selected = self.editor.textCursor().hasSelection()
        clipboard = QGuiApplication.clipboard().mimeData()
        self.undo_action.setEnabled(not locked and self.editor.document().isUndoAvailable())
        self.redo_action.setEnabled(not locked and self.editor.document().isRedoAvailable())
        self.cut_action.setEnabled(not locked and selected)
        self.copy_action.setEnabled(selected)
        self.paste_action.setEnabled(not locked and clipboard is not None and clipboard.hasText())
        self.plain_paste_action.setEnabled(self.paste_action.isEnabled())
        self.delete_action.setEnabled(not locked and selected)
        self.select_action.setEnabled(bool(self.editor.toPlainText()))
        self.clear_action.setEnabled(not locked)
        self.menu.popup(global_pos)

    def _merge(self, fmt: QTextCharFormat) -> None:
        if self.locked:
            return
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)
        self.editor.setFocus()

    def set_font_family(self, family: str) -> None:
        fmt = QTextCharFormat()
        fmt.setFontFamily(family)
        self._merge(fmt)

    def set_font_size(self, size: int) -> None:
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        self._merge(fmt)

    def toggle_style(self, style: str) -> None:
        fmt = QTextCharFormat()
        current = self.editor.currentCharFormat()
        if style == "bold":
            fmt.setFontWeight(QFont.Normal if current.fontWeight() >= QFont.Bold else QFont.Bold)
        elif style == "italic":
            fmt.setFontItalic(not current.fontItalic())
        elif style == "underline":
            fmt.setFontUnderline(not current.fontUnderline())
        else:
            fmt.setFontStrikeOut(not current.fontStrikeOut())
        self._merge(fmt)

    def choose_text_color(self) -> None:
        color = QColorDialog.getColor(self.editor.textColor(), self.parent, "文字颜色")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._merge(fmt)

    def choose_highlight(self) -> None:
        color = QColorDialog.getColor(QColor("#FFE09B"), self.parent, "文字底色")
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self._merge(fmt)

    def align(self, alignment) -> None:
        if not self.locked:
            self.editor.setAlignment(alignment)
            self.editor.setFocus()

    def indent(self, amount: int) -> None:
        if self.locked:
            return
        cursor = self.editor.textCursor()
        block = cursor.blockFormat()
        block.setIndent(max(0, block.indent() + amount))
        cursor.setBlockFormat(block)
        self.editor.setFocus()

    def make_list(self, style) -> None:
        if not self.locked:
            self.editor.textCursor().createList(style)
            self.editor.setFocus()

    def insert_link(self) -> None:
        if self.locked:
            return
        url, accepted = QInputDialog.getText(self.parent, "插入链接", "链接地址（https://…）")
        if not accepted or not url.strip():
            return
        url = url.strip()
        if not url.lower().startswith(("http://", "https://")):
            QMessageBox.warning(self.parent, "链接地址", "只支持 http:// 或 https:// 链接。")
            return
        cursor = self.editor.textCursor()
        label = cursor.selectedText().replace("\u2029", " ") or url
        fmt = QTextCharFormat()
        fmt.setAnchor(True)
        fmt.setAnchorHref(url)
        fmt.setForeground(QColor("#D97927"))
        fmt.setFontUnderline(True)
        cursor.insertText(label, fmt)

    def insert_date(self) -> None:
        if not self.locked:
            self.editor.insertPlainText(datetime.now().strftime("%Y-%m-%d %H:%M"))

    def paste_plain(self) -> None:
        if not self.locked:
            self.editor.insertPlainText(QGuiApplication.clipboard().text())

    def delete_selection(self) -> None:
        if not self.locked:
            self.editor.textCursor().removeSelectedText()

    def clear_format(self) -> None:
        if self.locked:
            return
        cursor = self.editor.textCursor()
        plain = QTextCharFormat()
        if cursor.hasSelection():
            cursor.setCharFormat(plain)
        self.editor.setCurrentCharFormat(plain)
        self.editor.setFocus()

    def find_dialog(self) -> None:
        value, accepted = QInputDialog.getText(self.parent, "查找文字", "查找", text=self.find_text)
        if accepted and value:
            self.find_text = value
            self.find_next()

    def find_next(self) -> None:
        if not self.find_text:
            self.find_dialog()
            return
        if not self.editor.find(self.find_text):
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)
            if not self.editor.find(self.find_text):
                QMessageBox.information(self.parent, "查找文字", "没有找到匹配内容。")

    def replace_dialog(self) -> None:
        if self.locked:
            return
        dialog = QDialog(self.parent)
        dialog.setWindowTitle("查找与替换")
        layout = QVBoxLayout(dialog)
        source = QLineEdit(self.find_text, dialog)
        source.setPlaceholderText("查找")
        target = QLineEdit(dialog)
        target.setPlaceholderText("替换为")
        layout.addWidget(source)
        layout.addWidget(target)
        buttons = QHBoxLayout()
        for label, callback in (
                ("查找下一个", lambda: self._find_from_dialog(source)),
                ("替换当前", lambda: self._replace_current(source, target)),
                ("全部替换", lambda: self._replace_all(source, target))):
            button = QPushButton(label, dialog)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        dialog.exec()

    def _find_from_dialog(self, source: QLineEdit) -> None:
        self.find_text = source.text()
        if self.find_text:
            self.find_next()

    def _replace_current(self, source: QLineEdit, target: QLineEdit) -> None:
        needle = source.text()
        if not needle:
            return
        self.find_text = needle
        cursor = self.editor.textCursor()
        if cursor.selectedText() != needle:
            self.find_next()
            cursor = self.editor.textCursor()
        if cursor.selectedText() == needle:
            cursor.insertText(target.text())

    def _replace_all(self, source: QLineEdit, target: QLineEdit) -> None:
        needle = source.text()
        if not needle:
            return
        self.find_text = needle
        cursor = QTextCursor(self.editor.document())
        cursor.beginEditBlock()
        count = 0
        while True:
            found = self.editor.document().find(needle, cursor)
            if found.isNull():
                break
            found.insertText(target.text())
            cursor = found
            count += 1
        cursor.endEditBlock()
        QMessageBox.information(self.parent, "查找与替换", f"已替换 {count} 处。")
