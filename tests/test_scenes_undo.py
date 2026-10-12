"""Exercise scene visibility, grouping undo, file move undo, and panel recovery."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMessageBox

from app import ConfigStore, Controller
from shd_desktop.desktop.desktop_groups import HIDE_BITS, file_attributes


class Positions:
    def capture_many(self, paths):
        from shd_desktop.desktop.desktop_groups import path_key
        return {path_key(path): [120, 240] for path in paths}

    def get(self, path):
        return [120, 240]

    def refresh(self):
        pass

    def restore(self, records):
        return []


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    desktop = root / "Desktop"
    desktop.mkdir()
    icon = desktop / "Game.lnk"
    icon.write_text("game")
    original = file_attributes(icon) & HIDE_BITS
    store = ConfigStore(root / "config")
    store.data["panels"] = []
    controller = Controller(app, store, [desktop])
    controller.groups.positions = Positions()

    controller.add_virtual("游戏")
    virtual = next(panel for panel in controller.panels.values() if panel.is_virtual)
    assert virtual.receive_drop([icon], QPoint())
    assert file_attributes(icon) & HIDE_BITS == HIDE_BITS
    virtual.drag_back_to_desktop([icon])
    assert file_attributes(icon) & HIDE_BITS == original
    assert not virtual.config["items"]
    controller.undo_last()
    assert file_attributes(icon) & HIDE_BITS == HIDE_BITS
    assert len(virtual.config["items"]) == 1

    controller.scenes.create("清爽桌面")
    controller.center.refresh_scenes()
    second_scene = store.data["active_scene"]
    virtual.close_panel()
    assert file_attributes(icon) & HIDE_BITS == original
    controller.switch_scene(store.data["scenes"][0]["id"])
    assert virtual.isVisible()
    assert file_attributes(icon) & HIDE_BITS == HIDE_BITS
    controller.switch_scene(second_scene)
    assert not virtual.isVisible()
    assert file_attributes(icon) & HIDE_BITS == original
    controller.undo_last()
    assert virtual.isVisible()
    assert file_attributes(icon) & HIDE_BITS == HIDE_BITS

    managed = root / "config" / "Collections" / "work"
    managed.mkdir(parents=True)
    controller.add_folder(managed, "工作")
    folder = next(panel for panel in controller.panels.values() if panel.folder == managed)
    document = desktop / "Note.txt"
    document.write_text("note")
    assert folder.receive_drop([document], QPoint())
    assert not document.exists() and (managed / document.name).exists()
    controller.undo_last()
    assert document.exists() and not (managed / document.name).exists()

    question = QMessageBox.question
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.Yes
    try:
        assert folder.receive_drop([document], QPoint())
        controller.remove_panel(folder.config["id"])
        assert document.exists() and not managed.exists()
        controller.undo_last()
        assert folder.config["id"] in controller.panels
        assert not document.exists() and (managed / document.name).exists()
        controller.remove_panel(virtual.config["id"])
        assert icon.exists() and file_attributes(icon) & HIDE_BITS == original
        controller.undo_last()
        assert virtual.config["id"] in controller.panels
        assert file_attributes(icon) & HIDE_BITS == HIDE_BITS
    finally:
        QMessageBox.question = question
        controller.groups.restore_for_exit()
        controller.events.close()
        controller.center.music.bridge.close()

print("scene switching and organizing undo passed")
