"""Native Windows check for expanded frame order and delayed resize writes."""

from pathlib import Path
from tempfile import TemporaryDirectory

import win32gui
from PySide6.QtCore import QEventLoop, QPoint, QSize, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import ConfigStore, Controller


app = QApplication([])
with TemporaryDirectory() as temp:
    root = Path(temp)
    store = ConfigStore(root / "config")
    saves = []
    original_save = store.save

    def save():
        saves.append(True)
        original_save()

    store.save = save
    store.data["panels"] = [
        {"id": "a", "path": str(root), "title": "展开", "x": 300, "y": 300,
         "w": 350, "h": 300, "expanded_h": 300, "collapsed": False},
        {"id": "b", "path": str(root), "title": "折叠", "x": 300, "y": 300,
         "w": 350, "h": 55, "expanded_h": 300, "collapsed": True},
    ]
    controller = Controller(app, store)
    expanded = controller.panels["a"]
    collapsed = controller.panels["b"]
    app.processEvents()
    saves.clear()
    expanded.toggle_collapsed()
    assert expanded.height() == 55 and not expanded.list.isVisible()
    expanded.toggle_collapsed()
    assert expanded.height() == 300 and expanded.list.isVisible()
    assert not saves, "fold/unfold click should not wait for a disk write"
    app.processEvents()
    order = []
    win32gui.EnumWindows(lambda hwnd, _: order.append(hwnd), None)
    assert order.index(int(expanded.winId())) < order.index(int(collapsed.winId()))

    def assert_front(front, behind):
        windows = []
        win32gui.EnumWindows(lambda hwnd, _: windows.append(hwnd), None)
        assert windows.index(int(front.winId())) < windows.index(int(behind.winId()))

    collapsed.toggle_collapsed()
    app.processEvents()
    assert_front(collapsed, expanded), "newly expanded frame must be on top"
    QTest.mousePress(expanded.header, Qt.LeftButton)
    QTest.mouseRelease(expanded.header, Qt.LeftButton)
    app.processEvents()
    assert_front(expanded, collapsed), "clicked frame must come forward"
    QTest.mousePress(collapsed.list.viewport(), Qt.LeftButton, pos=QPoint(10, 10))
    QTest.mouseRelease(collapsed.list.viewport(), Qt.LeftButton, pos=QPoint(10, 10))
    app.processEvents()
    assert_front(collapsed, expanded), "clicking an icon area must bring the frame forward"
    controller.restack_panels()
    assert_front(collapsed, expanded), "Explorer or scene restack must keep the active frame"
    collapsed.toggle_collapsed()
    assert_front(expanded, collapsed), "expanded frames must remain above collapsed frames"

    collapsed.toggle_collapsed()
    collapsed.move(660, 300)
    expanded.resize_to(QSize(350, 297))
    assert expanded.size() == QSize(352, 300), f"resize result {expanded.size()} at {expanded.pos()}"
    assert expanded._snap_active
    expanded.finish_resize()
    assert not expanded._snap_active
    expanded.resize(350, 300)
    collapsed.toggle_collapsed()
    collapsed.move(300, 300)

    expanded.drag_to(QPoint(310, 365))
    assert expanded.pos() == QPoint(300, 363), "snap should appear while dragging"
    assert expanded._snap_active
    expanded.drag_to(QPoint(350, 410))
    assert expanded.pos() == QPoint(350, 410), "moving away should release the snap"
    expanded.finish_move()
    assert not expanded._snap_active

    expanded._save_timer.stop()
    collapsed._save_timer.stop()
    saves.clear()
    for width in range(351, 371):
        expanded.resize(width, 300)
        app.processEvents()
    assert not saves, "resize should not write the layout for every pixel"
    loop = QEventLoop()
    QTimer.singleShot(400, loop.quit)
    loop.exec()
    assert len(saves) == 1
    collapsed.close()
    expanded.close()
    controller.events.close()
    controller.center.music.bridge.close()
print("panel order and resize debounce passed")
