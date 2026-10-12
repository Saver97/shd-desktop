"""Focused file operation check; run with QT_QPA_PLATFORM=offscreen."""

from pathlib import Path
from tempfile import TemporaryDirectory
from PySide6.QtCore import QPointF, QMimeData, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from app import ConfigStore, FolderPanel


app = QApplication([])
with TemporaryDirectory() as tmp:
    root = Path(tmp)
    source = root / "source"
    target = root / "target"
    source.mkdir()
    target.mkdir()
    store = ConfigStore(root / "config")
    config = {"id": "test", "path": str(target), "view": "list"}
    store.data["panels"] = [config]
    panel = FolderPanel(config, store, lambda _: None)
    panel.refresh = lambda: None

    captured = []
    panel.receive_drop = lambda paths, position: captured.append((paths, position)) or True
    payload = QMimeData()
    payload.setUrls([QUrl.fromLocalFile(str(source / "copy.txt"))])
    drop = QDropEvent(QPointF(12, 18), Qt.CopyAction, payload,
                      Qt.LeftButton, Qt.NoModifier)
    panel.list.dropEvent(drop)
    assert captured and captured[0][0] == [source / "copy.txt"]
    assert drop.isAccepted()

    for name, move, expected_in_source in (
        ("copy.txt", False, True), ("move.txt", True, False)
    ):
        (source / name).write_text(name)
        skipped, errors = panel.apply_drop([source / name], move)
        assert not skipped and not errors
        assert (source / name).exists() is expected_in_source
        assert (target / name).read_text() == name

    panel.close()

print("copy and move passed")
