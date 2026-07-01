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
    name="Paper + Rust",
    tool_1="#6E7658",
    tool_2="#8C7044",
    tool_3="#985D46",
    number_icon="#64574A",
)

DARK_TOOLS = Palette(
    name="Paper + Rust Dark",
    tool_1="#9FAC89",
    tool_2="#C2A16C",
    tool_3="#C9866D",
    number_icon="#C5B9AB",
)

LIGHT_COLORS = ThemeColors(
    background="#F5F1EA",
    surface="#FFFDF9",
    panel="#EAE2D8",
    soft="#DCCDBE",
    border="#C4B6A6",
    text="#342E29",
    secondary_text="#776C62",
    primary="#57483D",
    primary_text="#FFFFFF",
    canvas="#27231F",
    canvas_text="#FAF5ED",
    status_ready="#64745C",
    status_running="#957346",
    status_error="#A4533F",
)

DARK_COLORS = ThemeColors(
    background="#1C1917",
    surface="#28231F",
    panel="#342E29",
    soft="#463C34",
    border="#65584C",
    text="#F2ECE4",
    secondary_text="#C2B5A7",
    primary="#665548",
    primary_text="#FFF9F2",
    canvas="#100E0D",
    canvas_text="#F2ECE4",
    status_ready="#91A286",
    status_running="#C09A63",
    status_error="#D7836D",
)

# Change these assignments while testing palettes.
AESTHETIC_PALETTE = PRIMARY_TOOLS
BRAND_SURFACE = LIGHT_COLORS.surface


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
        QWidget {
            font-size: 13px;
        }
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
        QPushButton, QToolButton {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 3px;
            padding: 6px 10px;
            min-height: 18px;
        }
        QPushButton:hover, QToolButton:hover {
            background: {theme.PANEL};
            border-color: {theme.TEXT};
        }
        QPushButton:disabled, QToolButton:disabled {
            background: {theme.PANEL};
            color: {theme.CONNECTOR};
        }
        QPushButton#PrimaryButton, QPushButton#ExportButton {
            background: {theme.PRIMARY};
            border-color: {theme.PRIMARY};
            color: {theme.PRIMARY_TEXT};
            font-weight: 600;
        }
        QPushButton#PrimaryButton:hover, QPushButton#ExportButton:hover {
            background: {theme.SOFT};
            border-color: {theme.TEXT};
            color: {theme.TEXT};
        }
        QPushButton#PrimaryButton:disabled, QPushButton#ExportButton:disabled {
            background: {theme.PANEL};
            border-color: {theme.BORDER};
            color: {theme.CONNECTOR};
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
        QSpinBox, QDoubleSpinBox, QListWidget, QTreeWidget, QTableWidget {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 2px;
            padding: 4px 6px;
            selection-background-color: {theme.SOFT};
            selection-color: {theme.TEXT};
        }
        QGroupBox {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 2px;
            margin-top: 14px;
            padding: 14px 10px 10px 10px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 7px;
            padding: 0 3px;
            background: {theme.BACKGROUND};
            color: {theme.TEXT};
        }
        QTabWidget::pane {
            background: {theme.SURFACE};
            border: 1px solid {theme.BORDER};
            border-radius: 0;
            top: -1px;
        }
        QTabBar::tab {
            background: transparent;
            color: {theme.CONNECTOR};
            border: 0;
            border-bottom: 2px solid transparent;
            padding: 7px 10px;
        }
        QTabBar::tab:hover {
            color: {theme.TEXT};
            background: {theme.PANEL};
        }
        QTabBar::tab:selected {
            color: {theme.TEXT};
            border-bottom-color: {theme.TOOL_1};
            font-weight: 600;
        }
        QHeaderView::section {
            background: {theme.PANEL};
            color: {theme.TEXT};
            border: 0;
            border-right: 1px solid {theme.BORDER};
            border-bottom: 1px solid {theme.BORDER};
            padding: 6px 8px;
            font-weight: 600;
            text-align: left;
        }
        QProgressBar {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 2px;
            min-height: 16px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: {theme.TOOL_1};
            border-radius: 1px;
        }
        QScrollArea {
            border: 0;
            background: transparent;
        }
        QSplitter::handle {
            background: {theme.BORDER};
            width: 1px;
            height: 1px;
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


def workspace_stylesheet(root_object_name: str, extra: str = "") -> str:
    """Shared visual contract for every full-size tool workspace."""

    base = """
        QWidget#ROOT_OBJECT {
            background: {theme.BACKGROUND};
            color: {theme.TEXT};
            font-size: 13px;
        }
        QLabel {
            background: transparent;
            color: {theme.TEXT};
        }
        QLabel#TitleLabel, QLabel#PreviewTitle {
            color: {theme.TEXT};
            font-size: 15px;
            font-weight: 600;
        }
        QLabel#MutedLabel, QLabel#StatusLabel, QLabel#SettingsPlaceholder,
        QLabel#DimensionLabel {
            color: {theme.CONNECTOR};
            font-size: 12px;
        }
        QFrame#OperationsBar, QFrame#TerminalToolbar {
            background: {theme.SURFACE};
            border: 1px solid {theme.BORDER};
            border-radius: 2px;
        }
        QFrame#InlineSettings, QFrame#MarkerGapInline {
            background: transparent;
            border: 0;
        }
        QPushButton#RemoveButton, QPushButton#ClearButton,
        QPushButton#DeleteButton {
            background: {theme.SURFACE};
            border-color: {theme.STATUS_ERROR};
            color: {theme.STATUS_ERROR};
            font-weight: 600;
        }
        QPushButton#RemoveButton:hover, QPushButton#ClearButton:hover,
        QPushButton#DeleteButton:hover {
            background: {theme.PANEL};
            border-color: {theme.STATUS_ERROR};
            color: {theme.STATUS_ERROR};
        }
    """.replace("ROOT_OBJECT", root_object_name)
    return stylesheet(base + extra)


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
        .replace("{theme.BRAND_SURFACE}", BRAND_SURFACE)
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
