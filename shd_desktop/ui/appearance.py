"""Live HUD preview and search shortcut settings."""

from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QIcon, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                              QHBoxLayout, QKeySequenceEdit, QLabel, QPushButton,
                              QSlider, QVBoxLayout)

from shd_desktop.ui.theme import HUD_DEFAULTS, normalize_hud
from shd_desktop.integration.search_hotkey import DEFAULT_SHORTCUT


class AppearanceDialog(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("SHD Desktop · 外观与快捷键")
        self.setWindowIcon(controller.app.windowIcon())
        self.setMinimumWidth(480)
        self.original = normalize_hud(controller.store.data.get("hud"))
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(80)
        self.preview_timer.timeout.connect(self.preview)
        root = QVBoxLayout(self)
        root.addWidget(QLabel("HUD 外观  //  修改时预览，保存后下次启动沿用"))
        form = QFormLayout()
        self.sliders, self.labels = {}, {}
        for key, title, low, high, unit in (("opacity", "桌面底板不透明度", 40, 100, "%"),
                                           ("font_size", "界面字号", 10, 16, " px"),
                                           ("icon_size", "分框图标尺寸", 24, 64, " px")):
            row = QHBoxLayout()
            slider = QSlider(Qt.Horizontal)
            slider.setRange(low, high)
            slider.setValue(self.original[key])
            label = QLabel()
            label.setMinimumWidth(50)
            self.sliders[key], self.labels[key] = slider, (label, unit)
            slider.valueChanged.connect(self.changed)
            row.addWidget(slider, 1)
            row.addWidget(label)
            form.addRow(title, row)
        root.addLayout(form)
        root.addWidget(QLabel("透明度作用于桌面分框、状态卡和 ISAC；文字保持清晰。"))
        self.enabled = QCheckBox("启用全局快速查找快捷键")
        search = controller.store.data.get("search", {})
        self.enabled.setChecked(bool(search.get("enabled", True)))
        root.addWidget(self.enabled)
        self.shortcut = QKeySequenceEdit(QKeySequence(search.get("shortcut", DEFAULT_SHORTCUT)))
        self.shortcut.setMaximumSequenceLength(1)
        root.addWidget(self.shortcut)
        self.status = QLabel("托盘和控制台也可打开快速查找。按 Esc 取消本次预览。")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        defaults = QPushButton("恢复默认外观")
        defaults.clicked.connect(self.reset_defaults)
        root.addWidget(defaults)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.update_labels()

    def values(self):
        return {key: slider.value() for key, slider in self.sliders.items()}

    def update_labels(self):
        for key, (label, unit) in self.labels.items():
            label.setText(str(self.sliders[key].value()) + unit)

    def changed(self):
        self.update_labels()
        self.preview_timer.start()

    def preview(self):
        self.controller.apply_appearance(self.values())

    def reset_defaults(self):
        for key, slider in self.sliders.items():
            with QSignalBlocker(slider):
                slider.setValue(HUD_DEFAULTS[key])
        self.changed()

    def save(self):
        text = self.shortcut.keySequence().toString(QKeySequence.PortableText)
        if not self.enabled.isChecked() and not text:
            text = DEFAULT_SHORTCUT
        try:
            canonical = self.controller.search_hotkey.configure(self.enabled.isChecked(), text)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.preview_timer.stop()
        self.preview()
        self.controller.store.data["hud"] = self.values()
        self.controller.store.data["search"] = {"enabled": self.enabled.isChecked(), "shortcut": canonical}
        self.controller.store.save()
        self.accept()

    def reject(self):
        self.preview_timer.stop()
        self.controller.apply_appearance(self.original)
        super().reject()
