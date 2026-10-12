"""SHD Desktop P0: independent Windows folder panels and layout persistence."""

from __future__ import annotations

import argparse
import copy
import ctypes
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from datetime import datetime

from shd_desktop.music.music_network import bypass_music_proxy

# FFmpeg's Windows C runtime snapshots the environment when its DLL loads.
# Install music-only bypass rules before any multimedia backend is imported.
bypass_music_proxy()

from PySide6.QtCore import QFileInfo, QFileSystemWatcher, QItemSelectionModel, QMimeData, QPoint, QRect, QSize, QStandardPaths, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QCursor, QDrag, QFont, QIcon, QMouseEvent, QPainter, QPen
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFileIconProvider,
    QInputDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSizeGrip,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from shd_desktop.ui.center import ControlCenter
from shd_desktop.integration.desktop_menu import is_enabled as desktop_menu_enabled, set_enabled as set_desktop_menu_enabled
from shd_desktop.desktop.desktop_groups import DesktopGroups, path_key
from shd_desktop.desktop.desktop_groups import HIDE_BITS, file_attributes
from shd_desktop.desktop.auto_organize import TYPES, classify, icon_for_type
from shd_desktop.ai.isac_ui import ChatWindow, LlmSettingsWindow
from shd_desktop.integration.instance import claim_or_forward, receive_requests
from shd_desktop.ai.llm import LlmClient, ToolDispatcher
from shd_desktop.data.services import ScheduleStore, WeatherClient
from shd_desktop.ui.weather_art import weather_pixmap
from shd_desktop.ui.theme import STYLE, apply_hud, current_hud, hud_background, scaled_style, normalize_hud
from shd_desktop.ui.appearance import AppearanceDialog
from shd_desktop.ui.quick_find import QuickFind
from shd_desktop.integration.search_hotkey import SearchHotkey, DEFAULT_SHORTCUT
from shd_desktop.desktop.panel_layout import snap_position, snap_size
from shd_desktop.desktop.screen_recovery import visible_geometry
from shd_desktop.desktop.scenes import SceneStore
from shd_desktop.notes.notes import NotesManager
from shd_desktop.integration.startup import migrate_enabled as migrate_startup_enabled


def pointer_on_windows_desktop() -> bool:
    """Accept a manual drop only over Explorer's actual desktop view."""
    if os.name != "nt":
        return False
    import win32gui
    point = QCursor.pos()
    handle = win32gui.WindowFromPoint((point.x(), point.y()))
    while handle:
        if win32gui.GetClassName(handle) == "SHELLDLL_DefView":
            return True
        handle = win32gui.GetParent(handle)
    return False


def process_alive(pid: int) -> bool:
    if os.name != "nt":
        return False
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = (ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def confirm_auto_arrange_grouping(parent: QWidget | None = None) -> bool:
    message = ("Windows 桌面开启了“自动排列图标”。\n\n"
               "仍可继续按类型分类，文件不会被移动；关闭软件后图标会重新显示，"
               "但原来的精确排列位置可能无法恢复。\n\n是否继续？")
    return QMessageBox.question(
        parent, "自动排列已开启", message,
        QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) == QMessageBox.Yes


BASE = Path(__file__).resolve().parent
ICON = BASE / "assets" / "app.ico"
TRAY_ICON = BASE / "assets" / "tray.png"
ACCENT = "#F48A35"
ICON_DIR = BASE / "assets" / "icons"
CATEGORIES = {
    "常用": "cat-frequent-gen-64.png", "工作": "cat-logistics-gen-64.png",
    "资料": "cat-intel-gen-64.png", "媒体": "cat-media-gen-64.png",
    "网络": "cat-network-gen-64.png", "系统": "cat-system-gen-64.png",
    "游戏": "cat-combat-gen-64.png", "其他": "cat-all-gen-64.png",
}


def themed_icon(name: str) -> QIcon:
    return QIcon(str(ICON_DIR / name))


def desktop_path() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
    return Path(location) if location else Path.home() / "Desktop"


def icon_for_item(path: Path, provider: QFileIconProvider) -> QIcon:
    """Use the icon declared by a Windows Internet Shortcut when available."""
    if os.name == "nt" and path.suffix.lower() == ".url":
        buffer = ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetPrivateProfileStringW(
            "InternetShortcut", "IconFile", "", buffer, len(buffer), str(path))
        icon_path = Path(os.path.expandvars(buffer.value.strip().strip('"')))
        if icon_path.is_file():
            icon = (QIcon(str(icon_path)) if icon_path.suffix.lower() in
                    {".ico", ".png", ".jpg", ".jpeg", ".bmp"}
                    else provider.icon(QFileInfo(str(icon_path))))
            if not icon.isNull():
                return icon
    return provider.icon(QFileInfo(str(path)))


class ConfigStore:
    def __init__(self, root: Path | None = None):
        data_root = root or Path(os.getenv("LOCALAPPDATA", Path.home())) / "SHDDesktop"
        self.file = data_root / "layout.json"
        self.backup = data_root / "layout.backup.json"
        self.first_run = not self.file.exists()
        self._geometry_timer = None
        self.data = None
        for candidate in (self.file, self.backup):
            if not candidate.exists():
                continue
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("panels"), list):
                    raise ValueError("invalid layout structure")
                self.data = data
                break
            except (OSError, ValueError):
                continue
        if self.data is None:
            if self.file.exists() or self.backup.exists():
                raise OSError(f"桌面布局文件损坏，已保留原文件：{self.file}")
            self.data = {"version": 1, "panels": []}
        if self.file.exists() and "scenes" not in self.data:
            backup = self.file.with_name("layout.pre-0.5.0.json")
            if not backup.exists():
                shutil.copy2(self.file, backup)

    def save(self) -> None:
        if self._geometry_timer is not None:
            self._geometry_timer.stop()
        self.file.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(self.data, ensure_ascii=False, indent=2)
        temp = self.file.with_suffix(".tmp")
        temp.write_text(serialized, encoding="utf-8")
        temp.replace(self.file)
        try:
            backup_temp = self.backup.with_suffix(".tmp")
            backup_temp.write_text(serialized, encoding="utf-8")
            backup_temp.replace(self.backup)
        except OSError:
            pass

    def geometry_timer(self) -> QTimer:
        if self._geometry_timer is None:
            self._geometry_timer = QTimer()
            self._geometry_timer.setSingleShot(True)
            self._geometry_timer.setInterval(250)
            self._geometry_timer.timeout.connect(lambda: self.save())
        return self._geometry_timer


class Header(QLabel):
    def __init__(self, panel: "FolderPanel"):
        super().__init__(panel)
        self.panel = panel
        self._origin: QPoint | None = None
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self._origin = event.globalPosition().toPoint() - self.panel.pos()
            self.setCursor(Qt.ClosedHandCursor)
            if getattr(self.panel, "layer_callback", None):
                self.panel.layer_callback(self.panel)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None and event.buttons() & Qt.LeftButton:
            target = event.globalPosition().toPoint() - self._origin
            if hasattr(self.panel, "drag_to"):
                self.panel.drag_to(target)
            else:
                self.panel.move(target)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None:
            self._origin = None
            self.setCursor(Qt.OpenHandCursor)
            if hasattr(self.panel, "finish_move"):
                self.panel.finish_move()
            else:
                self.panel.save_geometry()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if hasattr(self.panel, "rename_panel"):
            self.panel.rename_panel()


class PanelSizeGrip(QSizeGrip):
    def __init__(self, panel: "FolderPanel"):
        super().__init__(panel)
        self.panel = panel
        self._start_cursor: QPoint | None = None
        self._start_size: QSize | None = None
        self._pending_size: QSize | None = None
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(16)
        self._resize_timer.timeout.connect(self._apply_pending_size)

    def _apply_pending_size(self) -> None:
        if self._pending_size is not None:
            size = self._pending_size
            self._pending_size = None
            self.panel.resize_to(size)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            if self.panel.layer_callback:
                self.panel.layer_callback(self.panel)
            self._resize_timer.stop()
            self._pending_size = None
            self._start_cursor = event.globalPosition().toPoint()
            self._start_size = self.panel.size()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._start_cursor is not None and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._start_cursor
            size = QSize(self._start_size.width() + delta.x(),
                         self._start_size.height() + delta.y())
            self._pending_size = size
            if not self._resize_timer.isActive():
                self._resize_timer.start()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._start_cursor is not None:
            self._resize_timer.stop()
            self._apply_pending_size()
            self._start_cursor = None
            self._start_size = None
            self.panel.finish_resize()
            event.accept()


