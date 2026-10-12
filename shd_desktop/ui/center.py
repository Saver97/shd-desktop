"""Schedule and weather controls for the independent desktop app."""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from PySide6.QtCore import Qt, QDateTime, QSize, QSignalBlocker, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCheckBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTabWidget,
    QToolBar,
    QToolButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from shd_desktop.data.services import ScheduleStore, WeatherClient
from shd_desktop.ai.llm import LlmClient
from shd_desktop.music.music import MusicPane
from shd_desktop.ui.weather_art import weather_pixmap
from shd_desktop.integration.startup import is_enabled as startup_enabled, set_enabled as set_startup_enabled
from shd_desktop.ui.theme import current_hud, hud_section, scaled_style
from pathlib import Path

from shd_desktop.resources import ASSETS

ICON_DIR = ASSETS / "icons"


class ScheduleDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        # Windows' native item style otherwise adds another layer of row padding.
        size.setHeight(max(18, option.fontMetrics.height()) + 14)
        return size


class ForecastDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(32, option.fontMetrics.height()) + 14)
        return size


class SchedulePane(QWidget):
    changed = Signal()

    def __init__(self, events: ScheduleStore):
        super().__init__()
        self.setObjectName("SchedulePane")
        self.events = events
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(hud_section("任务日程", ICON_DIR / "fn-briefing-gen-64.png"))
        self.summary = QLabel()
        self.summary.setObjectName("ScheduleSummary")
        heading.addWidget(self.summary)
        heading.addStretch()
        self.batch_button = QPushButton("多选")
        self.batch_button.setObjectName("ScheduleBatch")
        self.batch_button.setCheckable(True)
        self.batch_button.setToolTip("进入多选模式，批量删除日程")
        self.batch_button.toggled.connect(self.set_batch_mode)
        heading.addWidget(self.batch_button)
        self.add_button = QPushButton("＋ 新增日程")
        self.add_button.setObjectName("ScheduleAdd")
        self.add_button.clicked.connect(self.open_editor)
        heading.addWidget(self.add_button)
        root.addLayout(heading)

        self.editor = QDialog(self)
        self.editor.setWindowTitle("新增日程")
        self.editor.setMinimumWidth(430)
        editor_layout = QVBoxLayout(self.editor)
        editor_layout.setContentsMargins(20, 20, 20, 20)
        editor_layout.setSpacing(16)
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.title = QLineEdit()
        self.title.setPlaceholderText("任务名称")
        form.addRow("事项", self.title)
        self.start = QDateTimeEdit()
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.start.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        form.addRow("开始", self.start)
        self.remind = QSpinBox()
        self.remind.setRange(0, 10080)
        self.remind.setValue(5)
        self.remind.setSuffix(" 分钟前")
        form.addRow("提醒", self.remind)
        editor_layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("添加日程")
        buttons.button(QDialogButtonBox.Save).setProperty("hudRole", "primary")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.add_event)
        buttons.rejected.connect(self.editor.reject)
        editor_layout.addWidget(buttons)
        self.list = QListWidget()
        self.list.setObjectName("ScheduleList")
        self.list.setIconSize(QSize(18, 18))
        self.list.setUniformItemSizes(True)
        self.list.setItemDelegate(ScheduleDelegate(self.list))
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        root.addWidget(self.list, 1)
        actions = QHBoxLayout()
        self.action_buttons = []
        for label, handler in (("完成 / 撤销", self.toggle_done), ("稍后 10 分钟", self.snooze), ("删除", self.delete)):
            button = QPushButton(label)
            button.setObjectName("ScheduleAction")
            button.clicked.connect(handler)
            actions.addWidget(button)
            self.action_buttons.append(button)
        self.batch_buttons = []
        for label, handler in (("全选", self.list.selectAll),
                               ("清空选择", self.list.clearSelection),
                               ("删除选中", self.delete_selected)):
            button = QPushButton(label)
            button.setObjectName("ScheduleAction")
            button.clicked.connect(handler)
            button.hide()
            actions.addWidget(button)
            self.batch_buttons.append(button)
        actions.addStretch()
        root.addLayout(actions)
        self.list.itemSelectionChanged.connect(self.update_actions)
        self.apply_hud()
        self.refresh()

    def apply_hud(self) -> None:
        self.setStyleSheet(scaled_style('''
            QLabel#ScheduleSummary { color: #94989F; font-size: 11px; }
            QListWidget#ScheduleList { background: transparent; border: 0;
                padding: 0; border-radius: 0; }
            QListWidget#ScheduleList::item { padding: 7px 10px;
                border-bottom: 1px solid #303238; border-left: 2px solid transparent; }
            QListWidget#ScheduleList::item:selected { background: #332B24;
                border-left: 2px solid #F48A35; color: #FFFFFF; }
            QListWidget#ScheduleList::item:hover { background: #27292D; }
            QPushButton#ScheduleAction { background: transparent;
                border: 0; padding: 5px 10px; }
            QPushButton#ScheduleAction:hover { background: #303238; color: #FFAE70; }
            QPushButton#ScheduleAction:disabled { color: #656A72; background: transparent; }
            QPushButton#ScheduleAdd { background: transparent; color: #FFAE70;
                border: 1px solid #71513A; padding: 5px 12px; }
            QPushButton#ScheduleAdd:hover { background: #3A2D23; }
            QPushButton#ScheduleBatch { background: transparent; color: #B8BDC3;
                border: 1px solid #45484D; padding: 5px 12px; }
            QPushButton#ScheduleBatch:hover, QPushButton#ScheduleBatch:checked {
                background: #3A2D23; color: #FFAE70; border-color: #71513A; }
        '''))

    def open_editor(self) -> None:
        if not self.title.text().strip():
            self.start.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        self.editor.open()
        self.title.setFocus()

    def update_actions(self) -> None:
        if self.batch_button.isChecked():
            count = len(self.list.selectedItems())
            self.batch_buttons[0].setEnabled(self.list.count() > 0)
            self.batch_buttons[1].setEnabled(count > 0)
            self.batch_buttons[2].setEnabled(count > 0)
            self.batch_buttons[2].setText(f"删除选中 ({count})" if count else "删除选中")
            return
        for button in self.action_buttons:
            button.setEnabled(self.selected_id() is not None)

    def set_batch_mode(self, enabled: bool) -> None:
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.list.setSelectionMode(QAbstractItemView.MultiSelection if enabled
                                   else QAbstractItemView.SingleSelection)
        self.batch_button.setText("退出多选" if enabled else "多选")
        for button in self.action_buttons:
            button.setVisible(not enabled)
        for button in self.batch_buttons:
            button.setVisible(enabled)
        self.update_actions()

    def add_event(self) -> None:
        try:
            self.events.add(self.title.text(), self.start.dateTime().toMSecsSinceEpoch(), self.remind.value())
        except ValueError as exc:
            QMessageBox.warning(self.editor, "日程未添加", str(exc))
            return
        self.title.clear()
        self.editor.accept()
        self.refresh()
        self.changed.emit()

    def refresh(self) -> None:
        selected = self.selected_id()
        selected_ids = ({item.data(Qt.UserRole) for item in self.list.selectedItems()}
                        if self.batch_button.isChecked() else set())
        blocker = QSignalBlocker(self.list)
        self.list.clear()
        now = int(time.time() * 1000)
        events = self.events.list()
        pending = sum(not event["done"] for event in events)
        self.summary.setText(f"{pending} 项待办  ·  共 {len(events)} 项")
        for event in events:
            stamp = datetime.fromtimestamp(event["start_ms"] / 1000).strftime("%m-%d %H:%M")
            state_icon = ("st-done" if event["done"] else
                          "st-overdue" if event["start_ms"] < now else
                          "st-reminder" if event["start_ms"] - now <= event["remind_minutes"] * 60000 else
                          "st-active")
            item = QListWidgetItem(f"{stamp}   {event['title']}")
            item.setIcon(QIcon(str(ICON_DIR / f"{state_icon}-gen-64.png")))
            item.setData(Qt.UserRole, event["id"])
            item.setToolTip(f"{stamp}  {event['title']}")
            if event["done"]:
                item.setForeground(Qt.gray)
            self.list.addItem(item)
            if event["id"] in selected_ids:
                item.setSelected(True)
            elif not self.batch_button.isChecked() and event["id"] == selected:
                self.list.setCurrentItem(item)
        del blocker
        self.update_actions()

    def selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def toggle_done(self) -> None:
        event_id = self.selected_id()
        if event_id:
            event = self.events.get(event_id)
            self.events.complete(event_id, not bool(event["done"]))
            self.refresh()
            self.changed.emit()

    def snooze(self) -> None:
        event_id = self.selected_id()
        if event_id:
            self.events.snooze(event_id)
            self.refresh()
            self.changed.emit()

    def delete(self) -> None:
        event_id = self.selected_id()
        if event_id and QMessageBox.question(self, "删除日程", "删除选中的日程？") == QMessageBox.Yes:
            self.events.delete(event_id)
            self.refresh()
            self.changed.emit()

    def delete_selected(self) -> None:
        if not self.batch_button.isChecked():
            return
        ids = [item.data(Qt.UserRole) for item in self.list.selectedItems()]
        if not ids:
            return
        if QMessageBox.question(self, "批量删除日程",
                                f"确定删除选中的 {len(ids)} 项日程？此操作无法撤销。") != QMessageBox.Yes:
            return
        self.events.delete_many(ids)
        self.refresh()
        self.changed.emit()


