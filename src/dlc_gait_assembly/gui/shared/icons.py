"""Small, dependency-free interface icons drawn with Qt."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def interface_icon(name: str, color: str, *, size: int = 18) -> QIcon:
    """Return a crisp, theme-aware line icon for a common interface action."""

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    scale = size / 18.0
    accent = QColor(color)
    painter.scale(scale, scale)
    painter.setPen(QPen(accent, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)

    if name == "gear":
        painter.drawEllipse(QRectF(4.2, 4.2, 9.6, 9.6))
        painter.drawEllipse(QRectF(7.1, 7.1, 3.8, 3.8))
        for index in range(8):
            angle = math.radians(index * 45)
            inner = QPointF(9 + math.cos(angle) * 5.1, 9 + math.sin(angle) * 5.1)
            outer = QPointF(9 + math.cos(angle) * 7.0, 9 + math.sin(angle) * 7.0)
            painter.drawLine(inner, outer)
    elif name == "trash":
        painter.drawRoundedRect(QRectF(4.2, 5.5, 9.6, 10.0), 1.2, 1.2)
        painter.drawLine(QPointF(2.8, 4.1), QPointF(15.2, 4.1))
        painter.drawLine(QPointF(6.7, 2.3), QPointF(11.3, 2.3))
        painter.drawLine(QPointF(7.1, 8.0), QPointF(7.1, 13.0))
        painter.drawLine(QPointF(10.9, 8.0), QPointF(10.9, 13.0))
    elif name == "clear":
        painter.drawLine(QPointF(2.8, 4.6), QPointF(9.1, 4.6))
        painter.drawLine(QPointF(2.8, 9.0), QPointF(8.0, 9.0))
        painter.drawLine(QPointF(2.8, 13.4), QPointF(9.1, 13.4))
        painter.drawLine(QPointF(10.7, 7.2), QPointF(15.2, 11.7))
        painter.drawLine(QPointF(15.2, 7.2), QPointF(10.7, 11.7))
    elif name == "plus":
        painter.drawEllipse(QRectF(2.1, 2.1, 13.8, 13.8))
        painter.drawLine(QPointF(9.0, 5.3), QPointF(9.0, 12.7))
        painter.drawLine(QPointF(5.3, 9.0), QPointF(12.7, 9.0))
    elif name == "document":
        path = QPainterPath()
        path.moveTo(4.0, 2.2)
        path.lineTo(10.8, 2.2)
        path.lineTo(14.0, 5.4)
        path.lineTo(14.0, 15.8)
        path.lineTo(4.0, 15.8)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(10.8, 2.2), QPointF(10.8, 5.4))
        painter.drawLine(QPointF(10.8, 5.4), QPointF(14.0, 5.4))
        painter.drawLine(QPointF(6.5, 9.0), QPointF(11.5, 9.0))
        painter.drawLine(QPointF(6.5, 12.0), QPointF(11.5, 12.0))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(2.2, 5.0)
        path.lineTo(7.2, 5.0)
        path.lineTo(8.7, 7.0)
        path.lineTo(15.8, 7.0)
        path.lineTo(14.6, 14.7)
        path.lineTo(3.4, 14.7)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "play":
        painter.drawEllipse(QRectF(1.9, 1.9, 14.2, 14.2))
        path = QPainterPath()
        path.moveTo(7.2, 5.4)
        path.lineTo(12.7, 9.0)
        path.lineTo(7.2, 12.6)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawPath(path)
    elif name == "upload":
        painter.drawRoundedRect(QRectF(3.0, 11.0, 12.0, 4.0), 1.0, 1.0)
        painter.drawLine(QPointF(9.0, 12.2), QPointF(9.0, 3.0))
        painter.drawLine(QPointF(5.7, 6.3), QPointF(9.0, 3.0))
        painter.drawLine(QPointF(12.3, 6.3), QPointF(9.0, 3.0))
    elif name == "download":
        painter.drawRoundedRect(QRectF(3.0, 11.0, 12.0, 4.0), 1.0, 1.0)
        painter.drawLine(QPointF(9.0, 3.0), QPointF(9.0, 12.0))
        painter.drawLine(QPointF(5.7, 8.7), QPointF(9.0, 12.0))
        painter.drawLine(QPointF(12.3, 8.7), QPointF(9.0, 12.0))
    elif name == "stack":
        for top, inset in ((2.4, 0.0), (6.4, 0.8), (10.4, 1.6)):
            painter.drawRoundedRect(
                QRectF(2.4 + inset, top, 13.2 - inset * 2, 4.2), 1.2, 1.2
            )
    elif name == "external":
        painter.drawRoundedRect(QRectF(2.5, 5.0, 10.5, 10.5), 1.2, 1.2)
        painter.drawLine(QPointF(8.2, 9.8), QPointF(15.0, 3.0))
        painter.drawLine(QPointF(10.2, 3.0), QPointF(15.0, 3.0))
        painter.drawLine(QPointF(15.0, 3.0), QPointF(15.0, 7.8))
    elif name == "sliders":
        for y, knob_x in ((4.0, 6.0), (9.0, 12.0), (14.0, 8.5)):
            painter.drawLine(QPointF(2.5, y), QPointF(15.5, y))
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(knob_x, y), 1.8, 1.8)
            painter.setBrush(Qt.NoBrush)
    elif name == "check":
        painter.drawEllipse(QRectF(1.9, 1.9, 14.2, 14.2))
        painter.drawLine(QPointF(5.1, 9.0), QPointF(7.8, 11.7))
        painter.drawLine(QPointF(7.8, 11.7), QPointF(13.1, 6.2))
    elif name == "eye":
        path = QPainterPath()
        path.moveTo(1.8, 9.0)
        path.cubicTo(5.0, 3.8, 13.0, 3.8, 16.2, 9.0)
        path.cubicTo(13.0, 14.2, 5.0, 14.2, 1.8, 9.0)
        path.closeSubpath()
        painter.drawPath(path)
        painter.setBrush(accent)
        painter.drawEllipse(QPointF(9.0, 9.0), 2.1, 2.1)
    else:
        painter.end()
        raise ValueError(f"Unknown interface icon: {name}")

    painter.end()
    return QIcon(pixmap)
