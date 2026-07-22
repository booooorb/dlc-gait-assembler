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
