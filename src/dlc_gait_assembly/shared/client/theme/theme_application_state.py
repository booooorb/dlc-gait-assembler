"""Track the selected light/dark appearance for shared presentation controls."""

from __future__ import annotations

from dlc_gait_assembly.shared.client.theme.theme_color_tokens import (
    DARK_COLORS,
    DARK_TOOLS,
    LIGHT_COLORS,
    PRIMARY_TOOLS,
)
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex


def set_dark_mode(enabled: bool) -> None:
    global IS_DARK, ACTIVE_PALETTE
    global BACKGROUND, SURFACE, PANEL, SOFT, BORDER, TEXT, CONNECTOR
    global PRIMARY, PRIMARY_HOVER, PRIMARY_TEXT, CANVAS, CANVAS_TEXT
    global STATUS_READY, STATUS_RUNNING, STATUS_ERROR, STATUS_OTHER
    global TOOL_1, TOOL_2, TOOL_3, NUMBER_ICON, STEP_NUMBER_COLORS, ACCENT
    global LIGHT, PALE, MID, DARK
    IS_DARK = bool(enabled)
    colors = DARK_COLORS if IS_DARK else LIGHT_COLORS
    ACTIVE_PALETTE = DARK_TOOLS if IS_DARK else PRIMARY_TOOLS
    BACKGROUND = colors.background
    SURFACE = colors.surface
    PANEL = colors.panel
    SOFT = colors.soft
    BORDER = colors.border
    TEXT = colors.text
    CONNECTOR = colors.secondary_text
    PRIMARY = colors.primary
    PRIMARY_HOVER = mix_hex(PRIMARY, SURFACE, 0.12)
    PRIMARY_TEXT = colors.primary_text
    CANVAS = colors.canvas
    CANVAS_TEXT = colors.canvas_text
    STATUS_READY = colors.status_ready
    STATUS_RUNNING = colors.status_running
    STATUS_ERROR = colors.status_error
    STATUS_OTHER = colors.secondary_text
    TOOL_1 = ACTIVE_PALETTE.tool_1
    TOOL_2 = ACTIVE_PALETTE.tool_2
    TOOL_3 = ACTIVE_PALETTE.tool_3
    NUMBER_ICON = ACTIVE_PALETTE.number_icon
    STEP_NUMBER_COLORS = (NUMBER_ICON,) * 5
    ACCENT = BORDER
    LIGHT = BACKGROUND
    PALE = SURFACE
    MID = ACCENT
    DARK = TEXT


set_dark_mode(False)
