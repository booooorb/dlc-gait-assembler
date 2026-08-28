from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

NOTO_SANS_FONT_DIR = Path(__file__).with_name("fonts")
NOTO_SANS_FONT_FILES = (
    "NotoSans-Regular.ttf",
    "NotoSans-Medium.ttf",
    "NotoSans-SemiBold.ttf",
    "NotoSans-Bold.ttf",
)


@lru_cache(maxsize=1)
def _noto_sans_family() -> str:
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
    return QFont(_noto_sans_family())


def interface_font() -> QFont:
    """Return the bundled Noto Sans family while retaining the platform UI size."""
    general = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font = QFont(_noto_sans_family())
    if general.pointSizeF() > 0:
        font.setPointSizeF(general.pointSizeF())
    return font


def color(value: str, alpha: int | None = None) -> QColor:
    qcolor = QColor(value)
    if alpha is not None:
        qcolor.setAlpha(alpha)
    return qcolor


def mix_hex(foreground_hex: str, background_hex: str, background_weight: float) -> str:
    foreground = QColor(foreground_hex)
    background = QColor(background_hex)
    weight = max(0.0, min(1.0, background_weight))
    red = round(foreground.red() * (1.0 - weight) + background.red() * weight)
    green = round(foreground.green() * (1.0 - weight) + background.green() * weight)
    blue = round(foreground.blue() * (1.0 - weight) + background.blue() * weight)
    return f"#{red:02x}{green:02x}{blue:02x}"


def application_palette() -> QPalette:
    from dlc_gait_assembly.gui import theme

    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: theme.BACKGROUND,
        QPalette.ColorRole.WindowText: theme.TEXT,
        QPalette.ColorRole.Base: theme.SURFACE,
        QPalette.ColorRole.AlternateBase: theme.PANEL,
        QPalette.ColorRole.ToolTipBase: theme.SURFACE,
        QPalette.ColorRole.ToolTipText: theme.TEXT,
        QPalette.ColorRole.Text: theme.TEXT,
        QPalette.ColorRole.Button: theme.SURFACE,
        QPalette.ColorRole.ButtonText: theme.TEXT,
        QPalette.ColorRole.BrightText: theme.STATUS_ERROR,
        QPalette.ColorRole.Highlight: theme.SOFT,
        QPalette.ColorRole.HighlightedText: theme.TEXT,
        QPalette.ColorRole.Link: theme.TOOL_1,
        QPalette.ColorRole.PlaceholderText: theme.CONNECTOR,
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))
    disabled_text = QColor(mix_hex(theme.CONNECTOR, theme.BACKGROUND, 0.32))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(theme.PANEL))
    return palette
