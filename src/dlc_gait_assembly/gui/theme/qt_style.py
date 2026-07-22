from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import QProxyStyle, QStyle

from dlc_gait_assembly.gui import theme

TOOLTIP_WAKEUP_SPEEDUP = 2


class FastToolTipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None) -> int:
        value = super().styleHint(hint, option, widget, returnData)
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return max(1, value // TOOLTIP_WAKEUP_SPEEDUP)
        return value

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            self._draw_checkbox(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorRadioButton:
            self._draw_radio_button(option, painter)
            return

        arrows = {
            QStyle.PrimitiveElement.PE_IndicatorArrowDown: "down",
            QStyle.PrimitiveElement.PE_IndicatorSpinDown: "down",
            QStyle.PrimitiveElement.PE_IndicatorArrowUp: "up",
            QStyle.PrimitiveElement.PE_IndicatorSpinUp: "up",
            QStyle.PrimitiveElement.PE_IndicatorArrowLeft: "left",
            QStyle.PrimitiveElement.PE_IndicatorArrowRight: "right",
        }
        direction = arrows.get(element)
        if direction is None:
            super().drawPrimitive(element, option, painter, widget)
            return

        rect = option.rect
        center = rect.center()
        x = float(center.x())
        y = float(center.y())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(option.palette.color(QPalette.ColorRole.ButtonText), 1.5))
        if direction == "down":
            points = (QPointF(x - 3.0, y - 1.5), QPointF(x, y + 1.5), QPointF(x + 3.0, y - 1.5))
        elif direction == "up":
            points = (QPointF(x - 3.0, y + 1.5), QPointF(x, y - 1.5), QPointF(x + 3.0, y + 1.5))
        elif direction == "left":
            points = (QPointF(x + 1.5, y - 3.0), QPointF(x - 1.5, y), QPointF(x + 1.5, y + 3.0))
        else:
            points = (QPointF(x - 1.5, y - 3.0), QPointF(x + 1.5, y), QPointF(x - 1.5, y + 3.0))
        painter.drawPolyline(points)
        painter.restore()

    @staticmethod
    def _draw_checkbox(option, painter: QPainter) -> None:
        state = option.state
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        checked = bool(state & QStyle.StateFlag.State_On)
        partial = bool(state & QStyle.StateFlag.State_NoChange)
        active = checked or partial
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        focused = bool(state & QStyle.StateFlag.State_HasFocus)

        border = theme.TOOL_1 if focused or active else theme.CONNECTOR if hovered else theme.BORDER
        fill = theme.TOOL_1 if active else theme.SURFACE if enabled else theme.PANEL
        rect = option.rect.adjusted(1, 1, -1, -1)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(border), 1.2))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, 2.5, 2.5)

        if active:
            mark_color = theme.CANVAS if theme.IS_DARK else theme.PRIMARY_TEXT
            painter.setPen(QPen(QColor(mark_color), 1.8))
            center = rect.center()
            if partial:
                painter.drawLine(rect.left() + 3, center.y(), rect.right() - 3, center.y())
            else:
                painter.drawPolyline(
                    (
                        QPointF(rect.left() + 3.0, center.y()),
                        QPointF(center.x() - 0.5, rect.bottom() - 3.0),
                        QPointF(rect.right() - 2.5, rect.top() + 3.0),
                    )
                )
        painter.restore()

    @staticmethod
    def _draw_radio_button(option, painter: QPainter) -> None:
        state = option.state
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        checked = bool(state & QStyle.StateFlag.State_On)
        hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        focused = bool(state & QStyle.StateFlag.State_HasFocus)
        border = theme.TOOL_1 if checked or focused else theme.CONNECTOR if hovered else theme.BORDER
        rect = option.rect.adjusted(1, 1, -1, -1)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(border), 1.2))
        painter.setBrush(QColor(theme.SURFACE if enabled else theme.PANEL))
        painter.drawEllipse(rect)
        if checked:
            dot = rect.adjusted(4, 4, -4, -4)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.TOOL_1))
            painter.drawEllipse(dot)
        painter.restore()


