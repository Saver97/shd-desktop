"""Rasterize the SHD vector mark and build a multi-size Windows ICO."""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parent / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"Cannot render icon at {size}px")
    return bytes(data)


def build() -> None:
    app = QGuiApplication([])
    renderer = QSvgRenderer(str(ROOT / "app-icon.svg"))
    if not renderer.isValid():
        raise RuntimeError("Invalid app-icon.svg")
    pictures = [(size, render_png(renderer, size)) for size in SIZES]
    (ROOT / "app-icon.png").write_bytes(pictures[-1][1])
    (ROOT / "tray.png").write_bytes(next(data for size, data in pictures if size == 64))
    offset = 6 + 16 * len(pictures)
    entries = []
    for size, data in pictures:
        width = 0 if size == 256 else size
        entries.append(struct.pack("<BBBBHHII", width, width, 0, 0, 1, 32,
                                   len(data), offset))
        offset += len(data)
    ico = struct.pack("<HHH", 0, 1, len(pictures)) + b"".join(entries)
    ico += b"".join(data for _, data in pictures)
    (ROOT / "app.ico").write_bytes(ico)
    app.quit()


if __name__ == "__main__":
    build()
