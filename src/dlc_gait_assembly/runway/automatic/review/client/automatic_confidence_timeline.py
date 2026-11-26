"""Plot per-frame tracking confidence on a scrubber for the entire recording."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSlider, QStyle

from dlc_gait_assembly.shared.client.theme import theme_application_state as theme


class ConfidenceTimeline(QSlider):
    frame_requested = Signal(int)

    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setLayoutDirection(Qt.LeftToRight)
        self.setFixedHeight(94)
        self.setAccessibleName("Recording timeline")
        self.setAccessibleDescription("Scrub through every frame with the mouse or arrow keys.")
        self.setToolTip("Click or drag to inspect any frame. Use the arrow keys to step one frame at a time.")
        self._frame_count = 0
        self._fps = 0.0
        self._scores = None
        self._current_frame = None
        self.valueChanged.connect(self.frame_requested.emit)

    def set_recording(self, frame_count, fps):
        self._frame_count = frame_count
        self._fps = fps
        self._current_frame = None
        self.setRange(0, max(0, frame_count - 1))
        self.setValue(0)
        self.setPageStep(max(1, frame_count // 20))
        self.setEnabled(frame_count > 0)
        self.update()

    def set_scores(self, scores):
        self._scores = scores
        self.update()

    def set_current_frame(self, frame):
        self._current_frame = frame
        if frame is not None:
            self.setValue(frame)
        self.update()

    def _plot_rect(self):
        inset = self.fontMetrics().horizontalAdvance("100%") + 9
        return QRectF(inset, 8, max(1, self.width() - inset - 10), self.height() - 42)

    def paintEvent(self, _event):
        plot = self._plot_rect()
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(plot, QColor(theme.SURFACE))
            for confidence in (1.0, 0.5, 0.0):
                y = plot.bottom() - confidence * plot.height()
                painter.setPen(QColor(theme.BORDER))
                painter.drawLine(QLineF(plot.left(), y, plot.right(), y))
                painter.setPen(QColor(theme.CONNECTOR))
                label = QRectF(0, y - 8, plot.left() - 6, 16)
                painter.drawText(label, Qt.AlignRight | Qt.AlignVCenter, f"{confidence:.0%}")

            if self._scores is not None and self._frame_count:
                self._draw_scores(painter, plot)
            elif self._frame_count:
                painter.drawText(plot, Qt.AlignCenter, "Confidence unavailable")

            track_y = plot.bottom() + 9
            painter.setPen(QPen(QColor(theme.CONNECTOR), 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QLineF(plot.left(), track_y, plot.right(), track_y))
            if self._current_frame is not None:
                self._draw_playhead(painter, plot, track_y)

            if self._frame_count:
                labels = QRectF(plot.left(), track_y + 4, plot.width(), 18)
                start, end = "Frame 1", f"Frame {self._frame_count:,}"
                if self._fps > 0:
                    start, end = "0 s", f"{(self._frame_count - 1) / self._fps:,.2f} s"
                painter.setPen(QColor(theme.CONNECTOR))
                painter.drawText(labels, Qt.AlignLeft | Qt.AlignVCenter, start)
                if self._frame_count > 1:
                    painter.drawText(labels, Qt.AlignRight | Qt.AlignVCenter, end)

            if self.hasFocus():
                painter.setPen(QPen(QColor(theme.PRIMARY), 1, Qt.DotLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def _draw_scores(self, painter, plot):
        scores = self._scores
        columns = max(1, int(plot.width()))
        color = QColor(theme.STATUS_READY)
        if len(scores) > columns:
            # Preserve short dips when multiple video frames share a screen pixel.
            starts = np.arange(columns, dtype=np.int64) * len(scores) // columns
            highs = np.maximum.reduceat(scores, starts)
            scores = np.minimum.reduceat(scores, starts)
            x_values = np.linspace(plot.left(), plot.right(), len(scores))
            span_color = QColor(color)
            span_color.setAlpha(95)
            painter.setPen(span_color)
            painter.drawLines([
                QLineF(x, plot.bottom() - low * plot.height(), x, plot.bottom() - high * plot.height())
                for x, low, high in zip(x_values, scores, highs, strict=True)
            ])

        points = QPolygonF([
            QPointF(x, plot.bottom() - confidence * plot.height())
            for x, confidence in zip(np.linspace(plot.left(), plot.right(), len(scores)), scores, strict=True)
        ])
        painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if len(points) == 1:
            painter.drawPoint(points[0])
        else:
            painter.drawPolyline(points)

    def _draw_playhead(self, painter, plot, track_y):
        offset = QStyle.sliderPositionFromValue(0, self.maximum(), self._current_frame, round(plot.width()))
        x = plot.left() + offset
        color = QColor(theme.PRIMARY)
        painter.setPen(color)
        painter.drawLine(QLineF(x, plot.top(), x, track_y))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(x, track_y), 4, 4)
        if self._scores is not None:
            y = plot.bottom() - self._scores[self._current_frame] * plot.height()
            painter.setPen(QColor(theme.SURFACE))
            painter.drawEllipse(QPointF(x, y), 3, 3)

    def _frame_at(self, event):
        plot = self._plot_rect()
        width = round(plot.width())
        position = max(0, min(width, round(event.position().x() - plot.left())))
        return QStyle.sliderValueFromPosition(0, self.maximum(), position, width)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.setSliderDown(True)
        frame = self._frame_at(event)
        if frame == self.value():
            self.frame_requested.emit(frame)
        else:
            self.setSliderPosition(frame)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setSliderPosition(self._frame_at(event))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.isSliderDown() and event.button() == Qt.LeftButton:
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
