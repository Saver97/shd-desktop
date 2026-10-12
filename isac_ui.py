"""Compact daily chat and a separate multi-profile model settings window."""

from __future__ import annotations

import json
import html
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, QTimer, QUrl
from PySide6.QtGui import QColor, QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QTextBrowser, QPushButton,
    QVBoxLayout, QWidget,
)

from llm import LlmClient
from llm_profiles import api_base
from theme import HudHeader, hud_background, scaled_style


ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"
APP_ICON = Path(__file__).resolve().parent / "assets" / "app.ico"


class ChatDragLabel(QLabel):
    def __init__(self, window: "ChatWindow"):
        super().__init__(window)
        self.window = window
        self.origin = None
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self.window.pinned:
            self.origin = event.globalPosition().toPoint() - self.window.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.origin is not None and not self.window.pinned and event.buttons() & Qt.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.origin)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.origin = None
        self.setCursor(Qt.OpenHandCursor)
        self.window.save_geometry()


class ChatWindow(QWidget):
    def __init__(self, store, client: LlmClient, open_settings):
        super().__init__()
        self.store = store
        self.client = client
        self.open_settings = open_settings
        self._save_timer = store.geometry_timer()
        self.config = store.data.setdefault("chat_window", {"x": 840, "y": 180,
                                                               "w": 430, "h": 520, "pinned": False})
        self.pinned = bool(self.config.get("pinned"))
        self.setWindowTitle("SHD Desktop · ISAC")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint |
                            (Qt.WindowStaysOnBottomHint if self.pinned else Qt.WindowType(0)))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(360, 300)
        self.setGeometry(self.config.get("x", 840), self.config.get("y", 180),
                         self.config.get("w", 430), self.config.get("h", 520))
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 15)
        root.setSpacing(10)
        title_row = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QIcon(str(ICON_DIR / "fn-isac-gen-64.png")).pixmap(28, 28))
        title_row.addWidget(logo)
        self.drag_label = ChatDragLabel(self)
        self.drag_label.setText("ISAC  //  终端对话")
        self.drag_label.setStyleSheet("color:#F1F1F1;font-weight:400;font-size:18px")
        title_row.addWidget(self.drag_label, 1)
        self.signal_label = QLabel("●  ONLINE")
        self.signal_label.setStyleSheet("color:#85C8BF;font-size:10px;font-weight:700")
        title_row.addWidget(self.signal_label)
        self.pin_button = QPushButton()
        self.pin_button.clicked.connect(self.toggle_pin)
        title_row.addWidget(self.pin_button)
        settings_button = QPushButton("配置")
        settings_button.setFixedWidth(48)
        settings_button.setToolTip("模型配置")
        settings_button.clicked.connect(open_settings)
        title_row.addWidget(settings_button)
        close_button = QPushButton("×")
        close_button.setFixedWidth(32)
        close_button.clicked.connect(self.hide)
        title_row.addWidget(close_button)
        root.addLayout(title_row)
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background:rgba(255,255,255,45)")
        root.addWidget(divider)
        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("当前模型"))
        self.model_button = QPushButton()
        self.model_button.setMaximumWidth(260)
        self.model_menu = QMenu(self.model_button)
        self.model_button.setMenu(self.model_menu)
        profile_row.addWidget(self.model_button, 1)
        reset_button = QPushButton("新对话")
        reset_button.clicked.connect(self.new_chat)
        profile_row.addWidget(reset_button)
        root.addLayout(profile_row)
        self.log = QTextBrowser()
        self.log.setObjectName("DailyChatLog")
        self.log.setReadOnly(True)
        self.log.setOpenExternalLinks(False)
        self.log.setPlaceholderText("例如：明天 9 点提醒我开会；显示桌面文件夹；暂停音乐。")
        root.addWidget(self.log, 1)
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("输入消息或桌面指令…")
        self.input.returnPressed.connect(self.send)
        input_row.addWidget(self.input, 1)
        self.send_button = QPushButton("发送")
        self.send_button.setProperty("hudRole", "primary")
        self.send_button.clicked.connect(self.send)
        input_row.addWidget(self.send_button)
        self.stop_button = QPushButton("中断")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(client.cancel)
        input_row.addWidget(self.stop_button)
        root.addLayout(input_row)
        self.status = QLabel("就绪")
        self.status.setStyleSheet("color:#9FB5B9;font-size:11px")
        root.addWidget(self.status)
        client.answer.connect(self.answer)
        client.error.connect(self.error)
        client.busy_changed.connect(self.set_busy)
        client.profile_changed.connect(lambda: QTimer.singleShot(0, self.sync_profiles))
        client.interrupted.connect(self.on_interrupted)
        self.sync_profiles()
        self.update_pin_button()
        self.apply_hud()

    def apply_hud(self):
        self.drag_label.setStyleSheet(scaled_style("color:#F1F1F1;font-weight:400;font-size:18px"))
        self.status.setStyleSheet(scaled_style("color:#9FB5B9;font-size:11px"))
        self.log.document().setDefaultFont(self.input.font())
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect().adjusted(1, 1, -2, -2), hud_background())
        painter.fillRect(1, 15, 3, 28, QColor(244, 138, 53))

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self.save_geometry(deferred=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self.save_geometry(deferred=True)

    def save_geometry(self, deferred: bool = False):
        geometry = self.geometry()
        self.config.update(x=geometry.x(), y=geometry.y(), w=geometry.width(), h=geometry.height())
        if deferred:
            self._save_timer.start()
        else:
            self.store.save()

    def hideEvent(self, event):
        if self._save_timer.isActive():
            self.store.save()
        super().hideEvent(event)

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.config["pinned"] = self.pinned
        self.save_geometry()
        self.setWindowFlag(Qt.WindowStaysOnBottomHint, self.pinned)
        self.show()
        self.update_pin_button()

    def update_pin_button(self):
        self.pin_button.setText("解锁" if self.pinned else "固定")
        self.pin_button.setToolTip("固定后无法拖动窗口；再次点击解锁")

    def sync_profiles(self):
        self.model_menu.clear()
        active = self.client.profiles.active()
        for profile in self.client.profiles.profiles:
            submenu = self.model_menu.addMenu(profile["name"])
            models = profile.get("models", [])
            if not models:
                submenu.addAction("未保存模型").setEnabled(False)
            for model in models:
                action = submenu.addAction(model)
                action.setCheckable(True)
                action.setChecked(profile["id"] == active["id"] and model == active.get("model"))
                action.triggered.connect(
                    lambda _checked=False, pid=profile["id"], name=model: self.choose_model(pid, name))
        title = f"{active['name']} / {active.get('model') or '未设置模型'}"
        self.model_button.setText(title)
        self.model_button.setToolTip(title)

    def choose_model(self, profile_id: str, model: str):
        try:
            self.client.activate_model(profile_id, model)
            self.status.setText(f"已切换到 {model}，新对话已开始")
            self.log.clear()
        except ValueError as exc:
            self.status.setText(str(exc))
            self.sync_profiles()

    def append_message(self, role: str, content: str) -> None:
        palette = {
            "你": ("#FFAC70", "#38312C", "#FF8A31"),
            "ISAC": ("#A7D9D0", "#2B333C", "#6FC8B8"),
            "系统": ("#F3C982", "#3A3328", "#D6A54B"),
            "错误": ("#FF9A92", "#493033", "#E6665B"),
        }
        label, background, accent = palette.get(role, palette["系统"])
        safe = html.escape(content).replace("\n", "<br>")
        self.log.append(
            f'<table width="100%" cellspacing="0" cellpadding="8" bgcolor="{background}">'
            f'<tr><td><font color="{accent}">●</font> '
            f'<font color="{label}"><b>{role}</b></font><br>'
            f'<font color="#F1F3F3">{safe}</font></td></tr></table><br>')
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def new_chat(self):
        if self.client.busy:
            return
        self.client.clear_history()
        self.log.clear()
        self.status.setText("新对话已开始")

    def send(self):
        message = self.input.text().strip()
        if not message:
            return
        self.input.clear()
        self.append_message("你", message)
        self.client.ask(message)

    def answer(self, message: str):
        self.append_message("ISAC", message)
        self.status.setText("就绪")

    def error(self, message: str):
        self.append_message("错误", message)
        self.status.setText("请求失败")

    def on_interrupted(self):
        self.append_message("系统", "已中断当前回复")
        self.status.setText("已中断")

    def set_busy(self, busy: bool):
        self.input.setEnabled(not busy)
        self.send_button.setEnabled(not busy)
        self.stop_button.setEnabled(busy)
        self.signal_label.setText("●  BUSY" if busy else "●  ONLINE")
        self.signal_label.setStyleSheet(
            f"color:{'#F6A45B' if busy else '#85C8BF'};font-size:10px;font-weight:700")
        self.status.setText("正在回复…" if busy else "就绪")


class LlmSettingsWindow(QMainWindow):
    def __init__(self, client: LlmClient):
        super().__init__()
        self.client = client
        self.network = QNetworkAccessManager(self)
        self.current_id: str | None = None
        self.auto_fetched: set[str] = set()
        self.setWindowTitle("SHD Desktop · 模型配置")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(880, 660)
        self.setMinimumSize(760, 590)
        self.setMenuWidget(HudHeader("ISAC  /  MODEL ROUTING", "模型连接与配置档", "CONFIG  /  02"))
        body = QWidget()
        root = QHBoxLayout(body)
        left = QVBoxLayout()
        left.addWidget(QLabel("已保存的配置"))
        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(self.load_selected)
        left.addWidget(self.profile_list, 1)
        for label, handler in (("新增", self.add_profile), ("复制", self.duplicate_profile),
                               ("删除", self.delete_profile)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            left.addWidget(button)
        root.addLayout(left, 1)
        right = QVBoxLayout()
        right.addWidget(QLabel("连接设置  //  日常聊天窗口可按配置选择模型"))
        form = QFormLayout()
        self.name = QLineEdit()
        form.addRow("名称", self.name)
        self.mode = QComboBox()
        self.mode.addItem("Chat Completions", "chat")
        self.mode.addItem("Responses", "responses")
        form.addRow("API 模式", self.mode)
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("https://api.openai.com/v1")
        form.addRow("API 地址", self.base_url)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        form.addRow("API 密钥", self.key)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.setInsertPolicy(QComboBox.NoInsert)
        form.addRow("模型", self.model)
        self.models_url = QLineEdit()
        self.models_url.setPlaceholderText("留空时使用 API 地址下的 /models")
        form.addRow("模型列表 URL", self.models_url)
        right.addLayout(form)
        right.addWidget(QLabel("此配置保存的模型  //  可在聊天窗口按配置展开选择"))
        self.saved_models = QListWidget()
        self.saved_models.setMaximumHeight(115)
        self.saved_models.itemDoubleClicked.connect(self.use_saved_model)
        right.addWidget(self.saved_models)
        model_actions = QHBoxLayout()
        for label, handler in (("添加当前模型", self.add_model),
                               ("移除选中模型", self.remove_model)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            model_actions.addWidget(button)
        right.addLayout(model_actions)
        right.addWidget(QLabel("模型列表获取失败时可手填模型名，再点“添加当前模型”。"))
        row = QHBoxLayout()
        for label, handler in (("获取模型列表", self.fetch_models), ("保存配置", self.save_current),
                               ("设为当前", self.activate_current)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            row.addWidget(button)
        right.addLayout(row)
        self.status = QLabel("密钥按配置分别使用 Windows DPAPI 加密保存")
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        right.addStretch(1)
        root.addLayout(right, 3)
        self.setCentralWidget(body)
        self.refresh_profiles(select_id=client.profiles.active()["id"])

    def refresh_profiles(self, select_id: str | None = None):
        with QSignalBlocker(self.profile_list):
            self.profile_list.clear()
            active_id = self.client.profiles.active()["id"]
            for profile in self.client.profiles.profiles:
                item = QListWidgetItem(("● " if profile["id"] == active_id else "  ") + profile["name"])
                item.setData(Qt.UserRole, profile["id"])
                self.profile_list.addItem(item)
                if profile["id"] == select_id:
                    self.profile_list.setCurrentItem(item)
        self.load_selected(self.profile_list.currentItem(), None)
        self.client.profile_changed.emit()

    def load_selected(self, current, previous):
        if not current:
            return
        profile = self.client.profiles.get(current.data(Qt.UserRole))
        if not profile:
            return
        self.current_id = profile["id"]
        self.name.setText(profile["name"])
        self.mode.setCurrentIndex(1 if profile.get("mode") == "responses" else 0)
        self.base_url.setText(profile.get("base_url", ""))
        self.key.clear()
        self.key.setPlaceholderText("已保存" if self.client.profiles.secret(profile).load() else "输入密钥")
        self.model.clear()
        self.model.setEditText(profile.get("model", ""))
        self.refresh_saved_models(profile)
        self.models_url.setText(profile.get("models_url", ""))
        if self.isVisible() and profile["id"] not in self.auto_fetched and self.client.profiles.secret(profile).load():
            self.auto_fetched.add(profile["id"])
            QTimer.singleShot(100, lambda pid=profile["id"]: self.fetch_models(pid))

    def refresh_saved_models(self, profile: dict) -> None:
        self.saved_models.clear()
        for model in profile.get("models", []):
            self.saved_models.addItem(("● " if model == profile.get("model") else "  ") + model)
            self.saved_models.item(self.saved_models.count() - 1).setData(Qt.UserRole, model)

    def use_saved_model(self, item) -> None:
        self.model.setEditText(item.data(Qt.UserRole))
        self.save_current()

    def add_model(self) -> None:
        if not self.model.currentText().strip():
            self.status.setText("先选择或填写模型名")
            return
        self.save_current()

    def remove_model(self) -> None:
        item = self.saved_models.currentItem()
        if not item or not self.current_id:
            return
        if self.client.busy:
            self.status.setText("请先中断或等待当前回复")
            return
        self.client.profiles.remove_model(self.current_id, item.data(Qt.UserRole))
        profile = self.client.profiles.get(self.current_id)
        self.model.setEditText(profile.get("model", ""))
        self.refresh_saved_models(profile)
        self.client.profile_changed.emit()
        self.status.setText("已从此配置移除模型")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_profiles(self.client.profiles.active()["id"])
        profile = self.client.profiles.get(self.current_id)
        if profile and profile["id"] not in self.auto_fetched and self.client.profiles.secret(profile).load():
            self.auto_fetched.add(profile["id"])
            QTimer.singleShot(100, lambda pid=profile["id"]: self.fetch_models(pid))

    def add_profile(self):
        profile = self.client.profiles.add()
        self.refresh_profiles(profile["id"])

    def duplicate_profile(self):
        source = self.client.profiles.get(self.current_id)
        if source:
            profile = self.client.profiles.add(source)
            self.refresh_profiles(profile["id"])

    def delete_profile(self):
        if not self.current_id:
            return
        if QMessageBox.question(self, "删除模型配置", "删除当前配置及其保存的密钥？") != QMessageBox.Yes:
            return
        try:
            self.client.profiles.remove(self.current_id)
            self.client.clear_history()
            self.refresh_profiles(self.client.profiles.active()["id"])
        except ValueError as exc:
            self.status.setText(str(exc))

    def save_current(self):
        if self.client.busy:
            self.status.setText("请先中断或等待当前回复")
            return False
        try:
            profile = self.client.profiles.update(
                self.current_id, name=self.name.text(), mode=self.mode.currentData(),
                base_url=self.base_url.text(), model=self.model.currentText(),
                models_url=self.models_url.text())
            if self.key.text():
                self.client.profiles.secret(profile).save(self.key.text())
                self.key.clear()
                self.key.setPlaceholderText("已保存")
            self.client.clear_history()
            self.status.setText("配置已保存")
            self.refresh_saved_models(profile)
            self.refresh_profiles(profile["id"])
            return True
        except (ValueError, OSError) as exc:
            self.status.setText(str(exc))
            return False

    def activate_current(self):
        if self.save_current():
            try:
                self.client.activate(self.current_id)
                self.refresh_profiles(self.current_id)
                self.status.setText("已设为当前配置")
            except ValueError as exc:
                self.status.setText(str(exc))

    def fetch_models(self, requested_id=None):
        profile_id = requested_id if isinstance(requested_id, str) else self.current_id
        if not profile_id or profile_id != self.current_id:
            return
        try:
            address = self.models_url.text().strip() or api_base(self.base_url.text()) + "/models"
            if not address.startswith(("https://", "http://")):
                raise ValueError("模型列表 URL 无效")
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        profile = self.client.profiles.get(profile_id)
        key = self.key.text() or self.client.profiles.secret(profile).load()
        request = QNetworkRequest(QUrl(address))
        if key:
            request.setRawHeader(b"Authorization", ("Bearer " + key).encode("utf-8"))
        self.status.setText("正在获取模型列表…")
        reply = self.network.get(request)

        def finished():
            try:
                if self.current_id != profile_id:
                    return
                raw = bytes(reply.readAll()).decode("utf-8", "replace")
                status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                if status and int(status) >= 400:
                    raise RuntimeError(f"HTTP {status}: {raw[:200]}")
                if reply.error() != QNetworkReply.NoError:
                    raise RuntimeError(reply.errorString())
                data = json.loads(raw)
                names = sorted({str(item["id"]) for item in data.get("data", []) if item.get("id")})
                if not names:
                    raise ValueError("接口未返回模型 ID")
                selected = self.model.currentText()
                self.model.clear()
                self.model.addItems(names)
                self.model.setEditText(selected or names[0])
                self.status.setText(f"获取到 {len(names)} 个模型；选择后点击保存配置")
            except (ValueError, RuntimeError, TypeError) as exc:
                self.status.setText(f"获取失败：{exc}。可手填模型名。")
            finally:
                reply.deleteLater()

        reply.finished.connect(finished)
