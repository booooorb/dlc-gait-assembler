"""Register and select fonts bundled with the installed application."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path

GEIST_FONT_PATH = resource_path("fonts", "Geist.ttf")


@lru_cache(maxsize=1)
def geist_family() -> str:
    """Register the bundled variable Geist font and return its Qt family name."""
    font_id = QFontDatabase.addApplicationFont(str(GEIST_FONT_PATH))
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    if not families:
        raise RuntimeError(f"Qt could not register the bundled font: {GEIST_FONT_PATH}")
    return families[0]


def fixed_width_font() -> QFont:
    """Return Geist for text surfaces that historically requested a fixed font."""
    return QFont(geist_family())


def interface_font() -> QFont:
    """Return Geist while retaining the platform UI size."""
    general = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font = QFont(geist_family())
    if general.pointSizeF() > 0:
        font.setPointSizeF(general.pointSizeF())
    return font
