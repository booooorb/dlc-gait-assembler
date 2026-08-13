from dlc_gait_assembly.gui.theme.palette import (
    NOTO_SANS_FONT_DIR,
    NOTO_SANS_FONT_FILES,
    color,
    fixed_width_font,
    interface_font,
    mix_hex,
)
from dlc_gait_assembly.gui.theme.tokens import (
    AESTHETIC_PALETTE,
    BRAND_SURFACE,
    DARK_COLORS,
    DARK_TOOLS,
    HIGH_VARIETY,
    LIGHT_COLORS,
    PALE_GARDEN,
    PASTEL_SKY,
    PRIMARY_TOOLS,
    Palette,
    ThemeColors,
)


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

    # Backward-compatible aliases for call sites that think in light-to-dark swatches.
    LIGHT = BACKGROUND
    PALE = SURFACE
    MID = ACCENT
    DARK = TEXT

set_dark_mode(False)

from dlc_gait_assembly.gui.theme.palette import application_palette  # noqa: E402
from dlc_gait_assembly.gui.theme.styles import (  # noqa: E402
    application_stylesheet,
    stylesheet,
    workspace_stylesheet,
)

__all__ = [
    "ACCENT",
    "ACTIVE_PALETTE",
    "AESTHETIC_PALETTE",
    "BACKGROUND",
    "BORDER",
    "BRAND_SURFACE",
    "CANVAS",
    "CANVAS_TEXT",
    "CONNECTOR",
    "DARK",
    "DARK_COLORS",
    "DARK_TOOLS",
    "HIGH_VARIETY",
    "NOTO_SANS_FONT_DIR",
    "NOTO_SANS_FONT_FILES",
    "IS_DARK",
    "LIGHT",
    "LIGHT_COLORS",
    "MID",
    "NUMBER_ICON",
    "PALE",
    "PALE_GARDEN",
    "PANEL",
    "PASTEL_SKY",
    "PRIMARY",
    "PRIMARY_HOVER",
    "PRIMARY_TEXT",
    "PRIMARY_TOOLS",
    "Palette",
    "SOFT",
    "STATUS_ERROR",
    "STATUS_OTHER",
    "STATUS_READY",
    "STATUS_RUNNING",
    "STEP_NUMBER_COLORS",
    "SURFACE",
    "TEXT",
    "TOOL_1",
    "TOOL_2",
    "TOOL_3",
    "ThemeColors",
    "application_palette",
    "application_stylesheet",
    "color",
    "fixed_width_font",
    "interface_font",
    "mix_hex",
    "set_dark_mode",
    "stylesheet",
    "workspace_stylesheet",
]
