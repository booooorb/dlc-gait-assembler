from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette


@dataclass(frozen=True)
class Palette:
    name: str
    tool_1: str
    tool_2: str
    tool_3: str
    number_icon: str


@dataclass(frozen=True)
class ThemeColors:
    background: str
    surface: str
    panel: str
    soft: str
    border: str
    text: str
    secondary_text: str
    primary: str
    primary_text: str
    canvas: str
    canvas_text: str
    status_ready: str
    status_running: str
    status_error: str


PALE_GARDEN = Palette(
    name="Pale Garden",
    tool_1="#F1F3E0",
    tool_2="#D2DCB6",
    tool_3="#A1BC98",
    number_icon="#778873",
)

PASTEL_SKY = Palette(
    name="Pastel Sky",
    tool_1="#D9F9DF",
    tool_2="#AEE2FF",
    tool_3="#B5BAFF",
    number_icon="#9FA1FF",
)

HIGH_VARIETY = Palette(
    name="High Variety",
    tool_1="#2EC4B6",
    tool_2="#3A86FF",
    tool_3="#FF6B6B",
    number_icon="#845EC2",
)

PRIMARY_TOOLS = Palette(
    name="Field Notes",
    tool_1="#5E6F60",
    tool_2="#7A684D",
    tool_3="#80594B",
    number_icon="#555750",
)

DARK_TOOLS = Palette(
    name="Field Notes Dark",
    tool_1="#91A58F",
    tool_2="#B49A6A",
    tool_3="#B77C69",
    number_icon="#B7B9B0",
)

LIGHT_COLORS = ThemeColors(
    background="#F1F1EF",
    surface="#FFFFFF",
    panel="#E7E7E3",
    soft="#D8D8D2",
    border="#BDBEB8",
    text="#282925",
    secondary_text="#686A63",
    primary="#30312D",
    primary_text="#FFFFFF",
    canvas="#272925",
    canvas_text="#F1F1EF",
    status_ready="#5C7553",
    status_running="#7A684D",
    status_error="#9B4D3F",
)

DARK_COLORS = ThemeColors(
    background="#181916",
    surface="#22231F",
    panel="#2D2E29",
    soft="#3A3B35",
    border="#51534B",
    text="#ECEDE7",
    secondary_text="#B3B5AC",
    primary="#50534B",
    primary_text="#F5F5F1",
    canvas="#10110F",
    canvas_text="#ECEDE7",
    status_ready="#8EA486",
    status_running="#B49A6A",
    status_error="#D68B7B",
)

# Change these assignments while testing palettes.
AESTHETIC_PALETTE = PASTEL_SKY
LOGO_SURFACE = "#FFFFFF"
LOGO_BORDER = "#D6D7D0"


def set_dark_mode(enabled: bool) -> None:
    global IS_DARK, ACTIVE_PALETTE
    global BACKGROUND, SURFACE, PANEL, SOFT, BORDER, TEXT, CONNECTOR
    global PRIMARY, PRIMARY_TEXT, CANVAS, CANVAS_TEXT
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
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: BACKGROUND,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: SURFACE,
        QPalette.ColorRole.AlternateBase: PANEL,
        QPalette.ColorRole.ToolTipBase: SURFACE,
        QPalette.ColorRole.ToolTipText: TEXT,
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: SURFACE,
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.BrightText: STATUS_ERROR,
        QPalette.ColorRole.Highlight: SOFT,
        QPalette.ColorRole.HighlightedText: TEXT,
        QPalette.ColorRole.Link: TOOL_1,
        QPalette.ColorRole.PlaceholderText: CONNECTOR,
    }
    for role, value in roles.items():
        palette.setColor(role, QColor(value))

    disabled_text = QColor(mix_hex(CONNECTOR, BACKGROUND, 0.32))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_text)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, QColor(PANEL))
    return palette


def application_stylesheet() -> str:
    return stylesheet(
        """
        QToolTip {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            padding: 4px 6px;
        }
        QMenuBar, QMenu {
            background: {theme.SURFACE};
            color: {theme.TEXT};
        }
        QMenuBar::item:selected, QMenu::item:selected {
            background: {theme.PANEL};
            color: {theme.TEXT};
        }
        QMenu::separator {
            background: {theme.BORDER};
            height: 1px;
            margin: 4px 8px;
        }
        QDialog, QMessageBox {
            background: {theme.BACKGROUND};
            color: {theme.TEXT};
        }
        QCheckBox, QRadioButton {
            color: {theme.TEXT};
            spacing: 6px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            background: {theme.SURFACE};
            border: 1px solid {theme.BORDER};
            border-radius: 2px;
        }
        QCheckBox::indicator:checked {
            background: {theme.TOOL_1};
            border-color: {theme.TOOL_1};
        }
        QRadioButton::indicator {
            width: 14px;
            height: 14px;
            background: {theme.SURFACE};
            border: 1px solid {theme.BORDER};
            border-radius: 7px;
        }
        QRadioButton::indicator:checked {
            background: {theme.TOOL_1};
            border: 3px solid {theme.SURFACE};
        }
        QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
            background: {theme.PANEL};
            border-color: {theme.BORDER};
        }
        QComboBox QAbstractItemView {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            selection-background-color: {theme.SOFT};
            selection-color: {theme.TEXT};
        }
        QPushButton:focus, QToolButton:focus,
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QListWidget:focus {
            border: 1px solid {theme.TOOL_1};
        }
        """
    )


def stylesheet(template: str) -> str:
    return (
        template.replace("{theme.mix_hex(theme.SOFT, theme.SURFACE, 0.35)}", mix_hex(SOFT, SURFACE, 0.35))
        .replace("{theme.BACKGROUND}", BACKGROUND)
        .replace("{theme.SURFACE}", SURFACE)
        .replace("{theme.PANEL}", PANEL)
        .replace("{theme.SOFT}", SOFT)
        .replace("{theme.BORDER}", BORDER)
        .replace("{theme.ACCENT}", ACCENT)
        .replace("{theme.TEXT}", TEXT)
        .replace("{theme.CONNECTOR}", CONNECTOR)
        .replace("{theme.PRIMARY}", PRIMARY)
        .replace("{theme.PRIMARY_TEXT}", PRIMARY_TEXT)
        .replace("{theme.CANVAS}", CANVAS)
        .replace("{theme.CANVAS_TEXT}", CANVAS_TEXT)
        .replace("{theme.LOGO_SURFACE}", LOGO_SURFACE)
        .replace("{theme.LOGO_BORDER}", LOGO_BORDER)
        .replace("{theme.STATUS_READY}", STATUS_READY)
        .replace("{theme.STATUS_RUNNING}", STATUS_RUNNING)
        .replace("{theme.STATUS_ERROR}", STATUS_ERROR)
        .replace("{theme.STATUS_OTHER}", STATUS_OTHER)
        .replace("{theme.TOOL_1}", TOOL_1)
        .replace("{theme.TOOL_2}", TOOL_2)
        .replace("{theme.TOOL_3}", TOOL_3)
        .replace("{theme.NUMBER_ICON}", NUMBER_ICON)
        .replace("{theme.LIGHT}", LIGHT)
        .replace("{theme.PALE}", PALE)
        .replace("{theme.MID}", MID)
        .replace("{theme.DARK}", DARK)
    )
