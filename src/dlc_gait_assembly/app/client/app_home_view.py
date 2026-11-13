"""Present the illustrated setup menu and host the automated workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.business.app_navigation_routes import LADDER_UI_ENABLED
from dlc_gait_assembly.app.client.app_branding_widgets import (
    MenuIllustrationLabel,
    WorkspaceChoiceCard,
)
from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
from dlc_gait_assembly.shared.client.qt_page_stack import CurrentPageStackedWidget
from dlc_gait_assembly.shared.client.theme.theme_menu_graphics import menu_colors
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex


class MainMenuWidget(QWidget):
    tool_requested = Signal(str)
    runway_requested = Signal()

    def __init__(self, tools: list[ToolSpec], *, automatic_factory):
        super().__init__()
        self.setObjectName("MainMenuWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._tools = tools

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 16, 32, 20)
        content_row = QHBoxLayout()
        self.view_stack = CurrentPageStackedWidget()
        self.view_stack.setMaximumWidth(1320)
        content_row.addStretch(1)
        content_row.addWidget(self.view_stack, 100)
        content_row.addStretch(1)
        root.addLayout(content_row, 1)

        self.home_page = self._build_home_page()
        self.view_stack.addWidget(self.home_page)

        self.automated_profiles = automatic_factory()
        self.view_stack.addWidget(self.automated_profiles)
        self._apply_style()

    def _build_home_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("PipelineHomePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)
        layout.addStretch()
        choices = QHBoxLayout()
        choices.setSpacing(20)
        choices.addWidget(self._setup_card(
            "Runway analysis",
            asset="runway-mouse",
            illustration="Laboratory mouse walking through a runway enclosure",
            requested=self.runway_requested.emit,
        ), 3)
        choices.addWidget(self._setup_card(
            "Ladder analysis",
            asset="ladder-mouse",
            enabled=LADDER_UI_ENABLED,
            illustration="Laboratory mouse walking across a horizontal ladder",
            requested=lambda: self.tool_requested.emit("ladder_analysis"),
        ), 2)
        layout.addLayout(choices)
        layout.addStretch()
        return page

    def _setup_card(self, title, *, asset, illustration, requested, enabled=True) -> WorkspaceChoiceCard:
        card = WorkspaceChoiceCard(title if enabled else f"{title} (WIP)")
        card.setEnabled(enabled)
        card.setObjectName("SetupChoiceCard")
        card.setProperty("setupAsset", asset)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.setSpacing(10)
        image = MenuIllustrationLabel(asset, illustration, card)
        label = QLabel(title, card)
        label.setObjectName("SetupTitle")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        for decoration in (image, label):
            decoration.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout.addWidget(decoration)
        if enabled:
            card.clicked.connect(requested)
            layout.addSpacing(24)
        else:
            card.unsetCursor()
            card.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            badge = QLabel("(WIP)", card)
            badge.setObjectName("SetupStatus")
            layout.addWidget(badge, 0, Qt.AlignHCenter)
        return card

    def show_automated(self) -> None:
        self.view_stack.setCurrentWidget(self.automated_profiles)

    def _apply_style(self) -> None:
        self.automated_profiles._apply_style()
        colors = menu_colors(theme.IS_DARK)
        disabled_surface = mix_hex(colors["surface"], "#000000", 0.22 if theme.IS_DARK else 0.12)
        self.setStyleSheet(f"""
            QWidget#MainMenuWidget {{
                background: {colors["bg"]};
            }}
            QWidget#PipelineHomePage {{ background: transparent; }}
            QWidget#PipelineHomePage QLabel {{
                background: transparent; color: {colors["text"]}; border: 0;
            }}
            QLabel#SetupTitle {{ font-size: 26px; font-weight: 600; }}
            QFrame#SetupChoiceCard {{
                background: {colors["surface"]}; border: 1px solid {colors["line"]}; border-radius: 0;
            }}
            QFrame#SetupChoiceCard:disabled {{ background: {disabled_surface}; }}
            QWidget#PipelineHomePage QLabel#SetupStatus {{
                background: {colors["panel"]}; color: {colors["text"]};
                border-radius: 4px; padding: 3px 8px; font-weight: 700;
            }}
            QFrame#SetupChoiceCard:enabled:hover, QFrame#SetupChoiceCard:enabled:focus {{
                border-color: {colors["accent"]};
            }}
        """)
