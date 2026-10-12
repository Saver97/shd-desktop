"""Shortcut labels and shell icon engines must stay off the paint path."""

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QIconEngine, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import app as desktop


calls = []


class ShellIcon(QIconEngine):
    def clone(self):
        return ShellIcon()

    def pixmap(self, size, mode, state):
        calls.append(size.width())
        pixmap = QPixmap(size)
        pixmap.fill(QColor("orange"))
        return pixmap


application = QApplication([])
original_icon = desktop.icon_for_item
desktop.icon_for_item = lambda path, provider: QIcon(ShellIcon())
try:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        folder = root / "files"
        folder.mkdir()
        for name in ("Game.lnk", "Site.URL", "Notes.txt", "Archive.tar.gz"):
            (folder / name).write_text("test")
        store = desktop.ConfigStore(root / "config")
        config = {"id": "icons", "path": str(folder), "collapsed": True,
                  "w": 500, "h": 55, "expanded_h": 420}
        store.data["panels"] = [config]
        panel = desktop.FolderPanel(config, store, lambda _: None)
        labels = {panel.list.item(i).text() for i in range(panel.list.count())}
        assert labels == {"Game", "Site", "Notes.txt", "Archive.tar.gz"}, labels
        for i in range(panel.list.count()):
            item = panel.list.item(i)
            assert Path(item.data(Qt.UserRole)).exists()
            assert item.toolTip() == item.data(Qt.UserRole)
        assert len(calls) == 4, calls
        panel.show()
        for _ in range(3):
            panel.toggle_collapsed()
            QTest.qWait(25)
            panel.list.viewport().repaint()
            panel.toggle_collapsed()
            application.processEvents()
        panel.toggle_view()
        panel.toggle_collapsed()
        QTest.qWait(25)
        panel.list.viewport().repaint()
        panel.refresh()
        application.processEvents()
        assert len(calls) == 4, "paint/expand/view/refresh queried the shell engine again"
        (folder / "Game.lnk").write_text("updated shortcut")
        panel.refresh()
        assert len(calls) == 5, "changed shortcut should invalidate its cached bitmap"
        panel.close()
finally:
    desktop.icon_for_item = original_icon
print("shortcut labels and rendered icon cache passed")