def weather_description(code: int) -> str:
    if code == 0:
        return "晴"
    if code in (1, 2, 3):
        return "多云"
    if code in (45, 48):
        return "雾"
    if 51 <= code <= 67:
        return "雨"
    if 71 <= code <= 77:
        return "雪"
    if 80 <= code <= 82:
        return "阵雨"
    if code >= 95:
        return "雷雨"
    return "天气变化"


class WeatherPane(QWidget):
    def __init__(self, store, client: WeatherClient):
        super().__init__()
        self.setObjectName("WeatherPane")
        self.store = store
        self.client = client
        self.saved_locations = store.data.setdefault("weather_locations", [])
        if not isinstance(self.saved_locations, list):
            self.saved_locations = []
            store.data["weather_locations"] = self.saved_locations
        if not self.saved_locations and isinstance(store.data.get("weather_location"), dict):
            location = dict(store.data["weather_location"])
            location["id"] = uuid.uuid4().hex
            self.saved_locations.append(location)
            store.data["weather_active_id"] = location["id"]
            if store.data.get("weather_cache"):
                store.data["weather_caches"] = {location["id"]: store.data["weather_cache"]}
            store.save()
        for location in self.saved_locations:
            location.setdefault("id", uuid.uuid4().hex)
        if self.saved_locations and not any(location["id"] == store.data.get("weather_active_id")
                                            for location in self.saved_locations):
            store.data["weather_active_id"] = self.saved_locations[0]["id"]
            store.save()
        store.data.setdefault("weather_caches", {})
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(hud_section("区域天气", ICON_DIR / "cat-intel-gen-64.png"))
        heading.addStretch()
        self.locations_combo = QComboBox()
        self.locations_combo.setMaximumWidth(240)
        self.locations_combo.setMinimumWidth(100)
        self.locations_combo.setToolTip("切换已保存地区")
        self.locations_combo.setPlaceholderText("选择地区")
        self.locations_combo.currentIndexChanged.connect(self.select_location)
        heading.addWidget(self.locations_combo)
        self.manage_button = QPushButton("管理地区")
        self.manage_button.setObjectName("WeatherAction")
        self.manage_button.clicked.connect(self.open_locations)
        heading.addWidget(self.manage_button)
        refresh = QPushButton("刷新")
        refresh.setObjectName("WeatherAction")
        refresh.clicked.connect(self.refresh)
        heading.addWidget(refresh)
        root.addLayout(heading)

        self.location_editor = QDialog(self)
        self.location_editor.setWindowTitle("管理天气地区")
        self.location_editor.setMinimumWidth(520)
        editor_layout = QVBoxLayout(self.location_editor)
        editor_layout.setContentsMargins(20, 20, 20, 20)
        editor_layout.setSpacing(16)
        saved_row = QHBoxLayout()
        saved_row.addWidget(QLabel("已保存地区"))
        self.manage_combo = QComboBox()
        self.manage_combo.currentIndexChanged.connect(self.locations_combo.setCurrentIndex)
        saved_row.addWidget(self.manage_combo, 1)
        remove_button = QPushButton("移除地区")
        remove_button.clicked.connect(self.remove_location)
        saved_row.addWidget(remove_button)
        editor_layout.addLayout(saved_row)
        search = QHBoxLayout()
        self.city = QLineEdit()
        self.city.setPlaceholderText("输入城市，例如 香港、上海")
        search.addWidget(self.city, 1)
        button = QPushButton("搜索并添加")
        button.setIcon(QIcon(str(ICON_DIR / "fn-search-gen-64.png")))
        button.clicked.connect(self.search_city)
        search.addWidget(button)
        self.city.returnPressed.connect(self.search_city)
        editor_layout.addLayout(search)
        self.location_status = QLabel("选择搜索结果后保存；每个地区分别保留天气缓存。")
        self.location_status.setWordWrap(True)
        editor_layout.addWidget(self.location_status)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.location_editor.reject)
        editor_layout.addWidget(buttons)
        current_row = QHBoxLayout()
        self.current_icon = QLabel()
        self.current_icon.setFixedSize(76, 76)
        self.current_icon.setPixmap(weather_pixmap(2, 70))
        current_row.addWidget(self.current_icon)
        current_text = QVBoxLayout()
        self.current_title = QLabel("尚未选择地区")
        self.current_title.setObjectName("WeatherCurrent")
        current_text.addWidget(self.current_title)
        self.current_detail = QLabel("选择地区后显示天气")
        self.current_detail.setWordWrap(True)
        current_text.addWidget(self.current_detail)
        current_row.addLayout(current_text, 1)
        root.addLayout(current_row)
        self.forecast_heading = QLabel("每日预报")
        self.forecast_heading.setObjectName("WeatherForecastTitle")
        root.addWidget(self.forecast_heading)
        self.days = QListWidget()
        self.days.setObjectName("WeatherForecast")
        self.days.setIconSize(QSize(32, 32))
        self.days.setUniformItemSizes(True)
        self.days.setItemDelegate(ForecastDelegate(self.days))
        self.days.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        root.addWidget(self.days, 1)
        self.summary = QLabel("请先设置地区")
        self.summary.setObjectName("WeatherSummary")
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignTop)
        root.addWidget(self.summary)
        client.locations.connect(self.choose_location)
        client.forecast_for.connect(self.update_forecast)
        client.error.connect(self.show_error)
        self.apply_hud()
        self.refresh_location_list()
        cached = store.data.get("weather_caches", {}).get(store.data.get("weather_active_id"))
        if cached:
            self.render(cached, cached=True)
        location = self.active_location()
        if location:
            store.data["weather_location"] = location
            self.city.setText(location["name"])

    def apply_hud(self) -> None:
        self.setStyleSheet(scaled_style('''
            QLabel#WeatherCurrent { font-size: 24px; font-weight: 400; color: #FF9D52; }
            QLabel#WeatherForecastTitle { color: #ADB1B8; font-size: 12px; padding: 4px 0; }
            QLabel#WeatherSummary { color: #9399A2; font-size: 11px; }
            QListWidget#WeatherForecast { background: transparent;
                border: 0; padding: 0; border-radius: 0; }
            QListWidget#WeatherForecast::item { padding: 7px 10px;
                border-bottom: 1px solid #303238; }
            QListWidget#WeatherForecast::item:selected { background: #332B24; color: #FFFFFF; }
            QListWidget#WeatherForecast::item:hover { background: #27292D; }
            QPushButton#WeatherAction { background: transparent; border: 0; padding: 5px 10px; }
            QPushButton#WeatherAction:hover { background: #303238; color: #FFAE70; }
        '''))

    def open_locations(self) -> None:
        self.location_editor.open()
        self.city.selectAll()
        self.city.setFocus()

    def active_location(self) -> dict | None:
        active_id = self.store.data.get("weather_active_id")
        return next((item for item in self.saved_locations if item.get("id") == active_id), None)

    def refresh_location_list(self) -> None:
        for combo in (self.locations_combo, self.manage_combo):
            with QSignalBlocker(combo):
                combo.clear()
                for location in self.saved_locations:
                    combo.addItem(location["name"], location["id"])
                    if location["id"] == self.store.data.get("weather_active_id"):
                        combo.setCurrentIndex(combo.count() - 1)

    def select_location(self, index: int) -> None:
        location_id = self.locations_combo.itemData(index) if index >= 0 else None
        location = next((item for item in self.saved_locations if item["id"] == location_id), None)
        if not location:
            return
        self.store.data["weather_active_id"] = location_id
        for combo in (self.locations_combo, self.manage_combo):
            with QSignalBlocker(combo):
                combo.setCurrentIndex(combo.findData(location_id))
        self.store.data["weather_location"] = location
        cached = self.store.data["weather_caches"].get(location_id)
        if cached:
            self.store.data["weather_cache"] = cached
            self.render(cached, cached=True)
        else:
            self.store.data.pop("weather_cache", None)
            self.current_title.setText("暂无天气数据")
            self.current_detail.setText(location["name"])
            self.days.clear()
            self.forecast_heading.setText("每日预报  ·  等待更新")
        self.city.setText(location["name"])
        self.store.save()
        self.refresh()

    def next_location(self) -> None:
        if self.locations_combo.count() > 1:
            self.locations_combo.setCurrentIndex(
                (self.locations_combo.currentIndex() + 1) % self.locations_combo.count())

    def remove_location(self) -> None:
        location = self.active_location()
        if not location:
            return
        self.saved_locations.remove(location)
        self.store.data["weather_caches"].pop(location["id"], None)
        if self.saved_locations:
            self.store.data["weather_active_id"] = self.saved_locations[0]["id"]
            self.refresh_location_list()
            self.select_location(self.locations_combo.currentIndex())
        else:
            self.store.data.pop("weather_active_id", None)
            self.store.data.pop("weather_location", None)
            self.store.data.pop("weather_cache", None)
            self.refresh_location_list()
            self.current_title.setText("尚未选择地区")
            self.current_detail.setText("选择地区后显示天气")
            self.days.clear()
            self.forecast_heading.setText("每日预报")
            self.summary.setText("请先设置地区")
            self.store.save()

    def search_city(self) -> None:
        query = self.city.text().strip()
        if query:
            self.location_status.setText("正在查找地区...")
            self.client.search(query)

    def choose_location(self, locations: list) -> None:
        if not locations:
            self.location_status.setText("没有找到该地区，请尝试加入省份或国家")
            return
        labels = [f"{x['name']} · {x.get('admin1', '')} · {x.get('country', '')}" for x in locations]
        label, accepted = QInputDialog.getItem(self.location_editor, "选择地区", "地点", labels, 0, False)
        if not accepted:
            return
        found = locations[labels.index(label)]
        selected = {
            "name": label, "latitude": found["latitude"], "longitude": found["longitude"],
            "timezone": found.get("timezone", "auto"),
        }
        existing = next((item for item in self.saved_locations
                         if item["latitude"] == selected["latitude"] and
                         item["longitude"] == selected["longitude"]), None)
        if existing:
            selected = existing
        else:
            selected["id"] = uuid.uuid4().hex
            self.saved_locations.append(selected)
        self.store.data["weather_active_id"] = selected["id"]
        self.store.data["weather_location"] = selected
        self.store.save()
        self.refresh_location_list()
        self.select_location(self.locations_combo.currentIndex())
        self.location_status.setText(f"已保存：{selected['name']}")

    def refresh(self) -> None:
        location = self.active_location()
        if not location:
            self.summary.setText("请先设置地区")
            return
        self.summary.setText("正在更新天气...")
        self.client.fetch(location["latitude"], location["longitude"], location["timezone"], location["id"])

    def update_forecast(self, location_id: str, data: dict) -> None:
        if not location_id or not any(item["id"] == location_id for item in self.saved_locations):
            return
        cache = {"fetched_at": int(time.time()), "data": data}
        self.store.data["weather_caches"][location_id] = cache
        if location_id == self.store.data.get("weather_active_id"):
            self.store.data["weather_cache"] = cache
            self.render(cache)
        self.store.save()

    def render(self, cached_data: dict, cached: bool = False) -> None:
        data = cached_data["data"]
        current = data.get("current", {})
        daily = data.get("daily", {})
        location = self.store.data.get("weather_location", {})
        stamp = datetime.fromtimestamp(cached_data["fetched_at"]).strftime("%Y-%m-%d %H:%M")
        code = current.get("weather_code", -1)
        self.current_icon.setPixmap(weather_pixmap(code, 70))
        self.current_title.setText(f"{current.get('temperature_2m', '--')} °C  ·  {weather_description(code)}")
        self.current_detail.setText(f"{location.get('name', '当前地区')}\n"
                                    f"湿度 {current.get('relative_humidity_2m', '--')}%  ·  "
                                    f"风速 {current.get('wind_speed_10m', '--')} km/h")
        self.days.clear()
        count = len(daily.get("time", []))
        self.forecast_heading.setText(f"每日预报  ·  {count} 天" if count else "每日预报  ·  暂无数据")
        def at(key, index):
            values = daily.get(key, [])
            return values[index] if index < len(values) else "--"
        for index, day in enumerate(daily.get("time", [])):
            hi, lo = at("temperature_2m_max", index), at("temperature_2m_min", index)
            rain, day_code = at("precipitation_probability_max", index), at("weather_code", index)
            item = QListWidgetItem(f"{day}   {weather_description(day_code if isinstance(day_code, int) else -1)}"
                                   f"   {lo}–{hi} °C   降水 {rain}%")
            item.setIcon(QIcon(weather_pixmap(day_code if isinstance(day_code, int) else -1, 32)))
            item.setToolTip(item.text())
            self.days.addItem(item)
        self.summary.setText(f"{'离线缓存 · ' if cached else ''}更新于 {stamp}")

    def show_error(self, error: str) -> None:
        if self.location_editor.isVisible():
            self.location_status.setText(f"地区服务请求失败：{error}")
        self.current_icon.setPixmap(QIcon(str(ICON_DIR / "fn-alert-gen-64.png")).pixmap(70, 70))
        cached = self.store.data.get("weather_cache")
        if cached:
            self.render(cached, cached=True)
            self.summary.setText(self.summary.text() + f"\n刷新失败：{error}")
        else:
            self.summary.setText(f"天气服务暂不可用：{error}")


