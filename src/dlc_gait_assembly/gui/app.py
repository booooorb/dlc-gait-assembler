from __future__ import annotations

import sys

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.main_window import MainWindow
from dlc_gait_assembly.gui.theme.qt_style import FastToolTipStyle

THEME_SETTING_KEY = "appearance/theme"
WINDOW_GEOMETRY_SETTING_KEY = "window/geometry"
THEME_MODES = {"light", "dark"}


def resolved_theme_mode(settings: QSettings, system_scheme: Qt.ColorScheme) -> str:
    saved_mode = str(settings.value(THEME_SETTING_KEY, "")).strip().lower()
    if saved_mode in THEME_MODES:
        return saved_mode
    return "dark" if system_scheme == Qt.ColorScheme.Dark else "light"


def apply_theme_mode(app: QApplication, window: MainWindow | None, mode: str) -> None:
    if mode not in THEME_MODES:
        raise ValueError(f"Unknown theme mode: {mode}")
    theme.set_dark_mode(mode == "dark")
    app.setFont(theme.interface_font())
    app.setPalette(theme.application_palette())
    app.setStyleSheet(theme.application_stylesheet())
    if window is not None:
        window.set_theme_mode(mode)
        window.apply_theme()


def restore_window_geometry(window: MainWindow, settings: QSettings) -> bool:
    geometry = settings.value(WINDOW_GEOMETRY_SETTING_KEY)
    if geometry is None:
        return False
    return window.restoreGeometry(geometry)


def save_window_geometry(window: MainWindow, settings: QSettings) -> None:
    settings.setValue(WINDOW_GEOMETRY_SETTING_KEY, window.saveGeometry())
    settings.sync()


def main() -> int:
    app = QApplication(sys.argv)
    fast_tooltip_style = FastToolTipStyle(app.style())
    app.setStyle(fast_tooltip_style)
    app._fast_tooltip_style = fast_tooltip_style
    settings = QSettings("DLC Gait Assembler", "DLC Gait Assembler")
    initial_theme_mode = resolved_theme_mode(settings, app.styleHints().colorScheme())
    apply_theme_mode(app, None, initial_theme_mode)
    window = MainWindow(initial_theme_mode=initial_theme_mode)
    restore_window_geometry(window, settings)

    def select_theme_mode(mode: str) -> None:
        settings.setValue(THEME_SETTING_KEY, mode)
        settings.sync()
        apply_theme_mode(app, window, mode)

    window.theme_mode_requested.connect(select_theme_mode)
    app.aboutToQuit.connect(lambda: save_window_geometry(window, settings))
    window.show()
    return app.exec()
