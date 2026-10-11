"""Prepare packaged menu illustrations and theme-aware branding graphics."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import read_resource_text, resource_path

ASSETS = resource_path("icons")


def menu_colors(dark: bool) -> dict[str, str]:
    from dlc_gait_assembly.shared.client.theme.theme_color_tokens import (
        DARK_COLORS,
        DARK_TOOLS,
        LIGHT_COLORS,
        PRIMARY_TOOLS,
    )

    colors = DARK_COLORS if dark else LIGHT_COLORS
    tools = DARK_TOOLS if dark else PRIMARY_TOOLS
    return dict(
        bg=colors.background,
        surface=colors.surface,
        panel=colors.panel,
        line=colors.border,
        text=colors.text,
        muted=colors.secondary_text,
        accent=tools.tool_3,
        tint=colors.surface,
        button=tools.tool_3,
        button_text=colors.background if dark else colors.surface,
    )


@lru_cache(maxsize=1)
def menu_font() -> QFont:
    font_id = QFontDatabase.addApplicationFont(str(resource_path("fonts", "Geist.ttf")))
    families = QFontDatabase.applicationFontFamilies(font_id)
    return QFont(families[0] if families else "Sans Serif")


@lru_cache(maxsize=128)
def menu_icon(name: str, color: str, size: int = 24) -> QIcon:
    source = read_resource_text("icons", f"{name}.svg").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(source.encode()))
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)
