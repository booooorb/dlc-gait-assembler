"""Knee-correction stick-plot preview widget."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from dlc_gait_assembly.gui import theme


class KneeStickplotPreview(QWidget):
    def __init__(self):
        super().__init__()
        self._hip: tuple[float, float] | None = None
        self._ankle: tuple[float, float] | None = None
        self._old_knee: tuple[float, float] | None = None
        self._new_knee: tuple[float, float] | None = None
        self._background_frame: QImage | None = None
        self._correction_status = ""
        self._has_frame = False
        self._empty_message = "Generate a frame preview"

    def set_empty_message(self, message: str) -> None:
        self._empty_message = message
        if not self._has_frame:
            self.update()

    def set_points(
        self,
        hip: tuple[float, float] | None,
        ankle: tuple[float, float] | None,
        old_knee: tuple[float, float] | None,
        new_knee: tuple[float, float] | None,
        correction_status: str = "Corrected",
        background_frame: QImage | None = None,
    ) -> None:
        self._hip = hip
        self._ankle = ankle
        self._old_knee = old_knee
        self._new_knee = new_knee
        self._background_frame = background_frame
        self._correction_status = correction_status
        self._has_frame = True
        self.update()

    def clear_points(self) -> None:
        self._hip = None
        self._ankle = None
        self._old_knee = None
        self._new_knee = None
        self._background_frame = None
        self._correction_status = ""
        self._has_frame = False
        self.update()

    def _draw_background_frame(
        self,
        painter: QPainter,
        points: list[tuple[float, float]],
    ) -> tuple[QRectF, QRectF] | None:
        if self._background_frame is None or self._background_frame.isNull():
            return None
        image = self._background_frame
        source = self._frame_crop_rect(points, image.width(), image.height())
        scale = min(self.width() / source.width(), self.height() / source.height())
        width = max(1.0, source.width() * scale)
        height = max(1.0, source.height() * scale)
        left = (self.width() - width) / 2
        top = (self.height() - height) / 2
        target = QRectF(left, top, width, height)
        painter.drawImage(target, image, source)
        painter.fillRect(target, QColor(0, 0, 0, 30))
        return target, source

    def _frame_crop_rect(
        self,
        points: list[tuple[float, float]],
        image_width: int,
        image_height: int,
    ) -> QRectF:
        finite_points = [
            (float(x), float(y))
            for x, y in points
            if x == x and y == y
        ]
        if not finite_points:
            return QRectF(0.0, 0.0, float(image_width), float(image_height))

        xs = [point[0] for point in finite_points]
        ys = [point[1] for point in finite_points]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        limb_span = max(span_x, span_y)
        padding = max(40.0, limb_span * 0.75)
        crop_width = max(span_x + padding * 2, 160.0)
        crop_height = max(span_y + padding * 2, 140.0)
        crop_width = min(float(image_width), crop_width)
        crop_height = min(float(image_height), crop_height)
        center_x = min(max((min_x + max_x) / 2, crop_width / 2), image_width - crop_width / 2)
        center_y = min(max((min_y + max_y) / 2, crop_height / 2), image_height - crop_height / 2)
        left = min(max(0.0, center_x - crop_width / 2), image_width - crop_width)
        top = min(max(0.0, center_y - crop_height / 2), image_height - crop_height)
        return QRectF(left, top, crop_width, crop_height)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.CANVAS))
        available_points = [
            point
            for point in (self._hip, self._ankle, self._old_knee, self._new_knee)
            if point is not None
        ]
        image_mapping = self._draw_background_frame(painter, available_points)
        if not self._has_frame:
            painter.setPen(QColor(theme.CONNECTOR))
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self._empty_message)
            return
        missing = []
        if self._hip is None:
            missing.append("Hip unavailable (NaN coordinates)")
        if self._ankle is None:
            missing.append("Ankle unavailable (NaN coordinates)")
        if self._old_knee is None:
            missing.append("Old knee unavailable (missing/NaN coordinates)")
        if missing:
            painter.setPen(QColor("#aaa6a0"))
            for index, message in enumerate(missing):
                painter.drawText(
                    self.rect().adjusted(10, 8 + index * 16, -10, -8),
                    Qt.AlignTop | Qt.AlignRight,
                    message,
                )
        if self._correction_status and self._correction_status != "Corrected":
            painter.setPen(QColor(theme.STATUS_ERROR))
            painter.drawText(
                self.rect().adjusted(10, 8, -10, -8),
                Qt.AlignTop | Qt.AlignLeft,
                f"Retained: {self._correction_status}",
            )
        if self._hip is None or self._ankle is None:
            painter.setPen(QColor(theme.CONNECTOR))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Stickplot unavailable without both hip and ankle coordinates",
            )
            return

        margin = 42
        if image_mapping is not None:
            image_rect, source_rect = image_mapping

            def mapped(point: tuple[float, float]) -> tuple[int, int]:
                return (
                    int(
                        image_rect.left()
                        + (point[0] - source_rect.left())
                        * image_rect.width()
                        / max(1.0, source_rect.width())
                    ),
                    int(
                        image_rect.top()
                        + (point[1] - source_rect.top())
                        * image_rect.height()
                        / max(1.0, source_rect.height())
                    ),
                )

        else:
            xs = [point[0] for point in available_points]
            ys = [point[1] for point in available_points]
            x_span = max(max(xs) - min(xs), 1.0)
            y_span = max(max(ys) - min(ys), 1.0)
            draw_width = max(1, self.width() - margin * 2)
            draw_height = max(1, self.height() - margin * 2 - 24)
            scale = min(draw_width / x_span, draw_height / y_span)
            x_offset = margin + (draw_width - x_span * scale) / 2
            y_offset = margin + (draw_height - y_span * scale) / 2

            def mapped(point: tuple[float, float]) -> tuple[int, int]:
                return (
                    int(x_offset + (point[0] - min(xs)) * scale),
                    int(y_offset + (point[1] - min(ys)) * scale),
                )

        hip = mapped(self._hip)
        ankle = mapped(self._ankle)
        old_knee = mapped(self._old_knee) if self._old_knee is not None else None
        new_knee = mapped(self._new_knee) if self._new_knee is not None else None

        if old_knee is not None:
            old_pen = QPen(QColor("#aaa6a0"), 2, Qt.DashLine)
            painter.setPen(old_pen)
            painter.drawLine(*hip, *old_knee)
            painter.drawLine(*old_knee, *ankle)
            painter.setBrush(QColor("#aaa6a0"))
            painter.drawEllipse(old_knee[0] - 4, old_knee[1] - 4, 8, 8)

        chain_color = QColor(theme.CANVAS_TEXT)
        if new_knee is not None:
            painter.setPen(QPen(chain_color, 4))
            painter.drawLine(*hip, *new_knee)
            painter.drawLine(*new_knee, *ankle)
        painter.setPen(QPen(chain_color, 2))
        painter.setBrush(chain_color)
        for point in (hip, ankle):
            painter.drawEllipse(point[0] - 6, point[1] - 6, 12, 12)
        if new_knee is not None:
            corrected_color = QColor(theme.STATUS_READY)
            painter.setPen(QPen(corrected_color, 2))
            painter.setBrush(corrected_color)
            painter.drawEllipse(new_knee[0] - 8, new_knee[1] - 8, 16, 16)

        painter.setPen(QColor(theme.CANVAS_TEXT))
        painter.drawText(hip[0] + 8, hip[1] - 8, "Hip")
        painter.drawText(ankle[0] + 8, ankle[1] - 8, "Ankle")
        if old_knee is not None:
            painter.setPen(QColor("#8e8a84"))
            painter.drawText(old_knee[0] + 7, old_knee[1] + 14, "Old knee")
        if new_knee is not None:
            painter.setPen(QColor(theme.STATUS_READY))
            painter.drawText(new_knee[0] + 9, new_knee[1] - 9, "Corrected knee")

        legend_y = self.height() - 12
        painter.setPen(QPen(QColor("#aaa6a0"), 2, Qt.DashLine))
        painter.drawLine(margin, legend_y, margin + 22, legend_y)
        painter.setPen(QColor(theme.CONNECTOR))
        painter.drawText(margin + 28, legend_y + 4, "Original")
        painter.setPen(QPen(chain_color, 4))
        painter.drawLine(margin + 105, legend_y, margin + 127, legend_y)
        painter.setPen(QColor(theme.CANVAS_TEXT))
        painter.drawText(margin + 133, legend_y + 4, "Corrected")
