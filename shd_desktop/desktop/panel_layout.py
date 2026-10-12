"""Small geometry helpers for desktop panel placement."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize


def snap_position(rect: QRect, peers: list[QRect], threshold: int = 18,
                  gap: int = 8) -> QPoint:
    """Snap near a peer edge while preserving the panel's size."""
    horizontal: list[tuple[int, int]] = []
    vertical: list[tuple[int, int]] = []
    for peer in peers:
        vertical_overlap = rect.top() <= peer.bottom() + threshold and rect.bottom() >= peer.top() - threshold
        horizontal_overlap = rect.left() <= peer.right() + threshold and rect.right() >= peer.left() - threshold
        if vertical_overlap:
            for target in (peer.right() + 1 + gap, peer.left() - gap - rect.width(),
                           peer.left(), peer.right() + 1 - rect.width()):
                distance = abs(rect.left() - target)
                if distance <= threshold:
                    horizontal.append((distance, target))
        if horizontal_overlap:
            for target in (peer.bottom() + 1 + gap, peer.top() - gap - rect.height(),
                           peer.top(), peer.bottom() + 1 - rect.height()):
                distance = abs(rect.top() - target)
                if distance <= threshold:
                    vertical.append((distance, target))
    x = min(horizontal)[1] if horizontal else rect.left()
    y = min(vertical)[1] if vertical else rect.top()
    return QPoint(x, y)


def snap_size(rect: QRect, peers: list[QRect], minimum: QSize,
              threshold: int = 16, gap: int = 8) -> QSize:
    """Snap the right and bottom resize edges, keeping the top-left corner fixed."""
    widths: list[tuple[int, int]] = []
    heights: list[tuple[int, int]] = []
    for peer in peers:
        reach = threshold + gap
        vertical_overlap = rect.top() <= peer.bottom() + reach and rect.bottom() >= peer.top() - reach
        horizontal_overlap = rect.left() <= peer.right() + reach and rect.right() >= peer.left() - reach
        if vertical_overlap:
            for target in (peer.left() - gap - rect.left(), peer.right() - rect.left() + 1):
                distance = abs(rect.width() - target)
                if target >= minimum.width() and distance <= threshold:
                    widths.append((distance, target))
        if horizontal_overlap:
            for target in (peer.top() - gap - rect.top(), peer.bottom() - rect.top() + 1):
                distance = abs(rect.height() - target)
                if target >= minimum.height() and distance <= threshold:
                    heights.append((distance, target))
    width = min(widths)[1] if widths else rect.width()
    height = min(heights)[1] if heights else rect.height()
    return QSize(width, height)
