"""Present the six manual Runway stages in their declared application order."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget


def build_manual_stage_directory(
    self, automated_card, home_layout, ladder_card, manual_card, runway_card, runway_home_layout, view_stack
):
    manual_pipeline_page = QWidget()
    manual_pipeline_page.setObjectName("ManualPipelineMenuPage")
    manual_pipeline_layout = QVBoxLayout(manual_pipeline_page)
    manual_pipeline_layout.setContentsMargins(0, 0, 0, 0)
    manual_pipeline_layout.setSpacing(20)
    manual_pipeline_layout.addStretch(1)
    self._menu_heading(manual_pipeline_layout, "Manual pipeline")
    (expanded_manual_card, start_manual_button) = self._manual_choice_card(expanded=True)
    start_manual_button.clicked.connect(lambda: self.tool_requested.emit(self._tools[0].id))
    manual_pipeline_layout.addWidget(expanded_manual_card)
    manual_pipeline_layout.addStretch(1)
    self._expanded_manual_card_widget = expanded_manual_card
    self.start_manual_pipeline_button = start_manual_button
    self.manual_pipeline_page = manual_pipeline_page
    view_stack.addWidget(manual_pipeline_page)
    self._menu_page_layouts = (home_layout, runway_home_layout, manual_pipeline_layout)
    self._launch_cards = (runway_card, ladder_card, manual_card, automated_card, expanded_manual_card)