class ControlCenter(QMainWindow):
    def __init__(self, store, events: ScheduleStore, weather: WeatherClient,
                 llm: LlmClient, on_chat, on_profiles, on_collection, on_show_panels,
                 on_undo, on_auto_organize, on_new_scene, on_switch_scene,
                 on_save_scene, on_delete_scene, on_appearance=None, on_find=None,
                 on_new_note=None, on_notes=None, notes_manager=None,
                 on_widget_visibility=None):
        super().__init__()
        self.store = store
        self.on_switch_scene = on_switch_scene
        self.on_delete_scene = on_delete_scene
        self.setWindowTitle("SHD Desktop · 控制台")
        self.setObjectName("ControlCenter")
        self.resize(840, 670)
        self.setMinimumSize(720, 580)
        toolbar = QToolBar("快捷入口")
        toolbar.setObjectName("CenterToolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(18, 18))
        brand = QLabel("SHD / DESKTOP")
        brand.setObjectName("CenterBrand")
        self.brand = brand
        self.brand_action = toolbar.addWidget(brand)

        def menu_button(label):
            button = QToolButton()
            button.setText(label)
            button.setPopupMode(QToolButton.InstantPopup)
            menu = QMenu(button)
            button.setMenu(menu)
            toolbar.addWidget(button)
            return menu

        desktop_menu = menu_button("桌面")
        desktop_menu.addAction("新建分框", on_collection)
        desktop_menu.addAction("显示分框", on_show_panels)
        desktop_menu.addSeparator()
        desktop_menu.addAction("一键按类型整理", on_auto_organize)
        desktop_menu.addAction("撤销整理", on_undo)
        if on_new_note and on_notes:
            desktop_menu.addSeparator()
            desktop_menu.addAction("新建便签", on_new_note)
            desktop_menu.addAction("管理便签", on_notes)
        toolbar.addAction(QIcon(str(ICON_DIR / "fn-isac-gen-64.png")), "ISAC", on_chat)
        if on_find:
            toolbar.addAction("快速查找", on_find)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)
        self.scene_combo = QComboBox()
        self.scene_combo.setObjectName("CenterScene")
        self.scene_combo.setMinimumWidth(90)
        self.scene_combo.setMaximumWidth(140)
        self.scene_combo.setToolTip("切换桌面场景")
        self.scene_combo.currentIndexChanged.connect(self._switch_scene)
        toolbar.addWidget(self.scene_combo)
        scene_menu = menu_button("场景")
        scene_menu.addAction("保存当前", on_save_scene)
        scene_menu.addAction("新建场景", on_new_scene)
        scene_menu.addAction("删除场景", self._delete_scene)
        settings_menu = menu_button("设置")
        settings_menu.addAction("模型配置", on_profiles)
        if on_appearance:
            settings_menu.addAction("外观与快捷键", on_appearance)
        if on_widget_visibility:
            components = settings_menu.addMenu("桌面组件")
            def refresh_components():
                components.clear()
                for kind, label in (("schedule", "日程"), ("weather", "天气"),
                                    ("music", "音乐")):
                    action = components.addAction(label)
                    action.setCheckable(True)
                    config = store.data.get("widgets", {}).get(kind, {})
                    action.setChecked(not config.get("hidden", False))
                    action.triggered.connect(
                        lambda checked=False, name=kind: on_widget_visibility(name, checked))
            components.aboutToShow.connect(refresh_components)
        settings_menu.addSeparator()
        self.autostart = QCheckBox("开机启动")
        self.autostart.setChecked(startup_enabled())
        self.autostart.toggled.connect(self.toggle_autostart)
        self.autostart.setContentsMargins(12, 6, 12, 6)
        startup_action = QWidgetAction(settings_menu)
        startup_action.setDefaultWidget(self.autostart)
        settings_menu.addAction(startup_action)
        self.addToolBar(toolbar)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("CenterTabs")
        self.schedule = SchedulePane(events)
        self.weather = WeatherPane(store, weather)
        self.music = MusicPane(store.file.parent)
        self.notes = notes_manager
        self.tabs.addTab(self.schedule, QIcon(str(ICON_DIR / "fn-briefing-gen-64.png")), "日程")
        if self.notes is not None:
            self.tabs.addTab(self.notes, QIcon(str(ICON_DIR / "fn-widgets-gen-64.png")), "便签")
        self.tabs.addTab(self.weather, QIcon(str(ICON_DIR / "cat-intel-gen-64.png")), "天气")
        self.tabs.addTab(self.music, QIcon(str(ICON_DIR / "cat-media-gen-64.png")), "音乐")
        llm.tools_changed.connect(self.schedule.refresh)
        self.setCentralWidget(self.tabs)
        self.statusBar().showMessage("● 系统就绪")
        self.apply_hud()
        self.refresh_scenes()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_toolbar_density()

    def _update_toolbar_density(self) -> None:
        if hasattr(self, "brand_action"):
            self.brand_action.setVisible(self.width() >= 800 or current_hud()["font_size"] <= 12)

    def show_notes(self) -> None:
        if self.notes is None:
            return
        self.tabs.setCurrentWidget(self.notes)
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_hud(self) -> None:
        self.setStyleSheet(scaled_style('''
            QLabel#CenterBrand { color: #F48A35; font-size: 12px; padding: 0 12px 0 2px; }
            QToolBar#CenterToolbar { background: transparent; border: 0;
                padding: 4px 12px; spacing: 6px; }
            QToolBar#CenterToolbar QToolButton { background: transparent;
                border: 0; padding: 5px 9px; }
            QToolBar#CenterToolbar QToolButton:hover { background: #303238; color: #FFAE70; }
            QComboBox#CenterScene { background: transparent; border: 0;
                border-bottom: 1px solid #484B50; padding: 4px 6px; }
            QTabWidget#CenterTabs::pane { border: 0; border-top: 1px solid #303238; }
            QTabWidget#CenterTabs QTabBar::tab { background: transparent;
                padding: 7px 20px; border: 0; border-bottom: 2px solid transparent;
                min-width: 48px; margin-right: 6px; }
            QTabWidget#CenterTabs QTabBar::tab:selected { background: transparent;
                border-bottom: 2px solid #F48A35; color: #FFFFFF; }
            QTabWidget#CenterTabs QTabBar::tab:hover { background: #27292D; }
            QMainWindow#ControlCenter QStatusBar { background: transparent;
                border: 0; color: #8F959E; }
        '''))
        self._update_toolbar_density()

    def refresh_scenes(self) -> None:
        with QSignalBlocker(self.scene_combo):
            self.scene_combo.clear()
            for scene in self.store.data.get("scenes", []):
                self.scene_combo.addItem(scene["name"], scene["id"])
            index = self.scene_combo.findData(self.store.data.get("active_scene"))
            self.scene_combo.setCurrentIndex(index)

    def _switch_scene(self, index: int) -> None:
        if index >= 0:
            self.on_switch_scene(self.scene_combo.itemData(index))

    def _delete_scene(self) -> None:
        scene_id = self.scene_combo.currentData()
        if scene_id == self.store.data.get("active_scene"):
            QMessageBox.information(self, "场景", "请先切换到其他场景，再删除此场景。")
            return
        self.on_delete_scene(scene_id)

    def toggle_autostart(self, enabled: bool) -> None:
        try:
            set_startup_enabled(enabled)
        except OSError as exc:
            with QSignalBlocker(self.autostart):
                self.autostart.setChecked(startup_enabled())
            QMessageBox.warning(self, "开机启动设置失败", str(exc))
