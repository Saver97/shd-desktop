"""Two panel types remain separate, and disbanding restores desktop items."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from app import ConfigStore, Controller
from shd_desktop.desktop.desktop_groups import HIDE_BITS, file_attributes


class Positions:
    def refresh(self):
        pass

    def get(self, path):
        return [160, 320]

    def restore(self, records):
        return []


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    icon = desktop / "Game.lnk"
    icon.write_text("shortcut")
    original = file_attributes(icon) & HIDE_BITS
    store = ConfigStore(root / "config")
    store.data["panels"] = [{"id": "desktop", "kind": "folder", "path": str(desktop),
                             "title": "桌面", "view": "grid"}]
    controller = Controller(app, store, [desktop])
    controller.groups.positions = Positions()
    original_text, original_item = QInputDialog.getText, QInputDialog.getItem
    answers = iter([("游戏", True), ("游戏", True), ("桌面整理（不移动文件）", True)])
    QInputDialog.getText = lambda *args, **kwargs: next(answers)
    QInputDialog.getItem = lambda *args, **kwargs: next(answers)
    try:
        controller.add_collection()
    finally:
        QInputDialog.getText, QInputDialog.getItem = original_text, original_item
    virtual = next(panel for panel in controller.panels.values() if panel.is_virtual)
    assert "path" not in virtual.config
    assert virtual.receive_drop([icon], QPoint(0, 0))
    assert icon.exists() and file_attributes(icon) & HIDE_BITS == HIDE_BITS
    assert virtual.list.count() == 1
    assert controller.panels["desktop"].list.count() == 0

    original_question = QMessageBox.question
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
    try:
        controller.remove_panel(virtual.config["id"])
        assert virtual.config["id"] not in controller.panels
        assert icon.exists() and file_attributes(icon) & HIDE_BITS == original
        assert controller.panels["desktop"].list.count() == 1

        managed = store.file.parent / "Collections" / "tools"
        managed.mkdir(parents=True)
        controller.add_folder(managed, "工具")
        folder = next(panel for panel in controller.panels.values() if panel.folder == managed)
        second = desktop / "Tool.lnk"
        second.write_text("tool")
        assert folder.receive_drop([second], QPoint(0, 0))
        assert not second.exists() and (managed / second.name).exists()
        second.write_text("existing desktop item")
        controller.remove_panel(folder.config["id"])
        assert second.read_text() == "existing desktop item"
        assert (desktop / "Tool (恢复 1).lnk").read_text() == "tool"
        assert not managed.exists()

        controller.add_virtual("退出恢复")
        exit_group = next(panel for panel in controller.panels.values() if panel.is_virtual)
        assert exit_group.receive_drop([icon], QPoint(0, 0))
        assert file_attributes(icon) & HIDE_BITS == HIDE_BITS
        QTimer.singleShot(0, app.quit)
        app.exec()
        assert icon.exists() and file_attributes(icon) & HIDE_BITS == original
        assert len(exit_group.config["items"]) == 1
    finally:
        QMessageBox.question = original_question
        controller.events.close()
        controller.center.music.bridge.close()

print("virtual and folder panel modes passed")
