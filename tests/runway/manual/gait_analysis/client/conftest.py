"""Apply the desktop theme to gait layout tests that construct the workspace directly."""

import pytest
from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.app.app_bootstrap import apply_theme_mode
from dlc_gait_assembly.shared.client.theme import theme_application_state as theme


@pytest.fixture(scope="module")
def themed_gait_application():
    app = QApplication.instance() or QApplication([])
    font, palette, stylesheet = app.font(), app.palette(), app.styleSheet()
    dark_mode = theme.IS_DARK
    apply_theme_mode(app, None, "light")
    yield app
    theme.set_dark_mode(dark_mode)
    app.setFont(font)
    app.setPalette(palette)
    app.setStyleSheet(stylesheet)
