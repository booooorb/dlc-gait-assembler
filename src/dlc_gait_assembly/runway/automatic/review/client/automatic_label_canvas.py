"""Draw editable marker overlays with Napari-style pointer modes."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsScene, QGraphicsView, QRubberBand


def marker_color(index):
    return QColor.fromHsv((index * 137 + 38) % 360, 175, 250)


class LabelCanvas(QGraphicsView):
    positions_changed = Signal(object)
    selection_changed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(QGraphicsScene(parent), parent)
        self.setMinimumSize(420, 290)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor("#181b1e"))
        self._image = self.scene().addPixmap(QPixmap())
        self._items = {}
        self._selected = set()
        self._offset = (0, 0)
        self._mode = "select"
        self._space = False
        self._start = QPoint()
        self._gesture = None
        self._origins = {}
        self._rubber = QRubberBand(QRubberBand.Rectangle, self.viewport())
        self.active_marker = None
        self._set_cursor()

    def set_frame(self, pixmap, points, markers, offset, *, fit=False):
        self._gesture = None
        self._origins.clear()
        self._rubber.hide()
        self._set_cursor()
        size_changed = pixmap.size() != self._image.pixmap().size()
        self._image.setPixmap(pixmap)
        self.scene().setSceneRect(self._image.boundingRect())
        self._offset = offset
        self.set_points(points, markers)
        if fit or size_changed:
            self.fit_frame()

    def fit_frame(self):
        if not self._image.pixmap().isNull():
            self.fitInView(self._image, Qt.KeepAspectRatio)

    def set_points(self, points, markers):
        for item in self._items.values():
            self.scene().removeItem(item)
        self._items.clear()
        for index, marker in enumerate(markers):
            if marker not in points:
                continue
            item = QGraphicsEllipseItem(-5.5, -5.5, 11, 11)
            item.setFlag(QGraphicsItem.ItemIgnoresTransformations)
            item.setBrush(QBrush(marker_color(index)))
            item.setToolTip(" / ".join(marker))
            x, y = points[marker]
            item.setPos(x + self._offset[0], y + self._offset[1])
            item.setZValue(1)
            self.scene().addItem(item)
            self._items[marker] = item
        self.set_selected(self._selected)

    def set_selected(self, markers):
        self._selected = set(markers)
        for marker, item in self._items.items():
            selected = marker in self._selected
            item.setPen(QPen(QColor("#ffffff" if selected else "#232529"), 2.5 if selected else 1.5))
            item.setZValue(2 if selected else 1)

    def set_mode(self, mode):
        self._mode = mode
        self._set_cursor()

    def _set_cursor(self):
        cursor = Qt.OpenHandCursor if self._space or self._mode == "pan" else Qt.CrossCursor
        self.viewport().setCursor(cursor)

    def wheelEvent(self, event):
        if self._image.pixmap().isNull():
            return
        steps = event.angleDelta().y() / 120 or event.pixelDelta().y() / 45
        factor = 1.2**steps
        if 0.015 < self.transform().m11() * factor < 40:
            self.scale(factor, factor)
        event.accept()

    def hold_pan(self, pressed):
        self._space = pressed
        self._set_cursor()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._image.pixmap().isNull():
            super().mousePressEvent(event)
            return
        self.setFocus()
        self._start = event.position().toPoint()
        if self._space or self._mode == "pan":
            self._gesture = "pan"
            self._scroll_start = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if self._mode == "add":
            position = self.mapToScene(self._start)
            if self.active_marker is not None and self.sceneRect().contains(position):
                self.positions_changed.emit({self.active_marker: self._coordinate(position)})
            return
        self._extend = bool(event.modifiers() & (Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier))
        hit = self.itemAt(self._start)
        marker = next((key for key, item in self._items.items() if item == hit), None)
        if marker is None:
            self._gesture = "box"
            self._before_box = self._selected.copy() if self._extend else set()
            self._rubber.setGeometry(QRect(self._start, self._start))
            self._rubber.show()
            if not self._extend:
                self._select(set())
            return

        if self._extend:
            self._select(self._selected ^ {marker})
        elif marker not in self._selected:
            self._select({marker})
        self._gesture = "move"
        self._origins = {key: item.pos() for key, item in self._items.items() if key in self._selected}

    def mouseMoveEvent(self, event):
        position = event.position().toPoint()
        if self._gesture == "pan":
            delta = position - self._start
            self.horizontalScrollBar().setValue(self._scroll_start[0] - delta.x())
            self.verticalScrollBar().setValue(self._scroll_start[1] - delta.y())
        elif self._gesture == "box":
            box = QRect(self._start, position).normalized()
            self._rubber.setGeometry(box)
            self._select(
                self._before_box
                | {marker for marker, item in self._items.items() if box.contains(self.mapFromScene(item.pos()))}
            )
        elif self._gesture == "move" and self._origins:
            delta = self.mapToScene(position) - self.mapToScene(self._start)
            origins = tuple(self._origins.values())
            dx = max(
                -min(p.x() for p in origins), min(delta.x(), self.sceneRect().width() - 1 - max(p.x() for p in origins))
            )
            dy = max(
                -min(p.y() for p in origins),
                min(delta.y(), self.sceneRect().height() - 1 - max(p.y() for p in origins)),
            )
            for marker, origin in self._origins.items():
                self._items[marker].setPos(origin + QPointF(dx, dy))
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or self._gesture is None:
            super().mouseReleaseEvent(event)
            return
        gesture, self._gesture = self._gesture, None
        self._rubber.hide()
        self._set_cursor()
        if gesture == "move":
            changed = {
                marker: self._coordinate(self._items[marker].pos())
                for marker, origin in self._origins.items()
                if self._items[marker].pos() != origin
            }
            if changed:
                self.positions_changed.emit(changed)
        self._origins = {}

    def _select(self, markers):
        self.set_selected(markers)
        self.selection_changed.emit(markers)

    def _coordinate(self, position):
        return position.x() - self._offset[0], position.y() - self._offset[1]
