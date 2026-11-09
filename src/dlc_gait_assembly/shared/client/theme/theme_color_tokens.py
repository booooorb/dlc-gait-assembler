"""Define shared color, spacing, and appearance tokens for both application themes."""

from __future__ import annotations

from dataclasses import dataclass


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


PALE_GARDEN = Palette(name="Pale Garden", tool_1="#F1F3E0", tool_2="#D2DCB6", tool_3="#A1BC98", number_icon="#778873")
PASTEL_SKY = Palette(name="Pastel Sky", tool_1="#D9F9DF", tool_2="#AEE2FF", tool_3="#B5BAFF", number_icon="#9FA1FF")
HIGH_VARIETY = Palette(name="High Variety", tool_1="#2EC4B6", tool_2="#3A86FF", tool_3="#FF6B6B", number_icon="#845EC2")
PRIMARY_TOOLS = Palette(
    name="Paw Track", tool_1="#3B403E", tool_2="#555B57", tool_3="#252827", number_icon="#555B57"
)
DARK_TOOLS = Palette(
    name="Paw Track Dark", tool_1="#D9DDD6", tool_2="#BFC5BE", tool_3="#F4F2EC", number_icon="#BFC5BE"
)
LIGHT_COLORS = ThemeColors(
    background="#F4F2EC",
    surface="#FCFAF5",
    panel="#EBE9E2",
    soft="#DDDCD5",
    border="#C6C7BF",
    text="#252827",
    secondary_text="#565D58",
    primary="#252827",
    primary_text="#F4F2EC",
    canvas="#202422",
    canvas_text="#F4F2EC",
    status_ready="#46634E",
    status_running="#6C592F",
    status_error="#963F38",
)
DARK_COLORS = ThemeColors(
    background="#202422",
    surface="#282D2A",
    panel="#303632",
    soft="#3E4540",
    border="#535D56",
    text="#F4F2EC",
    secondary_text="#C0C7C0",
    primary="#F4F2EC",
    primary_text="#202422",
    canvas="#151817",
    canvas_text="#F4F2EC",
    status_ready="#ADC9B1",
    status_running="#D4BF90",
    status_error="#E7A49D",
)
AESTHETIC_PALETTE = PRIMARY_TOOLS
BRAND_SURFACE = LIGHT_COLORS.surface
