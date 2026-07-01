from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, QSettings, Qt
from PySide6.QtGui import QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.main_window import MainWindow


TOOLTIP_WAKEUP_SPEEDUP = 2
THEME_SETTING_KEY = "appearance/theme"
THEME_MODES = {"light", "dark"}


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


def resolved_theme_mode(settings: QSettings, system_scheme: Qt.ColorScheme) -> str:
    saved_mode = str(settings.value(THEME_SETTING_KEY, "")).strip().lower()
    if saved_mode in THEME_MODES:
        return saved_mode
    return "dark" if system_scheme == Qt.ColorScheme.Dark else "light"


def apply_theme_mode(app: QApplication, window: MainWindow | None, mode: str) -> None:
    if mode not in THEME_MODES:
        raise ValueError(f"Unknown theme mode: {mode}")
    theme.set_dark_mode(mode == "dark")
    app.setPalette(theme.application_palette())
    app.setStyleSheet(theme.application_stylesheet())
    if window is not None:
        window.set_theme_mode(mode)
        window.apply_theme()


def main() -> int:
    app = QApplication(sys.argv)
    fast_tooltip_style = FastToolTipStyle(app.style())
    app.setStyle(fast_tooltip_style)
    app._fast_tooltip_style = fast_tooltip_style
    settings = QSettings("DLC Gait Assembler", "DLC Gait Assembler")
    initial_theme_mode = resolved_theme_mode(settings, app.styleHints().colorScheme())
    apply_theme_mode(app, None, initial_theme_mode)
    window = MainWindow(initial_theme_mode=initial_theme_mode)

    def select_theme_mode(mode: str) -> None:
        settings.setValue(THEME_SETTING_KEY, mode)
        settings.sync()
        apply_theme_mode(app, window, mode)

    window.theme_mode_requested.connect(select_theme_mode)
    window.show()
    return app.exec()
