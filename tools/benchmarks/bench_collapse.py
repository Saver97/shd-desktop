"""Measure folder panel fold/unfold latency with a populated icon list."""

from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app import ConfigStore, FolderPanel
from shd_desktop.ui.theme import STYLE


app = QApplication([])
app.setFont(QFont("Microsoft YaHei UI", 10))
app.setStyleSheet(STYLE)
with TemporaryDirectory() as temp:
    root = Path(temp)
    folder = root / "icons"
    folder.mkdir()
    for index in range(160):
        (folder / f"shortcut-{index:03}.url").write_text(
            "[InternetShortcut]\nURL=https://example.com\n"
            f"IconFile={Path(__file__).resolve().parents[2] / 'assets' / 'tray.png'}\n"
        )
    store = ConfigStore(root / "config")
    config = {"id": "benchmark", "kind": "folder", "path": str(folder),
              "title": "折叠性能", "x": 150, "y": 150, "w": 500, "h": 420,
              "expanded_h": 420, "collapsed": False}
    store.data["panels"].append(config)
    panel = FolderPanel(config, store, lambda _: None)
    panel.show()
    app.processEvents()
    assert panel.list.count() == 160

    phases = {"apply": [], "save": [], "restack": []}
    original_apply = panel.apply_collapsed
    original_save = panel.save_geometry

    def timed_apply():
        start = perf_counter()
        original_apply()
        phases["apply"].append((perf_counter() - start) * 1000)

    def timed_save(*args, **kwargs):
        start = perf_counter()
        original_save(*args, **kwargs)
        phases["save"].append((perf_counter() - start) * 1000)

    def timed_restack():
        start = perf_counter()
        panel.lower() if config["collapsed"] else panel.raise_()
        phases["restack"].append((perf_counter() - start) * 1000)

    panel.apply_collapsed = timed_apply
    panel.save_geometry = timed_save
    panel.layer_callback = timed_restack

    measurements = {"fold": [], "unfold": [], "fold_paint": [], "unfold_paint": []}
    for index in range(12):
        for operation in ("fold", "unfold"):
            start = perf_counter()
            panel.toggle_collapsed()
            click_ms = (perf_counter() - start) * 1000
            start = perf_counter()
            app.processEvents()
            paint_ms = (perf_counter() - start) * 1000
            if index >= 2:
                measurements[operation].append(click_ms)
                measurements[f"{operation}_paint"].append(paint_ms)
    print(" ".join(f"{key}_median={median(values):.1f}ms max={max(values):.1f}ms"
                   for key, values in measurements.items()))
    print(" ".join(f"{key}_median={median(values):.1f}ms max={max(values):.1f}ms"
                   for key, values in phases.items()))
    panel.close()
