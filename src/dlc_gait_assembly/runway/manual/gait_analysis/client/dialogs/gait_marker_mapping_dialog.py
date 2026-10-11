"""Match coordinate-table body-part labels to the markers required by the selected analysis."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QLabel,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    BOTTOM_VIEW_LABELS,
    FORELIMB_SIDE_VIEW_LABELS,
    SIDE_VIEW_LABELS,
    auto_bodypart_label,
    raw_label_for_standard,
)
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    workspace_stylesheet as _dependency_theme_workspace_stylesheet,
)


class LabelMappingDialog(QDialog):
    def __init__(
        self,
        view_set: AlmaViewCsvSet,
        labels_by_view: dict[str, list[str]],
        existing_mapping: dict[str, dict[str, str]],
        parent=None,
        *,
        include_forelimb: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(f"Label matching: {view_set.name}")
        self.resize(820, 560)
        self._combos: dict[tuple[str, str], QComboBox] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        layout.addWidget(tabs, 1)
        side_labels = SIDE_VIEW_LABELS + (FORELIMB_SIDE_VIEW_LABELS if include_forelimb else ())
        bottom_labels = BOTTOM_VIEW_LABELS
        for view, title, csv_path, required_labels in (
            ("left", "Left side view", view_set.left_csv, side_labels),
            ("right", "Right side view", view_set.right_csv, side_labels),
            ("bottom", "Bottom view", view_set.bottom_csv, bottom_labels),
        ):
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(8, 8, 8, 8)
            page_layout.setSpacing(10)
            file_label = QLabel(csv_path.name)
            file_label.setObjectName("MutedLabel")
            page_layout.addWidget(file_label)
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            raw_labels = labels_by_view.get(view, [])
            choices = ["(none)", *raw_labels]
            existing_for_view = existing_mapping.get(view, {})
            for row, standard_label in enumerate(required_labels):
                combo = QComboBox()
                combo.addItems(choices)
                selected = raw_label_for_standard(existing_for_view, standard_label)
                if selected not in raw_labels:
                    selected = auto_bodypart_label(raw_labels, standard_label)
                combo.setCurrentText(selected or "(none)")
                set_tooltip(combo, f"Raw DLC label to use as {standard_label}.")
                self._combos[view, standard_label] = combo
                grid.addWidget(QLabel(standard_label), row, 0)
                grid.addWidget(combo, row, 1)
            page_layout.addLayout(grid)
            page_layout.addStretch(1)
            tabs.addTab(page, title)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(_dependency_theme_workspace_stylesheet("LabelMappingDialog", ""))

    def mapping(self) -> dict[str, dict[str, str]]:
        mapping: dict[str, dict[str, str]] = {"left": {}, "right": {}, "bottom": {}}
        for (view, standard_label), combo in self._combos.items():
            raw_label = combo.currentText()
            if raw_label and raw_label != "(none)":
                mapping[view][raw_label] = standard_label
        return {view: value for (view, value) in mapping.items() if value}
