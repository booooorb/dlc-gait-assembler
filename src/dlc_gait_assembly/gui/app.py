from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.main_window import MainWindow


TOOLTIP_WAKEUP_SPEEDUP = 2


class FastToolTipStyle(QProxyStyle):
    def styleHint(self, hint, option=None, widget=None, returnData=None) -> int:
        value = super().styleHint(hint, option, widget, returnData)
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return max(1, value // TOOLTIP_WAKEUP_SPEEDUP)
        return value

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
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


def main() -> int:
    app = QApplication(sys.argv)
    fast_tooltip_style = FastToolTipStyle(app.style())
    app.setStyle(fast_tooltip_style)
    app._fast_tooltip_style = fast_tooltip_style
    window: MainWindow | None = None

    def apply_system_theme(color_scheme: Qt.ColorScheme) -> None:
        theme.set_dark_mode(color_scheme == Qt.ColorScheme.Dark)
        app.setPalette(theme.application_palette())
        app.setStyleSheet(theme.application_stylesheet())
        if window is not None:
            window.apply_theme()

    apply_system_theme(app.styleHints().colorScheme())
    window = MainWindow()
    app.styleHints().colorSchemeChanged.connect(apply_system_theme)
    window.show()
    return app.exec()
