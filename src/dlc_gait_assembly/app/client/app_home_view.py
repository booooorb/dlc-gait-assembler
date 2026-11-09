"""Present the illustrated setup menu and host the automated workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.client.app_branding_widgets import (
    MenuIllustrationLabel,
    WorkspaceChoiceCard,
)
from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
from dlc_gait_assembly.shared.client.qt_page_stack import CurrentPageStackedWidget
from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet
from dlc_gait_assembly.shared.client.theme.theme_menu_graphics import menu_colors, menu_font


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
        title = self._menu_label("Choose a setup", "HomeTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        choices = QHBoxLayout()
        choices.setSpacing(20)
        choices.addWidget(self._setup_card(
            "Runway analysis",
            "From tracked keypoints to gait metrics. Work stage by stage or automate a complete batch.",
            asset="runway-mouse",
            illustration="Laboratory mouse walking through a runway enclosure",
            action="Open Runway",
            requested=self.runway_requested.emit,
        ), 3)
        choices.addWidget(self._setup_card(
            "Ladder analysis",
            "Review paw placements, detect slips and falls, and export rung-level events.",
            asset="ladder-mouse",
            illustration="Laboratory mouse walking across a horizontal ladder",
            action="Open ladder analysis",
            requested=lambda: self.tool_requested.emit("ladder_analysis"),
        ), 2)
        layout.addLayout(choices)
        layout.addStretch()
        return page

    def _setup_card(self, title, description, *, asset, illustration, action, requested) -> WorkspaceChoiceCard:
        card = WorkspaceChoiceCard(action)
        card.setObjectName("SetupChoiceCard")
        card.setProperty("setupAsset", asset)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.setSpacing(10)
        layout.addWidget(MenuIllustrationLabel(asset, illustration, card))
        layout.addWidget(self._menu_label(title, "SetupTitle"))
        layout.addWidget(self._menu_label(description, "MenuSubtitle"))
        layout.addStretch()
        button = QPushButton(action)
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(40)
        button.clicked.connect(requested)
        layout.addWidget(button)
        card.clicked.connect(requested)
        card.make_decorations_mouse_transparent(button)
        return card

    @staticmethod
    def _menu_label(text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def show_automated(self) -> None:
        self.view_stack.setCurrentWidget(self.automated_profiles)

    def _apply_style(self) -> None:
        self.automated_profiles._apply_style()
        colors = menu_colors(theme.IS_DARK)
        self.home_page.setFont(menu_font())
        texture = stylesheet("{theme.BACKGROUND_TEXTURE}")
        self.setStyleSheet(f"""
            QWidget#MainMenuWidget {{
                background: {colors["bg"]}; background-image: url({texture});
            }}
            QWidget#PipelineHomePage {{ background: transparent; }}
            QWidget#PipelineHomePage QLabel {{
                background: transparent; color: {colors["text"]}; border: 0;
            }}
            QLabel#HomeTitle {{ font-size: 34px; font-weight: 600; }}
            QLabel#SetupTitle {{ font-size: 26px; font-weight: 600; }}
            QLabel#MenuSubtitle {{ color: {colors["muted"]}; font-size: 14px; }}
            QFrame#SetupChoiceCard {{
                background: {colors["surface"]}; border: 1px solid {colors["line"]}; border-radius: 10px;
                min-height: 345px;
            }}
            QFrame#SetupChoiceCard:hover, QFrame#SetupChoiceCard:focus {{
                border-color: {colors["accent"]};
            }}
            QFrame#SetupChoiceCard[setupAsset="ladder-mouse"]:hover,
            QFrame#SetupChoiceCard[setupAsset="ladder-mouse"]:focus {{
                border-color: {theme.TOOL_2};
            }}
        """)
