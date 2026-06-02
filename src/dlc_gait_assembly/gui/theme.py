from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    name: str
    tool_1: str
    tool_2: str
    tool_3: str
    number_icon: str


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
    name="Primary Tools",
    tool_1="#00C68D",
    tool_2="#FFD400",
    tool_3="#FF0052",
    number_icon="#0055DA",
)

# Change these assignments while testing palettes.
AESTHETIC_PALETTE = PASTEL_SKY
ACTIVE_PALETTE = PRIMARY_TOOLS

BACKGROUND = "#EEEEEE"
SURFACE = "#EEEEEE"
PANEL = "#DDDDDD"
SOFT = "#F79B72"
BORDER = "#C9D1D6"
TEXT = "#2A4759"
CONNECTOR = "#708a9a"
STATUS_READY = "#2FA84F"
STATUS_RUNNING = "#2D7DD2"
STATUS_ERROR = "#C3110C"
STATUS_OTHER = "#D6A813"
STEP_NUMBER_COLORS = ("#280905", "#740A03", "#C3110C", "#E6501B", "#F79B72")

TOOL_1 = ACTIVE_PALETTE.tool_1
TOOL_2 = ACTIVE_PALETTE.tool_2
TOOL_3 = ACTIVE_PALETTE.tool_3
NUMBER_ICON = ACTIVE_PALETTE.number_icon
ACCENT = BORDER

# Backward-compatible aliases for call sites that think in light-to-dark swatches.
LIGHT = BACKGROUND
PALE = SURFACE
MID = ACCENT
DARK = TEXT


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
