"""Search cached panel entries; do not scan the disk on every keystroke."""

import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                              QListWidgetItem, QPushButton, QVBoxLayout)


class QuickFind(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("SHD Desktop · 快速查找")
        self.setWindowIcon(controller.app.windowIcon())
        self.resize(600, 430)
        self.records = []
        root = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("输入图标、文件或分框名称…")
        self.query.returnPressed.connect(self.open_selected)
        root.addWidget(self.query)
        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self.open_selected)
        root.addWidget(self.results, 1)
        row = QHBoxLayout()
        for title, callback in (("打开", self.open_selected), ("定位分框", self.locate_selected),
                                ("刷新列表", self.reload)):
            button = QPushButton(title)
            button.setAutoDefault(False)
            button.clicked.connect(callback)
            row.addWidget(button)
        root.addLayout(row)
        self.status = QLabel()
        root.addWidget(self.status)
        self.filter_timer = QTimer(self)
        self.filter_timer.setSingleShot(True)
        self.filter_timer.setInterval(60)
        self.filter_timer.timeout.connect(self.filter)
        self.query.textChanged.connect(lambda: self.filter_timer.start())
        self.locate_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.locate_shortcut.activated.connect(self.locate_selected)
        self.list_open_shortcut = QShortcut(QKeySequence("Return"), self.results)
        self.list_open_shortcut.activated.connect(self.open_selected)
        self.navigation = []
        for key, delta in (("Down", 1), ("Up", -1)):
            shortcut = QShortcut(QKeySequence(key), self.query)
            shortcut.activated.connect(lambda step=delta: self.results.setCurrentRow(
                max(0, min(self.results.count() - 1, self.results.currentRow() + step))))
            self.navigation.append(shortcut)

    def show_search(self):
        self.reload()
        self.show()
        self.raise_()
        self.activateWindow()
        self.query.setFocus()
        self.query.selectAll()

    def reload(self):
        self.records = self.controller.search_records()
        self.filter()

    def filter(self):
        self.filter_timer.stop()
        terms = self.query.text().casefold().split()
        matches = [record for record in self.records if all(term in record["search"] for term in terms)]
        self.results.setUpdatesEnabled(False)
        try:
            self.results.clear()
            for record in matches[:300]:
                item = QListWidgetItem(record["icon"], f"{record['name']}  ·  {record['panel_title']}")
                item.setData(Qt.UserRole, record)
                item.setToolTip(record["path"])
                self.results.addItem(item)
            if self.results.count():
                self.results.setCurrentRow(0)
        finally:
            self.results.setUpdatesEnabled(True)
        extra = "；前 300 项，继续输入缩小范围" if len(matches) > 300 else ""
        self.status.setText(f"{len(matches)} 项{extra}  //  Enter 打开 · Ctrl+Enter 定位 · Esc 关闭")

    def selected(self):
        item = self.results.currentItem()
        return item.data(Qt.UserRole) if item else None

    def open_selected(self, *_):
        if self.filter_timer.isActive():
            self.filter()
        record = self.selected()
        if not record:
            return
        path = Path(record["path"])
        if not path.exists():
            self.status.setText("项目已移动或删除，请刷新列表")
            return
        try:
            os.startfile(str(path))
        except OSError as exc:
            self.status.setText(f"无法打开：{exc}")
            return
        self.hide()

    def locate_selected(self):
        if self.filter_timer.isActive():
            self.filter()
        record = self.selected()
        if record:
            if self.controller.locate_search_result(record):
                self.hide()
            else:
                self.status.setText("分框或项目已变化，请刷新列表")
