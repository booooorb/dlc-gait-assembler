"""Translate selected theme colors into the application Qt palette."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


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
    import dlc_gait_assembly.shared.client.theme.theme_application_state as theme

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
