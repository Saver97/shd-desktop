"""Shared tactical desktop visual system."""

from __future__ import annotations

from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QSizePolicy, QWidget


ORANGE = "#F48A35"
MUTED = "#98A9AF"

HUD_DEFAULTS = {"opacity": 74, "font_size": 12, "icon_size": 40}


def normalize_hud(value) -> dict:
    value = value if isinstance(value, dict) else {}
    limits = {"opacity": (40, 100), "font_size": (10, 16), "icon_size": (24, 64)}
    result = {}
    for key, default in HUD_DEFAULTS.items():
        try:
            number = int(value.get(key, default))
        except (TypeError, ValueError, OverflowError):
            number = default
        low, high = limits[key]
        result[key] = max(low, min(high, number))
    return result


def current_hud() -> dict:
    return getattr(QApplication.instance(), "_shd_hud", HUD_DEFAULTS)


def hud_background() -> QColor:
    return QColor(17, 18, 20, int(current_hud()["opacity"] * 255 / 100))


def scaled_style(style: str) -> str:
    scale = current_hud()["font_size"] / 12
    return re.sub(r"(font-size:\s*)(\d+)px", lambda match:
                  match[1] + str(round(int(match[2]) * scale)) + "px", style)


def apply_hud(app, values: dict) -> None:
    settings = normalize_hud(values)
    if getattr(app, "_shd_hud", None) == settings:
        return
    app._shd_hud = settings
    app.setStyleSheet(scaled_style(STYLE))
    for widget in app.allWidgets():
        if hasattr(widget, "apply_hud"):
            widget.apply_hud()
        widget.update()


def hud_section(title: str, icon_path: Path) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    icon = QLabel()
    icon.setFixedSize(25, 25)
    icon.setPixmap(QPixmap(str(icon_path)).scaled(24, 24, Qt.KeepAspectRatio,
                                                 Qt.SmoothTransformation))
    layout.addWidget(icon)
    heading = QLabel(title)
    heading.setObjectName("HudSection")
    layout.addWidget(heading, 1)
    return row


