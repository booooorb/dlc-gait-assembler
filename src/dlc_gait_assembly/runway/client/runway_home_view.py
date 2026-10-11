"""Present Manual and Automatic choices within the Runway workflow."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget


def build_runway_home(self, view_stack):
    runway_home_page = QWidget()
    runway_home_page.setObjectName("RunwayHomePage")
    runway_home_layout = QVBoxLayout(runway_home_page)
    runway_home_layout.setContentsMargins(0, 0, 0, 0)
    runway_home_layout.setSpacing(20)
    runway_home_layout.addStretch(1)
    self._menu_heading(runway_home_layout, "Runway workflow")
    runway_choices = QHBoxLayout()
    runway_choices.setSpacing(20)
    (manual_card, manual_button) = self._manual_choice_card()
    manual_button.clicked.connect(self.manual_requested.emit)
    manual_card.clicked.connect(self.manual_requested.emit)
    runway_choices.addWidget(manual_card, 3)
    (automated_card, automated_button, profiles_button) = self._automated_choice_card()
    automated_button.clicked.connect(self.automated_requested.emit)
    automated_card.clicked.connect(self.automated_requested.emit)
    profiles_button.clicked.connect(self.profiles_requested.emit)
    runway_choices.addWidget(automated_card, 2)
    runway_home_layout.addLayout(runway_choices)
    handoff = QFrame()
    handoff.setObjectName("ProfileBridge")
    handoff.setProperty("pipelineRole", "profiles")
    handoff_layout = QHBoxLayout(handoff)
    handoff_layout.setContentsMargins(20, 14, 20, 14)
    handoff_layout.setSpacing(16)
    handoff_layout.addWidget(self._menu_graphic("file-settings", 28))
    handoff_layout.addWidget(self._menu_label("Reuse exported manual settings in a profile.", "MenuBody"), 1)
    handoff_layout.addWidget(profiles_button)
    runway_home_layout.addWidget(handoff)
    runway_home_layout.addStretch(1)
    self._manual_choice_card_widget = manual_card
    self._pipeline_handoff_widget = handoff
    self._automated_choice_card_widget = automated_card
    self.automated_choice_button = automated_button
    self.configure_profiles_button = profiles_button
    self.runway_manual_choice_button = manual_button
    self.runway_home_page = runway_home_page
    view_stack.addWidget(runway_home_page)
    return (automated_card, manual_card, runway_home_layout)
