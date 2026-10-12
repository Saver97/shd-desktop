"""One-click sorting uses virtual panels and supports a single-step undo."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMessageBox

from app import ConfigStore, Controller
from shd_desktop.desktop.desktop_groups import HIDE_BITS, file_attributes, path_key


class Positions:
    def capture_many(self, paths):
        return {path_key(path): [100, 200] for path in paths}

    def get(self, path):
        return [100, 200]

    def refresh(self):
        pass

    def restore(self, records):
        return []


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    files = [desktop / "Report.pdf", desktop / "Photo.PNG", desktop / "Game.lnk"]
    for path in files:
        path.write_text(path.name)
    folder = desktop / "Projects"
    folder.mkdir()
    files.append(folder)
    originals = {path: file_attributes(path) & HIDE_BITS for path in files}
    store = ConfigStore(root / "config")
    controller = Controller(app, store, [desktop])
    controller.groups.positions = Positions()
    controller.auto_organize()
    panels = {panel.config.get("auto_type"): panel for panel in controller.panels.values()
              if panel.is_virtual}
    assert set(panels) == {"文档", "图片", "快捷方式", "文件夹"}
    assert all(path.exists() and file_attributes(path) & HIDE_BITS == HIDE_BITS for path in files)
    assert len(controller._history) == 1
    controller.auto_organize()
    assert len(controller._history) == 1
    second = desktop / "Notes.txt"
    second.write_text("notes")
    controller.auto_organize()
    assert len(controller._history) == 2
    assert len(panels["文档"].config["items"]) == 2
    controller.undo_last()
    assert len(panels["文档"].config["items"]) == 1
    assert second.exists() and file_attributes(second) & HIDE_BITS == 0
    controller.undo_last()
    assert not any(panel.is_virtual for panel in controller.panels.values())
    assert all(path.exists() and file_attributes(path) & HIDE_BITS == originals[path] for path in files)
    class AutoArrange:
        def capture_many(self, paths):
            raise ValueError("Windows 桌面开启了自动排列")
        def refresh(self):
            pass
        def restore(self, records):
            return []
    controller.groups.positions = AutoArrange()
    prompts = []
    original_question = QMessageBox.question
    QMessageBox.question = lambda *args: prompts.append(args) or QMessageBox.Cancel
    try:
        controller.auto_organize()
    finally:
        QMessageBox.question = original_question
    assert len(prompts) == 1 and "精确排列位置" in prompts[0][2]
    assert not any(panel.is_virtual for panel in controller.panels.values())
    assert all(file_attributes(path) & HIDE_BITS == originals[path] for path in files)
    prompts.clear()
    QMessageBox.question = lambda *args: prompts.append(args) or QMessageBox.Yes
    try:
        controller.auto_organize()
    finally:
        QMessageBox.question = original_question
    assert len(prompts) == 1
    assert all(path.exists() and file_attributes(path) & HIDE_BITS == HIDE_BITS for path in files)
    assert all(record["position"] is None for panel in controller.panels.values()
               if panel.is_virtual for record in panel.config["items"])
    controller.undo_last()
    assert not any(panel.is_virtual for panel in controller.panels.values())
    assert all(file_attributes(path) & HIDE_BITS == originals[path] for path in files)
    controller.add_virtual("手动")
    manual = next(panel for panel in controller.panels.values() if panel.is_virtual)
    QMessageBox.question = lambda *args: QMessageBox.Yes
    try:
        assert manual.receive_drop([files[0]], QPoint())
    finally:
        QMessageBox.question = original_question
    assert file_attributes(files[0]) & HIDE_BITS == HIDE_BITS
    controller.undo_last()
    assert file_attributes(files[0]) & HIDE_BITS == originals[files[0]]
    controller.events.close()
    controller.center.music.bridge.close()

print("one-click desktop type sorting passed")
