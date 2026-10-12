"""Small code-drawn weather symbols matching the SHD orange/steel palette."""

from __future__ import annotations

from math import cos, pi, sin

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap


ORANGE = QColor("#FF8328")
WHITE = QColor("#E8E6E3")
BLUE = QColor("#65BCE8")


def weather_kind(code: int) -> str:
    if code == 0:
        return "sun"
    if code in (1, 2, 3):
        return "cloud"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or 85 <= code <= 86:
        return "snow"
    if code >= 95:
        return "storm"
    return "cloud"


def weather_pixmap(code: int, size: int = 64) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 64, size / 64)
    kind = weather_kind(code)
    if kind in ("sun", "cloud"):
        painter.setPen(QPen(ORANGE, 2.5, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(28, 25), 10, 10)
        for index in range(8):
            angle = index * pi / 4
            painter.drawLine(QPointF(28 + 15 * cos(angle), 25 + 15 * sin(angle)),
                             QPointF(28 + 20 * cos(angle), 25 + 20 * sin(angle)))
    if kind != "sun":
        cloud = QPainterPath()
        cloud.moveTo(13, 44)
        cloud.cubicTo(7, 44, 7, 34, 15, 33)
        cloud.cubicTo(17, 20, 34, 20, 38, 31)
        cloud.cubicTo(52, 26, 58, 44, 47, 45)
        cloud.closeSubpath()
        painter.setBrush(QColor("#344655"))
        painter.setPen(QPen(WHITE, 2.4))
        painter.drawPath(cloud)
    if kind == "fog":
        painter.setPen(QPen(BLUE, 2.1, Qt.SolidLine, Qt.RoundCap))
        for y in (48, 54, 60):
            painter.drawLine(16, y, 48, y)
    elif kind == "rain":
        painter.setPen(QPen(BLUE, 2.6, Qt.SolidLine, Qt.RoundCap))
        for x in (22, 33, 44):
            painter.drawLine(x, 49, x - 3, 58)
    elif kind == "snow":
        painter.setPen(QPen(BLUE, 2.1, Qt.SolidLine, Qt.RoundCap))
        for x in (22, 34, 46):
            painter.drawLine(x - 3, 54, x + 3, 54)
            painter.drawLine(x, 51, x, 57)
    elif kind == "storm":
        painter.setPen(QPen(ORANGE, 2.0))
        painter.setBrush(ORANGE)
        bolt = QPainterPath()
        bolt.moveTo(32, 46)
        bolt.lineTo(25, 56)
        bolt.lineTo(32, 55)
        bolt.lineTo(29, 64)
        bolt.lineTo(41, 51)
        bolt.lineTo(34, 52)
        bolt.closeSubpath()
        painter.drawPath(bolt)
    painter.end()
    return pixmap
