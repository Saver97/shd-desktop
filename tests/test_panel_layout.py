"""Panel snapping without involving the Windows desktop."""

from PySide6.QtCore import QPoint, QRect, QSize

from shd_desktop.desktop.panel_layout import snap_position, snap_size


assert snap_position(QRect(206, 100, 100, 100), [QRect(0, 100, 200, 100)]) == QPoint(208, 100)
assert snap_position(QRect(4, 206, 100, 100), [QRect(0, 0, 200, 200)]) == QPoint(0, 208)
assert snap_position(QRect(500, 500, 100, 100), [QRect(0, 0, 200, 200)]) == QPoint(500, 500)
assert snap_size(QRect(300, 300, 350, 297), [QRect(660, 300, 200, 300)],
                 QSize(300, 210)) == QSize(352, 300)
assert snap_size(QRect(300, 300, 400, 400), [QRect(660, 300, 200, 300)],
                 QSize(300, 210)) == QSize(400, 400)
print("panel snapping passed")
