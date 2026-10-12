"""Icons reflow when a frame is resized, without toggling its view mode."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QSize
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import ConfigStore, FolderPanel


def row_count(panel):
    return len({panel.list.visualItemRect(panel.list.item(index)).top()
                for index in range(panel.list.count())})


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    folder = root / "files"
    folder.mkdir()
    for index in range(20):
        (folder / f"file-{index:02}.txt").write_text("sample")
    store = ConfigStore(root / "config")
    config = {"id": "reflow", "kind": "folder", "path": str(folder), "title": "测试",
              "view": "grid", "x": 40, "y": 40, "w": 350, "h": 420}
    store.data["panels"] = [config]
    panel = FolderPanel(config, store, lambda _: None)
    panel.show()
    app.processEvents()
    narrow = row_count(panel)
    panel.resize_to(QSize(panel.width() + 300, panel.height()))
    QTest.qWait(40)
    during = row_count(panel)
    assert during < narrow, (narrow, during)
    panel.finish_resize()
    app.processEvents()
    wide = row_count(panel)
    assert wide < narrow, (narrow, wide)
    resize_calls = []
    original_resize = panel.resize_to
    def counted_resize(size):
        resize_calls.append(size.width())
        original_resize(size)
    panel.resize_to = counted_resize
    for width in range(500, 560):
        panel.grip._pending_size = QSize(width, panel.height())
        if not panel.grip._resize_timer.isActive():
            panel.grip._resize_timer.start()
    QTest.qWait(35)
    assert resize_calls == [559], resize_calls
    refreshes = []
    panel._refresh_timer.timeout.connect(lambda: refreshes.append(True))
    for _ in range(20):
        panel.watcher.directoryChanged.emit(str(folder))
    QTest.qWait(160)
    assert len(refreshes) == 1
    panel.close()

print("panel resize reflow passed")
