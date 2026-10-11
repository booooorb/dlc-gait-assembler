"""Register and select fonts bundled with the installed application."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QFont, QFontDatabase

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path

NOTO_SANS_FONT_DIR = resource_path("fonts")
NOTO_SANS_FONT_FILES = ("NotoSans-Regular.ttf", "NotoSans-Medium.ttf", "NotoSans-SemiBold.ttf", "NotoSans-Bold.ttf")


@lru_cache(maxsize=1)
def noto_sans_family() -> str:
    """Register the bundled static Noto Sans fonts and return their Qt family name."""
    family = ""
    for filename in NOTO_SANS_FONT_FILES:
        path = NOTO_SANS_FONT_DIR / filename
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            raise RuntimeError(f"Qt could not register the bundled font: {path}")
        families = QFontDatabase.applicationFontFamilies(font_id)
        if not families:
            raise RuntimeError(f"Qt registered no font family for: {path}")
        if not family:
            family = families[0]
    return family


def fixed_width_font() -> QFont:
    """Return Noto Sans for text surfaces that historically requested a fixed font."""
    return QFont(noto_sans_family())


def interface_font() -> QFont:
    """Return the bundled Noto Sans family while retaining the platform UI size."""
    general = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font = QFont(noto_sans_family())
    if general.pointSizeF() > 0:
        font.setPointSizeF(general.pointSizeF())
    return font
