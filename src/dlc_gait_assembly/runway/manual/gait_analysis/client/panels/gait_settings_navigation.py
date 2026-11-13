"""Keep every settings section visible in two compact rows."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.qt_sliding_tabs import SlidingTabBar


class GaitSettingsNavigation(QWidget):
    section_indices = ((0, 1, 7, 6), (3, 2, 4, 5))

    def __init__(self, pages, parent=None):
        super().__init__(parent)
        self.pages = pages
        self.setObjectName("RunwayStickySettingsNavigation")
        self._syncing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 6)
        layout.setSpacing(2)
        self.rows = tuple(SlidingTabBar(theme.TOOL_3) for _ in self.section_indices)
        labels = (("Setup", "Calibration", "Strides", "Output"), ("Filters", "Movement", "Labels", "Parameters"))
        for row, indices, names in zip(self.rows, self.section_indices, labels, strict=True):
            row.setObjectName("RunwaySettingsSectionRow")
            row.setExpanding(True)
            row.setDrawBase(False)
            for label in names:
                row.addTab(label)
            row.tabBarClicked.connect(lambda local, indices=indices: self._select(local, indices))
            row.currentChanged.connect(lambda local, indices=indices: self._select(local, indices))
            layout.addWidget(row)
        pages.currentChanged.connect(self._sync)
        self._sync(pages.currentIndex())

    def _select(self, local, indices):
        if not self._syncing and 0 <= local < len(indices):
            self.pages.setCurrentIndex(indices[local])

    def _sync(self, index):
        self._syncing = True
        try:
            for row, indices in zip(self.rows, self.section_indices, strict=True):
                active = index in indices
                row.set_active_row(active)
                if active and row.currentIndex() != indices.index(index):
                    row.setCurrentIndex(indices.index(index))
        finally:
            self._syncing = False

    def set_section_visible(self, index, visible):
        self._syncing = True
        try:
            for row, indices in zip(self.rows, self.section_indices, strict=True):
                if index in indices:
                    row.setTabVisible(indices.index(index), visible)
        finally:
            self._syncing = False
        self._sync(self.pages.currentIndex())

    def set_section_text(self, index, text):
        for row, indices in zip(self.rows, self.section_indices, strict=True):
            if index in indices:
                row.setTabText(indices.index(index), text)
