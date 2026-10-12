"""Read current folder panel definitions; benchmark isolated windows and config."""

import copy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import ConfigStore, FolderList, FolderPanel
from shd_desktop.ui.theme import STYLE


app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 10))
app.setStyleSheet(STYLE)
paints = []
original_paint = FolderList.paintEvent


def timed_paint(self, event):
    start = perf_counter()
    original_paint(self, event)
    paints.append((perf_counter() - start) * 1000)


FolderList.paintEvent = timed_paint
source = Path(os.environ["LOCALAPPDATA"]) / "SHDDesktop" / "layout.json"
configs = copy.deepcopy(json.loads(source.read_text(encoding="utf8"))["panels"])
configs = [config for config in configs if config.get("path") and config.get("kind") != "virtual"]
with TemporaryDirectory() as temp:
    store = ConfigStore(Path(temp))
    store.data["panels"] = configs
    panels = []
    for index, config in enumerate(configs):
        config.update(collapsed=True, x=100 + index * 30, y=100 + index * 70, h=55)
        panel = FolderPanel(config, store, lambda _: None)
        panel.show()
        panels.append(panel)
    app.processEvents()
    for index, panel in enumerate(panels):
        for turn in range(3):
            paints.clear()
            start = perf_counter()
            panel.toggle_collapsed()
            click = (perf_counter() - start) * 1000
            start = perf_counter()
            app.processEvents()
            events = (perf_counter() - start) * 1000
            QTest.qWait(40)
            print(f"panel={index} items={panel.list.count()} turn={turn} "
                  f"click={click:.1f}ms events={events:.1f}ms "
                  f"paints={[round(value, 1) for value in paints]}")
            panel.toggle_collapsed()
            app.processEvents()
            QTest.qWait(40)
    for panel in panels:
        panel.close()
