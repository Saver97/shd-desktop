"""Keep desktop windows reachable when the monitor layout changes."""

from __future__ import annotations

from PySide6.QtCore import QRect


def visible_geometry(saved: QRect, screens: list[QRect]) -> QRect:
    """Return a temporary on-screen geometry without changing the saved one."""
    if not screens:
        return QRect(saved)
    for screen in screens:
        overlap = saved.intersected(screen)
        if (overlap.width() >= min(120, saved.width())
                and overlap.height() >= min(55, saved.height())
                and screen.contains(saved.topLeft())):
            return QRect(saved)
    center = saved.center()
    screen = min(screens, key=lambda area: (
        max(area.left() - center.x(), 0, center.x() - area.right()) ** 2
        + max(area.top() - center.y(), 0, center.y() - area.bottom()) ** 2))
    width = min(saved.width(), screen.width())
    height = min(saved.height(), screen.height())
    x = min(max(saved.x(), screen.left()), screen.right() - width + 1)
    y = min(max(saved.y(), screen.top()), screen.bottom() - height + 1)
    return QRect(x, y, width, height)