class FolderList(QListWidget):
    def __init__(self, panel: "FolderPanel"):
        super().__init__(panel)
        self.panel = panel
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setStyleSheet(
            "QListWidget{background:transparent;border:0;color:#EAF0EF;outline:0}"
            "QListWidget::item{padding:5px;border:1px solid transparent;border-radius:0}"
            "QListWidget::item:hover{background:rgba(255,255,255,20);border-bottom-color:#F48A35}"
            "QListWidget::item:selected{background:#F48A35;border-color:#F48A35;color:#151618}"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.panel.layer_callback:
            self.panel.layer_callback(self.panel)
        super().mousePressEvent(event)

    def startDrag(self, supported_actions: Qt.DropActions) -> None:
        paths = [Path(item.data(Qt.UserRole)) for item in self.selectedItems()]
        if self.panel.is_virtual and paths:
            data = QMimeData()
            data.setData("application/x-shd-desktop-group", "\n".join(map(str, paths)).encode("utf-8"))
            drag = QDrag(self)
            drag.setMimeData(data)
            drag.exec(Qt.MoveAction)
            if pointer_on_windows_desktop():
                self.panel.drag_back_to_desktop(paths)
            return
        urls = [QUrl.fromLocalFile(str(path)) for path in paths]
        if urls:
            data = QMimeData()
            data.setUrls(urls)
            drag = QDrag(self)
            drag.setMimeData(data)
            drag.exec(Qt.CopyAction | Qt.MoveAction, Qt.MoveAction)
            if pointer_on_windows_desktop():
                QTimer.singleShot(300, lambda: self.panel.record_external_desktop_drop(paths))

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            if self.panel.receive_drop(paths, self.mapToGlobal(event.position().toPoint())):
                # Files were handled here. Never report MoveAction to the drag
                # source, which could otherwise remove them a second time.
                event.setDropAction(Qt.CopyAction)
                event.accept()
            else:
                event.ignore()
        else:
            event.ignore()


class FolderPanel(QWidget):
    def __init__(self, config: dict, store: ConfigStore, on_remove,
                 groups: DesktopGroups | None = None):
        super().__init__()
        self.config = config
        self.store = store
        self.on_remove = on_remove
        self.groups = groups
        self.is_virtual = config.get("kind") == "virtual"
        self.folder = Path(config.get("path") or (groups.roots[0] if groups else desktop_path()))
        self.group_changed_callback = None
        self.history_callback = None
        self.visibility_callback = None
        self.icon_provider = QFileIconProvider()
        self._icon_cache: dict[str, tuple[tuple[int, int], QIcon]] = {}
        self.snap_callback = None
        self.resize_callback = None
        self.layer_callback = None
        self._snap_active = False
        self._screen_relocating = False
        self._save_timer = self.store.geometry_timer()
        self._reflow_timer = QTimer(self)
        self._reflow_timer.setSingleShot(True)
        self._reflow_timer.setInterval(16)
        self._reflow_timer.timeout.connect(self._reflow_icons)
        self._last_icon_columns = None
        self.watcher = QFileSystemWatcher(self)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self.refresh)
        self.watcher.directoryChanged.connect(lambda _path: self._refresh_timer.start())
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(300, 55)
        self.setGeometry(config.get("x", 80), config.get("y", 80), config.get("w", 350), config.get("h", 420))

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 11)
        root.setSpacing(9)
        bar = QHBoxLayout()
        self.category_icon = QLabel()
        self.category_icon.setFixedSize(27, 27)
        self.category_icon.setPixmap(QPixmap(str(ICON_DIR / config.get("icon", CATEGORIES["其他"]))).scaled(
            25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        bar.addWidget(self.category_icon)
        self.header = Header(self)
        self.header.setStyleSheet("color:#F1F1F1;font-size:21px;font-weight:400")
        self.header.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.header.setToolTip("拖动时靠近其他面板会吸附；按住 Alt 可自由放置")
        bar.addWidget(self.header, 1)
        self.item_badge = QLabel("0 项")
        self.item_badge.setStyleSheet(
            "color:#F48A35;font-family:'Bahnschrift';font-size:20px;"
            "font-weight:400;padding:0 6px")
        self.item_badge.setToolTip("分框内项目数量")
        bar.addWidget(self.item_badge)
        self.manage_button = self._button("管理", self.open_panel_menu, "分框管理")
        self.manage_button.setFixedWidth(48)
        bar.addWidget(self.manage_button)
        self.collapse_button = self._button("折叠", self.toggle_collapsed, "折叠 / 展开分框")
        self.collapse_button.setFixedWidth(58)
        bar.addWidget(self.collapse_button)
        root.addLayout(bar)

        self.panel_menu = QMenu(self)
        self.view_action = self.panel_menu.addAction("切到列表", self.toggle_view)
        self.panel_menu.addAction("重命名分框", self.rename_panel)
        if not self.is_virtual:
            self.panel_menu.addAction("打开目录", lambda: os.startfile(str(self.folder)))
            self.panel_menu.addAction("更换目录", self.choose_folder)
        self.panel_menu.addSeparator()
        self.panel_menu.addAction("隐藏分框（可从托盘恢复）", self.close_panel)
        self.panel_menu.addAction("解散分框，恢复图标到桌面",
                                  lambda: self.on_remove(self.config["id"]))

        self.list = FolderList(self)
        if self.is_virtual:
            self.list.setContextMenuPolicy(Qt.CustomContextMenu)
            self.list.customContextMenuRequested.connect(self.item_menu)
        self.list.itemDoubleClicked.connect(self.open_item)
        root.addWidget(self.list, 1)

        footer = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color:#A2ABB8;font-size:10px")
        footer.addWidget(self.count_label, 1)
        self.grip = PanelSizeGrip(self)
        self.grip.setToolTip("拖动调整大小时靠近其他面板会吸附；按住 Alt 可自由缩放")
        footer.addWidget(self.grip)
        root.addLayout(footer)

        self.apply_hud()
        self.refresh()
        self.apply_collapsed()

    def _button(self, label: str, callback, tooltip: str) -> QPushButton:
        button = QPushButton(label)
        button.setToolTip(tooltip)
        button.setFixedHeight(29)
        button.setStyleSheet(
            "QPushButton{border:0;border-bottom:1px solid rgba(255,255,255,65);"
            "background:rgba(255,255,255,14);color:#E8EEEC;"
            "border-radius:0;padding:3px 5px;font-size:11px;font-weight:400}"
            "QPushButton:hover{background:#F48A35;border-color:#F48A35;color:#17191D}"
            "QPushButton:pressed{background:#CF6F26;color:#17191D}"
        )
        button.clicked.connect(callback)
        return button

    def open_panel_menu(self) -> None:
        self.panel_menu.exec(self.manage_button.mapToGlobal(QPoint(0, self.manage_button.height())))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        bounds = self.rect().adjusted(1, 1, -2, -2)
        painter.fillRect(bounds, hud_background())
        painter.fillRect(1, 12, 3, 29, QColor(244, 138, 53))
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.drawLine(14, 53, self.width() - 14, 53)
        if not self.config.get("collapsed"):
            painter.setPen(QPen(QColor(151, 159, 172, 38), 1))
            painter.drawLine(13, self.height() - 29, self.width() - 13, self.height() - 29)
        if self._snap_active:
            painter.setPen(QPen(QColor(244, 138, 53), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(bounds)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self.save_geometry(deferred=True)
            if hasattr(self, "list") and not self._reflow_timer.isActive():
                self._reflow_timer.start()

    def _reflow_icons(self, force: bool = False) -> None:
        if not hasattr(self, "list") or self.config.get("collapsed"):
            return
        if self.config.get("view", "grid") != "grid":
            if force:
                self.list.doItemsLayout()
            return
        cell_width = max(1, self.list.gridSize().width())
        columns = max(1, self.list.viewport().width() // cell_width)
        if force or columns != self._last_icon_columns:
            self.list.doItemsLayout()
            self._last_icon_columns = max(1, self.list.viewport().width() // cell_width)

    def save_geometry(self, deferred: bool = False) -> None:
        if self._screen_relocating:
            return
        g = self.geometry()
        self.config.update(x=g.x(), y=g.y(), w=g.width(), h=g.height())
        if not self.config.get("collapsed"):
            self.config["expanded_h"] = g.height()
        if deferred:
            self._save_timer.start()
        else:
            self._save_timer.stop()
            self.store.save()

    def drag_to(self, raw_position: QPoint) -> None:
        free_move = bool(QApplication.keyboardModifiers() & Qt.AltModifier)
        target = (self.snap_callback(self, raw_position)
                  if self.snap_callback and not free_move else raw_position)
        snapped = target != raw_position
        if snapped != self._snap_active:
            self._snap_active = snapped
            self.update()
        self.move(target)

    def finish_move(self) -> None:
        if self._snap_active:
            self._snap_active = False
            self.update()
        self.save_geometry()
        if self.layer_callback:
            self.layer_callback(self)

    def resize_to(self, raw_size: QSize) -> None:
        raw_size = raw_size.expandedTo(self.minimumSize())
        free_resize = bool(QApplication.keyboardModifiers() & Qt.AltModifier)
        target = (self.resize_callback(self, raw_size)
                  if self.resize_callback and not free_resize else raw_size)
        snapped = target != raw_size
        if snapped != self._snap_active:
            self._snap_active = snapped
            self.update()
        self.resize(target)

    def finish_resize(self) -> None:
        if self._snap_active:
            self._snap_active = False
            self.update()
        self.save_geometry()
        self._reflow_timer.stop()
        QTimer.singleShot(0, lambda: self._reflow_icons(force=True))
        if self.layer_callback:
            self.layer_callback(self)

    def apply_collapsed(self) -> None:
        collapsed = bool(self.config.get("collapsed"))
        content = (self.list, self.count_label, self.grip)
        self.setUpdatesEnabled(False)
        try:
            if collapsed:
                for widget in content:
                    widget.hide()
                self.setFixedHeight(55)
            else:
                desired_height = max(210, int(self.config.get("expanded_h", 420)))
                self.setMaximumHeight(16777215)
                self.resize(self.width(), desired_height)
                self.setMinimumHeight(210)
                for widget in content:
                    widget.show()
            self.collapse_button.setText("展开" if collapsed else "折叠")
        finally:
            self.setUpdatesEnabled(True)
        if self.isVisible() and not self.layer_callback:
            self.lower() if collapsed else self.raise_()

    def toggle_collapsed(self) -> None:
        if not self.config.get("collapsed"):
            self.config["expanded_h"] = self.height()
        self.config["collapsed"] = not bool(self.config.get("collapsed"))
        self.apply_collapsed()
        self.save_geometry(deferred=True)
        if self.layer_callback:
            self.layer_callback(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self.layer_callback:
            self.layer_callback(self)
        super().mousePressEvent(event)

    def rename_panel(self) -> None:
        title, accepted = QInputDialog.getText(self, "分框名称", "名称", text=self.header.text())
        if accepted and title.strip():
            self.config["title"] = title.strip()
            self.store.save()
            self.refresh()

    def apply_view(self) -> None:
        grid = self.config.get("view", "grid") == "grid"
        self._last_icon_columns = None
        self.view_action.setText("切到列表" if grid else "切到图标")
        self.list.setViewMode(QListView.IconMode if grid else QListView.ListMode)
        icon = current_hud()["icon_size"]
        scale = current_hud()["font_size"] / 12
        self.list.setIconSize(self._size(icon if grid else round(icon * .6)))
        self.list.setGridSize(self._size(icon + round(56 * scale), icon + round(42 * scale))
                              if grid else self._size(0, max(round(34 * scale), round(icon * .6) + 10)))
        self.list.setWordWrap(grid)
        self.list.setWrapping(grid)

    def apply_hud(self) -> None:
        scale = current_hud()["font_size"] / 12
        self.header.setStyleSheet(f"color:#F1F1F1;font-size:{min(24, round(21 * scale))}px;font-weight:400")
        self.item_badge.setStyleSheet(f"color:#F48A35;font-family:'Bahnschrift';font-size:{min(24, round(20 * scale))}px;padding:0 6px")
        self.count_label.setStyleSheet(scaled_style("color:#A2ABB8;font-size:10px"))
        for button in (self.manage_button, self.collapse_button):
            button.setStyleSheet(scaled_style(
                "QPushButton{border:0;border-bottom:1px solid rgba(255,255,255,65);"
                "background:rgba(255,255,255,14);color:#E8EEEC;padding:3px 5px;font-size:11px}"
                "QPushButton:hover{background:#F48A35;color:#17191D}"))
        self.apply_view()
        self._reflow_icons(force=True)
        self.update()

    @staticmethod
    def _size(w: int, h: int | None = None):
        from PySide6.QtCore import QSize
        return QSize(w, h if h is not None else w)

    def toggle_view(self) -> None:
        self.config["view"] = "list" if self.config.get("view", "grid") == "grid" else "grid"
        self.apply_view()
        self.store.save()

    def choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "选择面板目录", str(self.folder))
        if chosen:
            self.folder = Path(chosen)
            self.config["path"] = str(self.folder)
            self.store.save()
            self.refresh()

    def refresh(self) -> None:
        self._refresh_timer.stop()
        selected_paths = {item.data(Qt.UserRole) for item in self.list.selectedItems()}
        current_path = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.header.setText(self.config.get("title") or self.folder.name or "桌面")
        description = "桌面整理 · 文件保持原位" if self.is_virtual else str(self.folder)
        self.manage_button.setToolTip(description + "\n切换视图、目录及分框管理")
        watched = self.watcher.directories()
        wanted = str(self.folder) if self.folder.is_dir() else None
        if watched and (wanted is None or watched != [wanted]):
            self.watcher.removePaths(watched)
        self.list.setUpdatesEnabled(False)
        try:
            self.list.clear()
            if wanted is None:
                self.count_label.setText("目录不可用 · 点击管理重新选择")
                return
            if not watched or watched != [wanted]:
                self.watcher.addPath(wanted)
            try:
                if self.is_virtual:
                    paths = [Path(record["path"]) for record in self.groups.records(self.config)
                             if isinstance(record, dict) and record.get("path") and Path(record["path"]).exists()]
                else:
                    grouped = self.groups.grouped_keys() if self.groups else set()
                    paths = [path for path in self.folder.iterdir() if path_key(path) not in grouped]
                paths.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))
            except OSError as exc:
                self.count_label.setText(f"无法读取：{exc}")
                return
            shown = set()
            for path in paths:
                if path.name.startswith("."):
                    continue
                key = path_key(path)
                shown.add(key)
                label = path.stem if path.suffix.casefold() in {".lnk", ".url"} else path.name
                item = QListWidgetItem(self._cached_icon(path, key), label)
                item.setData(Qt.UserRole, str(path))
                item.setToolTip(str(path))
                self.list.addItem(item)
                if str(path) == current_path:
                    self.list.setCurrentItem(item, QItemSelectionModel.NoUpdate)
                if str(path) in selected_paths:
                    item.setSelected(True)
            self._icon_cache = {key: value for key, value in self._icon_cache.items() if key in shown}
            action_hint = "双击打开 · 右键移出" if self.is_virtual else "双击打开 · 拖放整理"
            mode = "桌面整理" if self.is_virtual else "文件夹分框"
            self.count_label.setText(f"{mode}  /  {action_hint}")
        finally:
            self.item_badge.setText(str(self.list.count()).zfill(2))
            self.list.setUpdatesEnabled(True)

    def _cached_icon(self, path: Path, key: str) -> QIcon:
        try:
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            signature = None
        cached = self._icon_cache.get(key)
        if signature is not None and cached and cached[0] == signature:
            return cached[1]
        source = icon_for_item(path, self.icon_provider)
        # QFileIconProvider returns a lazy shell engine. Retaining that QIcon
        # still queries Windows during every paint; keep only rendered pixmaps.
        icon = QIcon()
        dpi = max((screen.devicePixelRatio() for screen in QApplication.screens()), default=1)
        size = max(80, round(64 * dpi))
        pixmap = source.pixmap(size, size)
        if not pixmap.isNull():
            icon.addPixmap(pixmap)
            for logical_size in (24, 40):
                icon.addPixmap(pixmap.scaled(logical_size, logical_size,
                                            Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if signature is not None:
            self._icon_cache[key] = (signature, icon)
        return icon

    def open_item(self, item: QListWidgetItem) -> None:
        path = Path(item.data(Qt.UserRole))
        if path.exists():
            os.startfile(str(path))

    def item_menu(self, position: QPoint) -> None:
        item = self.list.itemAt(position)
        if not item or not self.is_virtual:
            return
        menu = QMenu(self)
        restore = menu.addAction("移出分框，恢复桌面图标")
        if menu.exec(self.list.mapToGlobal(position)) == restore:
            try:
                path = Path(item.data(Qt.UserRole))
                self.groups.remove(self.config, path)
                if self.history_callback:
                    self.history_callback({"kind": "group", "items": [{"path": str(path), "owner": self.config["id"]}]})
            except OSError as exc:
                QMessageBox.warning(self, "无法恢复图标", str(exc))
                return
            if self.group_changed_callback:
                self.group_changed_callback()

    def receive_drop(self, paths: list[Path], position: QPoint) -> bool:
        if self.is_virtual:
            before = {path_key(path): self.groups.owner_id(path) for path in paths}
            added, errors = self.groups.add(self.config, paths)
            if not added and any("自动排列" in error for error in errors):
                if confirm_auto_arrange_grouping(self):
                    added, errors = self.groups.add(
                        self.config, paths, snapshot={}, allow_unpositioned=True)
                else:
                    return False
            changed = [{"path": str(path), "owner": before[path_key(path)]} for path in paths
                       if path.name in added and before[path_key(path)] != self.config["id"]]
            if changed and self.history_callback:
                self.history_callback({"kind": "group", "items": changed})
            if self.group_changed_callback:
                self.group_changed_callback()
            if errors:
                QMessageBox.warning(self, "部分图标未整理", "\n".join(errors))
            return bool(added)
        if not self.folder.is_dir():
            return False
        skipped, errors = self.apply_drop(paths, move=True)
        return len(skipped) + len(errors) < len(paths)

    def drag_back_to_desktop(self, paths: list[Path]) -> None:
        changed, errors = [], []
        for path in paths:
            try:
                if self.groups.remove(self.config, path):
                    changed.append({"path": str(path), "owner": self.config["id"]})
            except OSError as exc:
                errors.append(f"{path.name}：{exc}")
        if changed and self.history_callback:
            self.history_callback({"kind": "group", "items": changed})
        if self.group_changed_callback:
            self.group_changed_callback()
        if errors:
            QMessageBox.warning(self, "部分图标未恢复", "\n".join(errors))

    def record_external_desktop_drop(self, paths: list[Path]) -> None:
        if self.is_virtual:
            return
        desktop = self.groups.roots[0]
        moved = [{"from": str(path), "to": str(desktop / path.name)} for path in paths
                 if not path.exists() and (desktop / path.name).exists()]
        if moved and self.history_callback:
            self.history_callback({"kind": "move", "items": moved})
        self.refresh()

    def apply_drop(self, paths: list[Path], move: bool) -> tuple[list[str], list[str]]:
        skipped = []
        errors = []
        positions_changed = False
        moved = []
        for source in paths:
            destination = self.folder / source.name
            if (not source.exists() or destination.exists() or source.parent == self.folder
                    or (source.is_dir() and destination.resolve().is_relative_to(source.resolve()))):
                skipped.append(source.name)
                continue
            try:
                original_position = None
                if move and self.groups and self.groups.is_desktop_item(source):
                    try:
                        original_position = self.groups.positions.get(source)
                    except (OSError, ValueError):
                        pass
                if move:
                    shutil.move(str(source), str(destination))
                    moved.append({"from": str(source), "to": str(destination)})
                    if original_position is not None:
                        self.config.setdefault("desktop_positions", {})[destination.name] = original_position
                        positions_changed = True
                elif source.is_dir():
                    shutil.copytree(source, destination)
                else:
                    shutil.copy2(source, destination)
            except OSError as exc:
                errors.append(f"{source.name}: {exc}")
        if positions_changed:
            self.store.save()
        if moved and self.history_callback:
            self.history_callback({"kind": "move", "items": moved})
        self.refresh()
        if skipped or errors:
            QMessageBox.warning(self, "部分条目未处理", "已跳过：" + ", ".join(skipped) + "\n" + "\n".join(errors))
        return skipped, errors

    def close_panel(self) -> None:
        self.config["hidden"] = True
        self.store.save()
        self.hide()
        if self.visibility_callback:
            self.visibility_callback()


class StatusPanel(QWidget):
    """Small movable desktop face for a control-center feature."""

    def __init__(self, kind: str, controller: "Controller", y: int):
        super().__init__()
        self.kind = kind
        self.controller = controller
        self.store = controller.store
        self._screen_relocating = False
        self._save_timer = self.store.geometry_timer()
        self.config = self.store.data.setdefault("widgets", {}).setdefault(
            kind, {"x": 470, "y": y, "w": 310, "h": 180})
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(260, 130)
        self.setGeometry(self.config["x"], self.config["y"], self.config["w"], self.config["h"])
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        self.header = Header(self)
        self.header.setText({"schedule": "日程  //  SCHEDULE", "weather": "天气  //  WEATHER",
                             "music": "音乐  //  QQ MUSIC"}[kind])
        self.header.setStyleSheet("color:#F1F1F1;font-size:16px;font-weight:400")
        root.addWidget(self.header)
        self.content = QLabel()
        self.content.setWordWrap(True)
        self.content.setAlignment(Qt.AlignTop)
        self.content.setStyleSheet("color:#E8E6E3;font-size:12px")
        content_row = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(58, 58)
        content_row.addWidget(self.icon_label)
        content_row.addWidget(self.content, 1)
        root.addLayout(content_row, 1)
        actions = QHBoxLayout()
        open_button = QPushButton("打开")
        open_button.clicked.connect(self.open_feature)
        actions.addWidget(open_button)
        if kind == "weather":
            switch = QPushButton("切换地区")
            switch.clicked.connect(self.switch_weather)
            actions.addWidget(switch)
        if kind == "music":
            play = QPushButton("播放 / 暂停")
            play.clicked.connect(controller.center.music.toggle_play)
            actions.addWidget(play)
            next_button = QPushButton("下一首")
            next_button.clicked.connect(controller.center.music.next_song)
            actions.addWidget(next_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.refresh()

    def switch_weather(self) -> None:
        self.controller.center.weather.next_location()
        self.refresh()

    def apply_hud(self) -> None:
        self.header.setStyleSheet(scaled_style("color:#F1F1F1;font-size:16px;font-weight:400"))
        self.content.setStyleSheet(scaled_style("color:#E8E6E3;font-size:12px"))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect().adjusted(1, 1, -2, -2), hud_background())
        painter.fillRect(1, 12, 3, 23, QColor(244, 138, 53))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self.save_geometry(deferred=True)

    def save_geometry(self, deferred: bool = False) -> None:
        if self._screen_relocating:
            return
        g = self.geometry()
        self.config.update(x=g.x(), y=g.y(), w=g.width(), h=g.height())
        if deferred:
            self._save_timer.start()
        else:
            self._save_timer.stop()
            self.store.save()

    def open_feature(self) -> None:
        pane = {"schedule": self.controller.center.schedule,
                "weather": self.controller.center.weather,
                "music": self.controller.center.music}[self.kind]
        self.controller.center.centralWidget().setCurrentWidget(pane)
        self.controller.open_center()

    def refresh(self) -> None:
        if self.kind == "schedule":
            future = [x for x in self.controller.events.list() if not x["done"]]
            future.sort(key=lambda x: x["start_ms"])
            lines = [f"{datetime.fromtimestamp(x['start_ms']/1000):%m-%d %H:%M}  {x['title']}"
                     for x in future[:3]]
            self.content.setText("\n".join(lines) if lines else "暂无待办日程")
            self.icon_label.setPixmap(themed_icon("fn-clock-gen-64.png").pixmap(54, 54))
        elif self.kind == "weather":
            cached = self.store.data.get("weather_cache")
            location = self.store.data.get("weather_location", {})
            if cached:
                current = cached["data"].get("current", {})
                self.icon_label.setPixmap(weather_pixmap(current.get("weather_code", -1), 54))
                self.content.setText(f"{location.get('name', '当前地区')}\n"
                    f"{current.get('temperature_2m', '--')} °C  ·  "
                    f"{current.get('relative_humidity_2m', '--')}% 湿度\n"
                    f"更新于 {datetime.fromtimestamp(cached['fetched_at']):%m-%d %H:%M}")
            else:
                self.icon_label.setPixmap(weather_pixmap(2, 54))
                self.content.setText("尚未设置地区；点击打开选择")
        else:
            self.icon_label.setPixmap(themed_icon("cat-media-gen-64.png").pixmap(54, 54))
            song = self.controller.center.music.current_song
            self.content.setText(f"{song['title']}\n{song['artist']}" if song else "尚未选择歌曲")


class IsacLauncher(QWidget):
    def __init__(self, controller: "Controller"):
        super().__init__()
        self.controller = controller
        self.config = controller.store.data.setdefault("isac_launcher", {"x": 850, "y": 80})
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(66, 66)
        self.move(self.config.get("x", 850), self.config.get("y", 80))
        self.origin = None
        self.was_dragged = False
        self.setToolTip("点击打开 ISAC；拖动调整入口位置")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(20, 27, 33, 238))
        painter.setPen(QPen(QColor(255, 132, 38), 2))
        painter.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        pixmap = themed_icon("fn-isac-gen-64.png").pixmap(43, 43)
        painter.drawPixmap(11, 11, pixmap)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.origin = event.globalPosition().toPoint() - self.pos()
            self.was_dragged = False

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.origin is not None and event.buttons() & Qt.LeftButton:
            self.was_dragged = True
            self.move(event.globalPosition().toPoint() - self.origin)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.origin is not None:
            self.origin = None
            self.config.update(x=self.x(), y=self.y())
            self.controller.store.save()
            if not self.was_dragged:
                self.controller.open_chat()


class Controller:
    def __init__(self, app: QApplication, store: ConfigStore,
                 desktop_roots: list[Path] | None = None, enable_hotkeys: bool = True):
        self.app = app
        self.store = store
        apply_hud(app, normalize_hud(store.data.get("hud")))
        self.scenes = SceneStore(store)
        self._history = store.data.setdefault("undo_history", [])
        roots = desktop_roots or [desktop_path(), Path(os.getenv("PUBLIC", "C:/Users/Public")) / "Desktop"]
        self.groups = DesktopGroups(store, roots)
        self.events = ScheduleStore(store.file.parent / "state.db")
        self.weather = WeatherClient(app)
        self.panels: dict[str, FolderPanel] = {}
        self._front_panel_id: str | None = None
        app.setQuitOnLastWindowClosed(False)
        app.aboutToQuit.connect(store.save)
        self._exit_restore_ok = False
        app.aboutToQuit.connect(self._restore_on_exit)
        self._session_file = store.file.parent / f"session-{os.getpid()}.running"
        stale = []
        for marker in store.file.parent.glob("session-*.running"):
            try:
                pid = int(marker.stem.split("-")[1])
            except (IndexError, ValueError):
                pid = 0
            if pid != os.getpid() and not process_alive(pid):
                stale.append(marker)
        if stale:
            stale_errors = self.groups.restore_for_exit(force_positions=True)
            if not stale_errors:
                for marker in stale:
                    try:
                        marker.unlink()
                    except OSError:
                        pass
        else:
            stale_errors = []
        self._session_file.write_text(str(os.getpid()), encoding="ascii")
        app.aboutToQuit.connect(self._clear_session)
        group_errors = stale_errors + self.groups.reapply_on_start()
        for config in store.data["panels"]:
            if (isinstance(config, dict) and config.get("id")
                    and (config.get("path") or config.get("kind") == "virtual")):
                self._show_panel(config)
        if not self.panels and store.first_run:
            self.add_folder(desktop_path())
        self.restack_panels()
        self.tray = QSystemTrayIcon(QIcon(str(TRAY_ICON)), app)
        self.tray_menu = QMenu()
        self.tray_menu.aboutToShow.connect(self.populate_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()
        if getattr(sys, "frozen", False) and "--smoke" not in sys.argv:
            try:
                set_desktop_menu_enabled(bool(store.data.setdefault("desktop_menu_enabled", True)))
            except OSError as exc:
                self.tray.showMessage("桌面右键入口", str(exc), QSystemTrayIcon.Warning, 8000)
        if group_errors:
            self.tray.showMessage("桌面图标恢复", "\n".join(group_errors[:3]),
                                  QSystemTrayIcon.Warning, 8000)
        self.notes = NotesManager(store.file.parent, self.events, self.tray)
        app.aboutToQuit.connect(self.notes.flush)
        dispatcher = ToolDispatcher(self.events, store, self.panels)
        dispatcher.notes = self.notes
        self.llm = LlmClient(store, dispatcher, app)
        self.settings = LlmSettingsWindow(self.llm)
        self.chat = ChatWindow(store, self.llm, self.open_profiles)
        self.center = ControlCenter(store, self.events, self.weather, self.llm,
                                    self.open_chat, self.open_profiles,
                                    self.add_collection, self.show_all,
                                    self.undo_last, self.auto_organize,
                                    self.create_scene, self.switch_scene,
                                    self.save_scene, self.delete_scene,
                                    self.open_appearance, self.open_search,
                                    self.notes.new_note, self.notes.show_manager, self.notes,
                                    self.set_widget_visible)
        self.notes.present_in_center = self.center.show_notes
        self.search_window = QuickFind(self)
        self.search_hotkey = SearchHotkey(app, self.open_search)
        self.appearance_window = None
        shortcut = store.data.get("search", {})
        if enable_hotkeys:
            try:
                self.search_hotkey.configure(bool(shortcut.get("enabled", True)),
                                             shortcut.get("shortcut", DEFAULT_SHORTCUT))
            except ValueError as exc:
                self.tray.showMessage("快速查找快捷键", str(exc), QSystemTrayIcon.Warning, 5000)
        app.aboutToQuit.connect(self.center.music.persist)
        dispatcher.music = self.center.music
        self.widgets = {
            "schedule": StatusPanel("schedule", self, 80),
            "weather": StatusPanel("weather", self, 290),
            "music": StatusPanel("music", self, 500),
        }
        for widget in self.widgets.values():
            widget.apply_hud()
            if not widget.config.get("hidden"):
                widget.show()
        self.isac_launcher = IsacLauncher(self)
        if not self.isac_launcher.config.get("hidden"):
            self.isac_launcher.show()
        self.weather.forecast.connect(lambda _: self.widgets["weather"].refresh())
        self.llm.tools_changed.connect(self.refresh_widgets)
        self.center.schedule.changed.connect(lambda: self.widgets["schedule"].refresh())
        self.center.music.player.mediaStatusChanged.connect(lambda _: self.widgets["music"].refresh())
        self.tray.messageClicked.connect(self.open_center)
        self.reminder_timer = QTimer(app)
        self.reminder_timer.setInterval(30000)
        self.reminder_timer.timeout.connect(self.scan_reminders)
        self.reminder_timer.start()
        self.scan_reminders()
        self._screen_change_timer = QTimer(app)
        self._screen_change_timer.setSingleShot(True)
        self._screen_change_timer.setInterval(250)
        self._screen_change_timer.timeout.connect(self._recover_window_positions)
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(lambda _screen: self._prepare_screen_change())
        for screen in app.screens():
            self._screen_added(screen)
        QTimer.singleShot(0, self._recover_window_positions)
        token_reader = getattr(self.groups.positions, "view_token", None)
        self._shell_token = token_reader() if token_reader else None
        self._shell_timer = QTimer(app)
        self._shell_timer.setInterval(2000)
        self._shell_timer.timeout.connect(self._check_explorer)
        self._shell_timer.start()

    def _restore_on_exit(self) -> None:
        errors = self.groups.restore_for_exit()
        self._exit_restore_ok = not errors
        if errors:
            try:
                log = self.store.file.parent / "recovery.log"
                with log.open("a", encoding="utf-8") as output:
                    output.write("\n".join(errors) + "\n")
            except OSError:
                pass

    def _screen_added(self, screen) -> None:
        screen.geometryChanged.connect(lambda _geometry: self._prepare_screen_change())
        screen.availableGeometryChanged.connect(lambda _geometry: self._prepare_screen_change())
        screen.logicalDotsPerInchChanged.connect(lambda _dpi: self._prepare_screen_change())
        self._prepare_screen_change()

    def _prepare_screen_change(self) -> None:
        # Qt can relocate windows while removing a screen. That temporary
        # geometry must not replace the user's saved multi-monitor layout.
        for window in (*self.panels.values(), *self.widgets.values()):
            window._save_timer.stop()
            window._screen_relocating = True
        for window in self.notes.windows.values():
            if window._save_timer.isActive():
                window._save_timer.stop()
                window.save_text()
            window._screen_relocating = True
        self._screen_change_timer.start()

    def _recover_window_positions(self) -> None:
        screens = [screen.availableGeometry() for screen in self.app.screens()]
        self._place_windows(screens)

    def _place_windows(self, screens: list[QRect]) -> None:
        for window in (*self.panels.values(), *self.widgets.values()):
            config = window.config
            saved = QRect(config.get("x", window.x()), config.get("y", window.y()),
                          config.get("w", window.width()), config.get("h", window.height()))
            target = visible_geometry(saved, screens)
            try:
                if target != window.geometry():
                    window.setGeometry(target)
            finally:
                window._screen_relocating = False
        for window in self.notes.windows.values():
            note = window.note
            saved = QRect(note.get("x", window.x()), note.get("y", window.y()),
                          note.get("w", window.width()), note.get("h", window.height()))
            target = visible_geometry(saved, screens)
            try:
                if target != window.geometry():
                    window.setGeometry(target)
            finally:
                window._screen_relocating = False
        launcher = self.isac_launcher
        position = visible_geometry(QRect(launcher.config.get("x", launcher.x()),
                                          launcher.config.get("y", launcher.y()), 66, 66), screens)
        if launcher.pos() != position.topLeft():
            launcher.move(position.topLeft())

    def _check_explorer(self) -> None:
        token_reader = getattr(self.groups.positions, "view_token", None)
        token = token_reader() if token_reader else None
        if token is None or token == self._shell_token:
            return
        self._shell_token = token
        errors = self.groups.sync_visibility(recapture=False)
        try:
            self.groups.positions.refresh()
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
        self.restack_panels()
        if errors:
            self.tray.showMessage("桌面恢复", "\n".join(errors[:3]),
                                  QSystemTrayIcon.Warning, 8000)

    def _show_panel(self, config: dict) -> None:
        panel = FolderPanel(config, self.store, self.remove_panel, self.groups)
        panel.snap_callback = self.snap_panel
        panel.resize_callback = self.snap_resize
        panel.layer_callback = self.restack_panels
        panel.group_changed_callback = self.refresh_panels
        panel.history_callback = self.record_action
        panel.visibility_callback = self.sync_group_visibility
        self.panels[config["id"]] = panel
        if not config.get("hidden"):
            panel.show()

    def restack_panels(self, active: FolderPanel | None = None) -> None:
        if (active is not None and active.isVisible()
                and self.panels.get(active.config["id"]) is active):
            self._front_panel_id = active.config["id"]
        expanded = [panel for panel in self.panels.values()
                    if panel.isVisible() and not panel.config.get("collapsed")]
        collapsed = [panel for panel in self.panels.values()
                     if panel.isVisible() and panel.config.get("collapsed")]
        for group in (expanded, collapsed):
            group.sort(key=lambda panel: panel.config["id"] != self._front_panel_id)
        # Qt's raise_() does not reorder WindowStaysOnBottomHint windows on
        # Windows. Lower from desired front to back: the first panel stays in
        # front of the other SHD panels, while the whole set stays on desktop.
        for panel in (*expanded, *collapsed):
            panel.lower()

    def snap_panel(self, panel: FolderPanel, raw_position: QPoint) -> QPoint:
        peers = [other.geometry() for other in self.panels.values()
                 if other is not panel and other.isVisible()]
        peers.extend(widget.geometry() for widget in getattr(self, "widgets", {}).values()
                     if widget.isVisible())
        raw_rect = QRect(raw_position, panel.size())
        return snap_position(raw_rect, peers, threshold=16)

    def snap_resize(self, panel: FolderPanel, raw_size: QSize) -> QSize:
        peers = [other.geometry() for other in self.panels.values()
                 if other is not panel and other.isVisible()]
        peers.extend(widget.geometry() for widget in getattr(self, "widgets", {}).values()
                     if widget.isVisible())
        raw_rect = QRect(panel.pos(), raw_size)
        return snap_size(raw_rect, peers, panel.minimumSize())

    def add_folder(self, path: Path, title: str | None = None, icon: str | None = None) -> None:
        index = len(self.panels)
        config = {"id": uuid.uuid4().hex, "kind": "folder", "path": str(path),
                  "title": title or path.name,
                  "icon": icon or CATEGORIES["其他"], "view": "grid", "collapsed": False,
                  "x": 80 + 380 * (index % 3), "y": 80 + 330 * (index // 3),
                  "w": 350, "h": 300, "expanded_h": 300}
        self.store.data["panels"].append(config)
        self.store.save()
        self._show_panel(config)
        self.restack_panels()

    def add_virtual(self, title: str, icon: str | None = None) -> dict:
        index = len(self.panels)
        screen = self.app.primaryScreen()
        bounds = screen.availableGeometry() if screen else QRect(0, 0, 1600, 900)
        occupied = [panel.geometry().adjusted(-8, -8, 8, 8)
                    for panel in self.panels.values() if panel.isVisible()]
        position = None
        for y in range(bounds.top() + 55, max(bounds.top() + 56, bounds.bottom() - 299), 320):
            for x in range(bounds.left() + 20, max(bounds.left() + 21, bounds.right() - 349), 370):
                candidate = QRect(x, y, 350, 300)
                if not any(candidate.intersects(rect) for rect in occupied):
                    position = (x, y)
                    break
            if position:
                break
        if position is None:
            position = (bounds.left() + 30 + 32 * (index % 5),
                        bounds.top() + 60 + 32 * (index % 5))
        config = {"id": uuid.uuid4().hex, "kind": "virtual", "title": title,
                  "icon": icon or CATEGORIES["其他"], "items": [], "view": "grid",
                  "collapsed": False, "x": position[0],
                  "y": position[1], "w": 350, "h": 300,
                  "expanded_h": 300}
        self.store.data["panels"].append(config)
        self.store.save()
        self._show_panel(config)
        self.restack_panels()
        return config

    def refresh_panels(self) -> None:
        for panel in self.panels.values():
            panel.refresh()

    def auto_organize(self) -> None:
        """Place ungrouped desktop entries into virtual panels by file type."""
        buckets = {name: [] for name, _, _ in TYPES}
        scan_errors = []
        for root in self.groups.roots:
            if not root.is_dir():
                continue
            try:
                paths = list(root.iterdir())
            except OSError as exc:
                scan_errors.append(f"{root}：{exc}")
                continue
            for path in paths:
                if path.name.casefold() == "desktop.ini" or self.groups.owner_id(path):
                    continue
                try:
                    if file_attributes(path) & HIDE_BITS:
                        continue
                    buckets[classify(path)].append(path)
                except OSError as exc:
                    scan_errors.append(f"{path.name}：{exc}")
        candidates = [path for paths in buckets.values() for path in paths]
        snapshot = None
        allow_unpositioned = False
        if candidates:
            try:
                capture_many = getattr(self.groups.positions, "capture_many", None)
                if capture_many:
                    snapshot = capture_many(candidates)
            except Exception as exc:
                if "自动排列" in str(exc):
                    if not confirm_auto_arrange_grouping():
                        return
                    snapshot = {}
                    allow_unpositioned = True
                else:
                    message = f"暂时无法读取桌面图标位置：{exc}\n\n本次没有更改桌面项目。"
                    QMessageBox.warning(None, "无法一键整理", message)
                    return
        created, grouped = [], []
        for name, paths in buckets.items():
            if not paths:
                continue
            config = next((p for p in self.store.data["panels"]
                           if p.get("kind") == "virtual" and p.get("auto_type") == name), None)
            if config is None:
                config = self.add_virtual(name, icon_for_type(name))
                config["auto_type"] = name
                created.append(config["id"])
            config["hidden"] = False
            self.panels[config["id"]].show()
            added, errors = self.groups.add(config, paths, snapshot=snapshot,
                                            allow_unpositioned=allow_unpositioned)
            successful = [path for path in paths if self.groups.owner_id(path) == config["id"]]
            grouped.extend({"path": str(path), "owner": None} for path in successful)
            scan_errors.extend(errors)
            if not successful and config["id"] in created:
                panel = self.panels.pop(config["id"])
                panel.hide()
                panel.deleteLater()
                self.store.data["panels"].remove(config)
                created.remove(config["id"])
        if grouped:
            self.record_action({"kind": "auto_sort", "items": grouped, "created": created})
        else:
            for panel_id in created:
                panel = self.panels.pop(panel_id)
                panel.close()
                panel.deleteLater()
                self.store.data["panels"] = [p for p in self.store.data["panels"] if p.get("id") != panel_id]
        self.store.save()
        self.sync_group_visibility(recapture=False)
        self.refresh_panels()
        self.restack_panels()
        if scan_errors:
            QMessageBox.warning(None, "部分桌面项目未整理", "\n".join(dict.fromkeys(scan_errors[:12])))
        elif grouped:
            self.tray.showMessage("一键整理完成", f"已按类型整理 {len(grouped)} 个桌面项目；可撤销。",
                                  QSystemTrayIcon.Information, 5000)
        else:
            self.tray.showMessage("一键整理", "没有尚未分组的桌面项目。",
                                  QSystemTrayIcon.Information, 5000)

    def _clear_session(self) -> None:
        if not self._exit_restore_ok:
            return
        try:
            self._session_file.unlink(missing_ok=True)
        except OSError:
            pass

    def toggle_desktop_menu(self, enabled: bool) -> None:
        try:
            set_desktop_menu_enabled(enabled)
        except OSError as exc:
            QMessageBox.warning(None, "桌面右键入口", str(exc))
            return
        self.store.data["desktop_menu_enabled"] = enabled
        self.store.save()

    def set_widget_visible(self, kind: str, visible: bool) -> None:
        widget = self.widgets[kind]
        widget.config["hidden"] = not visible
        widget.setVisible(visible)
        self.store.save()
        if visible:
            self.restack_panels()

    def populate_tray_menu(self) -> None:
        menu = self.tray_menu
        menu.clear()
        menu.addAction("打开控制台", self.open_center)
        menu.addAction(themed_icon("fn-search-gen-64.png"), "快速查找", self.open_search)
        menu.addAction("外观与快捷键", self.open_appearance)
        notes = menu.addMenu("便签")
        notes.addAction("新建便签", self.notes.new_note)
        notes.addAction("管理便签", self.notes.show_manager)
        notes.addAction("显示全部便签", self.notes.show_all)
        menu.addAction(themed_icon("fn-isac-gen-64.png"), "打开 ISAC", self.open_chat)
        menu.addAction(themed_icon("cat-system-gen-64.png"), "模型配置", self.open_profiles)
        menu.addSeparator()
        undo = menu.addAction("撤销上一步整理", self.undo_last)
        undo.setEnabled(bool(self._history))
        scenes = menu.addMenu("切换场景")
        for scene in self.store.data["scenes"]:
            action = scenes.addAction(scene["name"], lambda checked=False, sid=scene["id"]: self.switch_scene(sid))
            action.setCheckable(True)
            action.setChecked(scene["id"] == self.store.data.get("active_scene"))
        scenes.addSeparator()
        scenes.addAction("保存当前场景", self.save_scene)
        scenes.addAction("新建场景", self.create_scene)
        menu.addAction("显示全部面板", self.show_all)
        components = menu.addMenu("桌面组件")
        for kind, label in (("schedule", "日程"), ("weather", "天气"),
                            ("music", "音乐")):
            action = components.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.widgets[kind].config.get("hidden", False))
            action.triggered.connect(
                lambda checked=False, name=kind: self.set_widget_visible(name, checked))
        menu.addAction("一键按类型整理", self.auto_organize)
        menu.addAction(themed_icon("fn-widgets-gen-64.png"), "新建分类分框", self.add_collection)
        menu.addAction("添加已有文件夹", self.prompt_folder)
        desktop_entry = menu.addAction("桌面右键快捷入口", self.toggle_desktop_menu)
        desktop_entry.setCheckable(True)
        desktop_entry.setChecked(desktop_menu_enabled())
        desktop_entry.setEnabled(bool(getattr(sys, "frozen", False)))
        menu.addSeparator()
        menu.addAction(themed_icon("fn-power-gen-64.png"), "退出 SHD Desktop", self.app.quit)

    def record_action(self, action: dict) -> None:
        self._history.append(action)
        del self._history[:-20]
        self.store.save()

    def undo_last(self) -> None:
        if not self._history:
            return
        action = self._history[-1]
        kind = action.get("kind")
        try:
            if kind in ("group", "auto_sort"):
                for item in reversed(action["items"]):
                    path = Path(item["path"])
                    current = self.groups.owner_id(path)
                    if current and not item["owner"]:
                        owner = next(p for p in self.store.data["panels"] if p.get("id") == current)
                        self.groups.remove(owner, path)
                    if item["owner"]:
                        owner = next(p for p in self.store.data["panels"] if p.get("id") == item["owner"])
                        added, errors = self.groups.add(owner, [path], snapshot={},
                                                        allow_unpositioned=True)
                        if errors:
                            raise OSError("\n".join(errors))
                if kind == "auto_sort":
                    for panel_id in action.get("created", []):
                        panel = self.panels.pop(panel_id, None)
                        if panel:
                            panel.close()
                            panel.deleteLater()
                        self.store.data["panels"] = [p for p in self.store.data["panels"]
                                                     if p.get("id") != panel_id]
                self.sync_group_visibility(recapture=False)
            elif kind in ("move", "dissolve_folder"):
                for item in reversed(action.get("items", [])):
                    source, destination = Path(item["to"]), Path(item["from"])
                    if not source.exists() or destination.exists():
                        raise OSError(f"无法还原 {source.name}：原位置已被占用或文件已移动")
                for item in reversed(action.get("items", [])):
                    Path(item["from"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(item["to"], item["from"])
                if kind == "dissolve_folder":
                    self._restore_panel_config(action["panel"])
            elif kind == "dissolve_virtual":
                self._restore_panel_config(action["panel"])
                self.sync_group_visibility()
            elif kind == "scene":
                self.switch_scene(action["previous"], record=False)
            else:
                return
        except (OSError, KeyError, StopIteration) as exc:
            QMessageBox.warning(None, "撤销失败", str(exc))
            return
        self._history.pop()
        self.store.save()
        self.refresh_panels()

    def _restore_panel_config(self, config: dict) -> None:
        if config["id"] in self.panels:
            raise OSError("分框已存在，无法撤销")
        config = copy.deepcopy(config)
        self.store.data["panels"].append(config)
        self._show_panel(config)
        self.restack_panels()
        self.store.save()

    def sync_group_visibility(self, recapture: bool = True) -> None:
        errors = self.groups.sync_visibility(recapture=recapture)
        self.refresh_panels()
        if errors:
            self.tray.showMessage("桌面图标整理", "\n".join(errors[:3]), QSystemTrayIcon.Warning, 8000)

    def save_scene(self) -> None:
        self._save_live_geometry()
        self.scenes.capture()
        self.center.refresh_scenes()

    def create_scene(self) -> None:
        name, accepted = QInputDialog.getText(None, "新建场景", "场景名称")
        if accepted and name.strip():
            self._save_live_geometry()
            self.scenes.capture()
            self.scenes.create(name.strip())
            self.center.refresh_scenes()

    def delete_scene(self, scene_id: str) -> None:
        if self.scenes.delete(scene_id):
            self.center.refresh_scenes()

    def _save_live_geometry(self) -> None:
        for panel in self.panels.values():
            if panel.isVisible():
                panel.save_geometry()
        for widget in self.widgets.values():
            if widget.isVisible():
                widget.save_geometry()
        self.store.save()

    def switch_scene(self, scene_id: str, record: bool = True) -> None:
        previous = self.store.data.get("active_scene")
        if previous == scene_id:
            return
        self._save_live_geometry()
        self.scenes.switch(scene_id)
        for panel in self.panels.values():
            config = panel.config
            panel.setGeometry(config.get("x", 80), config.get("y", 80),
                              config.get("w", 350), config.get("h", 300))
            panel.apply_collapsed()
            panel.setVisible(not config.get("hidden"))
        for widget in self.widgets.values():
            config = widget.config
            widget.setGeometry(config.get("x", 470), config.get("y", 80),
                               config.get("w", 310), config.get("h", 180))
            widget.setVisible(not config.get("hidden"))
        config = self.isac_launcher.config
        self.isac_launcher.move(config.get("x", 850), config.get("y", 80))
        self.isac_launcher.setVisible(not config.get("hidden"))
        self.sync_group_visibility()
        self.restack_panels()
        if record:
            self.record_action({"kind": "scene", "previous": previous})
        self.center.refresh_scenes()

    def add_collection(self) -> None:
        title, accepted = QInputDialog.getText(None, "新建分类分框", "分框名称")
        if not accepted or not title.strip():
            return
        title = title.strip()
        label, accepted = QInputDialog.getItem(None, "选择分类图标", "分类", list(CATEGORIES), 0, False)
        if not accepted:
            return
        mode, accepted = QInputDialog.getItem(
            None, "分框模式", "图标拖入后的处理方式",
            ["桌面整理（不移动文件）", "文件夹分框（移动文件）"], 0, False)
        if not accepted:
            return
        if mode.startswith("桌面整理"):
            self.add_virtual(title, CATEGORIES[label])
            return
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")[:40] or "分类"
        folder = self.store.file.parent / "Collections" / f"{safe_name}-{uuid.uuid4().hex[:6]}"
        try:
            folder.mkdir(parents=True, exist_ok=False)
        except OSError as exc:
            QMessageBox.warning(None, "无法建立分框", str(exc))
            return
        self.add_folder(folder, title, CATEGORIES[label])

    def prompt_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(None, "选择面板目录", str(desktop_path()))
        if chosen:
            self.add_folder(Path(chosen))

    def remove_panel(self, panel_id: str) -> None:
        panel = self.panels.get(panel_id)
        if panel is None:
            return
        old_config = copy.deepcopy(panel.config)
        moved_back = []
        if panel.is_virtual:
            count = len(self.groups.records(panel.config))
            question = f"解散“{panel.config.get('title', '')}”？\n{count} 个图标会恢复到桌面。"
            if QMessageBox.question(panel, "解散桌面整理分框", question,
                                    QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
                return
            errors = self.groups.restore_panel(panel.config)
        else:
            source = panel.folder
            desktop = self.groups.roots[0]
            same_folder = path_key(source) == path_key(desktop)
            try:
                count = 0 if same_folder or not source.is_dir() else len(list(source.iterdir()))
            except OSError as exc:
                QMessageBox.warning(panel, "无法解散分框", str(exc))
                return
            question = (f"解散“{panel.config.get('title', '')}”？\n"
                        + (f"会将目录中的 {count} 项移回桌面；同名项目将自动改名。"
                           if count else "只删除分框，文件保持原位。"))
            if QMessageBox.question(panel, "解散文件夹分框", question,
                                    QMessageBox.Yes | QMessageBox.Cancel) != QMessageBox.Yes:
                return
            errors = []
            restored_positions = []
            if count:
                desktop.mkdir(parents=True, exist_ok=True)
                for item in list(source.iterdir()):
                    destination = desktop / item.name
                    number = 1
                    while destination.exists():
                        name = item.stem if item.is_file() else item.name
                        suffix = item.suffix if item.is_file() else ""
                        destination = desktop / f"{name} (恢复 {number}){suffix}"
                        number += 1
                    try:
                        shutil.move(str(item), str(destination))
                        moved_back.append({"from": str(item), "to": str(destination)})
                        point = panel.config.get("desktop_positions", {}).get(item.name)
                        if point:
                            restored_positions.append((destination, point))
                    except OSError as exc:
                        errors.append(f"{item.name}：{exc}")
            if restored_positions:
                try:
                    self.groups.positions.refresh()
                    missing = self.groups.positions.restore(restored_positions)
                    if missing:
                        QMessageBox.warning(panel, "图标已移回桌面",
                                            "部分图标未能恢复原排列位置，可在桌面手动调整。")
                except OSError:
                    QMessageBox.warning(panel, "图标已移回桌面",
                                        "桌面位置暂时无法还原，可在桌面手动调整。")
            collections = self.store.file.parent / "Collections"
            if not errors and source.parent == collections and source.is_dir():
                try:
                    source.rmdir()
                except OSError:
                    pass
        if errors:
            QMessageBox.warning(panel, "部分图标未恢复", "\n".join(errors))
            self.refresh_panels()
            return
        self.panels.pop(panel_id)
        panel.close()
        panel.deleteLater()
        self.store.data["panels"] = [p for p in self.store.data["panels"] if p.get("id") != panel_id]
        self.record_action({"kind": "dissolve_virtual" if panel.is_virtual else "dissolve_folder",
                            "panel": old_config, "items": moved_back})
        self.store.save()
        self.refresh_panels()

    def show_all(self) -> None:
        for panel in self.panels.values():
            panel.config["hidden"] = False
            panel.show()
        self.store.save()
        self.sync_group_visibility()
        for panel in self.widgets.values():
            panel.config["hidden"] = False
            panel.show()
        self.isac_launcher.config["hidden"] = False
        self.isac_launcher.show()
        self.store.save()
        self.restack_panels()

    def refresh_widgets(self) -> None:
        for panel in self.widgets.values():
            panel.refresh()

    def open_center(self) -> None:
        self.center.show()
        self.center.raise_()
        self.center.activateWindow()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_center()

    def open_chat(self) -> None:
        self.chat.show()
        self.chat.raise_()
        self.chat.activateWindow()

    def apply_appearance(self, values) -> None:
        apply_hud(self.app, values)

    def open_appearance(self) -> None:
        if self.appearance_window and self.appearance_window.isVisible():
            self.appearance_window.raise_()
            self.appearance_window.activateWindow()
            return
        if self.appearance_window:
            self.appearance_window.deleteLater()
        self.appearance_window = AppearanceDialog(self)
        self.appearance_window.show()
        self.appearance_window.raise_()
        self.appearance_window.activateWindow()

    def open_search(self) -> None:
        self.search_window.show_search()

    def search_records(self) -> list[dict]:
        records = []
        for panel_id, panel in self.panels.items():
            title = panel.config.get("title") or panel.folder.name or "桌面"
            for index in range(panel.list.count()):
                item = panel.list.item(index)
                path = item.data(Qt.UserRole)
                records.append({"panel_id": panel_id, "panel_title": title,
                                "name": item.text(), "path": path, "icon": item.icon(),
                                "search": f"{item.text()} {Path(path).name} {title}".casefold()})
        return records

    def locate_search_result(self, record: dict) -> bool:
        panel = self.panels.get(record["panel_id"])
        if not panel or not Path(record["path"]).exists():
            return False
        key = path_key(Path(record["path"]))
        item = next((panel.list.item(i) for i in range(panel.list.count())
                     if path_key(Path(panel.list.item(i).data(Qt.UserRole))) == key), None)
        if item is None:
            return False
        panel.config["hidden"] = False
        if panel.config.get("collapsed"):
            panel.toggle_collapsed()
        panel.show()
        self.sync_group_visibility()
        self.restack_panels()
        item = next((panel.list.item(i) for i in range(panel.list.count())
                     if path_key(Path(panel.list.item(i).data(Qt.UserRole))) == key), None)
        if item is None:
            return False
        panel.list.clearSelection()
        panel.list.setCurrentItem(item)
        item.setSelected(True)
        panel.list.doItemsLayout()
        panel.list.scrollToItem(item, QAbstractItemView.PositionAtCenter)
        self.restack_panels(panel)
        panel.activateWindow()
        panel.list.setFocus()
        self.store.geometry_timer().start()
        return True

    def open_profiles(self) -> None:
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def scan_reminders(self) -> None:
        for event in self.events.due():
            self.tray.showMessage("SHD · 日程提醒", event["title"], QSystemTrayIcon.Information, 10000)
            self.events.mark_notified(event["id"])
        if hasattr(self, "center"):
            self.center.schedule.refresh()
            self.refresh_widgets()


def main() -> int:
    # Windowed PyInstaller executables have no console streams. argparse --help
    # and error reporting still need writable streams instead of None.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    def record_crash(exc_type, exc_value, exc_traceback):
        try:
            log = Path(os.getenv("LOCALAPPDATA", Path.home())) / "SHDDesktop" / "crash.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as output:
                output.write("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
                output.write("\n")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = record_crash
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="render one panel and exit")
    parser.add_argument("--show-center", action="store_true", help="open the control center on launch")
    parser.add_argument("--new-note", action="store_true", help="create a desktop note")
    parser.add_argument("--restore-desktop-icons", action="store_true", help="restore grouped desktop icons and exit")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setApplicationName("SHD Desktop")
    app.setApplicationVersion("1.0.3")
    app.setWindowIcon(QIcon(str(ICON)))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    if args.restore_desktop_icons:
        roots = [desktop_path(), Path(os.getenv("PUBLIC", "C:/Users/Public")) / "Desktop"]
        errors = DesktopGroups(ConfigStore(), roots).restore_for_exit(force_positions=True)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            QMessageBox.warning(None, "部分桌面图标未恢复", "\n".join(errors[:12]))
        return 1 if errors else 0
    if args.smoke:
        with tempfile.TemporaryDirectory(prefix="shd-smoke-") as temp:
            controller = Controller(app, ConfigStore(Path(temp)), enable_hotkeys=False)
            def capture():
                output = Path.cwd() / "preview.png" if getattr(sys, "frozen", False) else BASE / "preview.png"
                controller.panels[next(iter(controller.panels))].grab().save(str(output))
                print(output)
                app.quit()
            QTimer.singleShot(500, capture)
            result = app.exec()
            controller.events.close()
            return result
    server = claim_or_forward(app, "note" if args.new_note else "center")
    if server is None:
        return 0
    if getattr(sys, "frozen", False):
        try:
            migrate_startup_enabled()
        except OSError:
            pass
    controller = Controller(app, ConfigStore())
    receive_requests(server, controller.open_center, controller.notes.new_note)
    if args.show_center:
        controller.open_center()
    if args.new_note:
        controller.notes.new_note()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