class HudHeader(QWidget):
    """Small vector header; no image decoding or animation during repaint."""

    def __init__(self, title: str, subtitle: str, code: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.code = code
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151618"))
        painter.fillRect(16, 25, 6, 6, QColor(244, 138, 53))
        painter.setPen(QColor("#F1F1F1"))
        painter.setFont(QFont("Segoe UI", min(21, round(19 * current_hud()["font_size"] / 12)), QFont.Normal))
        painter.drawText(35, 9, max(160, self.width() - 250), 32,
                         Qt.AlignVCenter, self.title)
        painter.setPen(QColor("#A4A6AA"))
        painter.setFont(QFont("Microsoft YaHei UI", round(9 * current_hud()["font_size"] / 12)))
        painter.drawText(36, 41, max(160, self.width() - 250), 20,
                         Qt.AlignVCenter, self.subtitle)
        if self.width() >= 560:
            painter.setPen(QColor("#E4E4E5"))
            painter.setFont(QFont("Bahnschrift", 10))
            painter.drawText(self.width() - 200, 17, 180, 21,
                             Qt.AlignRight | Qt.AlignVCenter, self.code)
            painter.setPen(QColor("#A4A6AA"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(self.width() - 200, 39, 180, 19,
                             Qt.AlignRight | Qt.AlignVCenter, "SHD NETWORK / LOCAL")
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        painter.drawLine(16, self.height() - 1, self.width() - 16, self.height() - 1)


STYLE = """
QWidget { color: #EAF0EF; font-family: 'Microsoft YaHei UI'; font-size: 12px; }
QMainWindow { background: #1A1B1E; }
QDialog, QMessageBox, QInputDialog { background: #24272E; color: #EAF0EF; }
QMessageBox QLabel, QInputDialog QLabel { color: #EAF0EF; }
QLabel { color: #D7E2E3; }
QLabel#HudSection {
    color: #F1F1F1; font-size: 16px; font-weight: 400;
    border-left: 2px solid #F48A35; padding: 3px 0 3px 9px;
}
QTextBrowser#DailyChatLog { background: rgba(0,0,0,40); border: 0; }
QLineEdit, QComboBox, QDateTimeEdit, QSpinBox, QListWidget,
QPlainTextEdit, QTextBrowser {
    background: #1D2026; color: #ECF3F2; border: 1px solid #414650;
    border-radius: 3px; padding: 7px; selection-background-color: #915024;
}
QLineEdit:hover, QComboBox:hover, QDateTimeEdit:hover, QSpinBox:hover,
QListWidget:hover, QPlainTextEdit:hover, QTextBrowser:hover { border-color: #717985; }
QLineEdit:focus, QComboBox:focus, QDateTimeEdit:focus, QSpinBox:focus,
QPlainTextEdit:focus, QTextBrowser:focus { border: 1px solid #F48A35; }
QLineEdit:disabled, QComboBox:disabled { color: #748991; background: #1A1D23; }
QListWidget::item { padding: 9px 8px; border-bottom: 1px solid #353A43; }
QListWidget::item:selected { background: #493A28; color: #FFFFFF; border-left: 2px solid #F48A35; }
QListWidget::item:hover { background: #2E333B; }
QPushButton {
    background: rgba(255,255,255,14);
    color: #EDF1EF; border: 0; border-bottom: 1px solid #55585D;
    border-radius: 0; padding: 7px 12px; font-weight: 400;
}
QPushButton:hover { background: #F48A35; border-color: #F48A35; color: #151618; }
QPushButton:pressed { background: #89512A; color: #FFFFFF; }
QPushButton:disabled { color: #89919C; border-color: #3B414B; background: #252932; }
QPushButton[hudRole="primary"] { background: #F48A35; color: #171819; border-color: #F48A35; }
QPushButton[hudRole="primary"]:hover { background: #FF9D52; }
QTabWidget::pane { background: #191A1D; border: 0; border-top: 1px solid #55585D; }
QTabBar::tab {
    background: rgba(255,255,255,12); color: #CFD0D3; padding: 10px 25px;
    border: 0; border-top: 3px solid transparent; margin-right: 3px; min-width: 72px;
}
QTabBar::tab:hover { color: #F1D4B6; background: #303640; }
QTabBar::tab:selected { color: #FFFFFF; border-top: 3px solid #F48A35; background: #383A3E; }
QToolBar { background: #202124; border-bottom: 1px solid #3D444F; spacing: 5px; padding: 5px 8px; }
QToolBar QToolButton { color: #E3EAEB; border: 1px solid transparent; padding: 7px 8px; }
QToolBar QToolButton:hover { background: #343A44; border-color: #CD793B; color: #FFD0A3; }
QToolBar::separator { width: 1px; background: #454C58; margin: 4px 9px; }
QStatusBar { background: #20242B; color: #B2B9C4; border-top: 1px solid #3D444F; }
QMenu { background-color: #272C34; color: #EDF3F2; border: 1px solid #606A77; padding: 5px; }
QMenu::item { background: transparent; color: #EDF3F2; padding: 7px 28px; }
QMenu::item:selected { background: #414852; color: #FFFFFF; }
QMenu::item:disabled { color: #8E98A5; }
QMenu::separator { height: 1px; background: #4A535F; margin: 5px 10px; }
QScrollBar:vertical { background: #1E2229; width: 10px; }
QScrollBar::handle:vertical { background: #5D6775; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #E08339; }
QSlider::groove:horizontal { height: 4px; background: #414B59; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #F48A35; border-radius: 2px; }
QSlider::handle:horizontal { background: #FFD1A4; border: 2px solid #F48A35; width: 13px; margin: -6px 0; border-radius: 8px; }
"""

