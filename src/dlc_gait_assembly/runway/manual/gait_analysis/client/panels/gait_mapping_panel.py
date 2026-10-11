"""Display and edit the body-part mapping for each selected camera view."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    STANDARD_BODYPARTS,
    auto_bodypart_label,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_marker_mapping_dialog import LabelMappingDialog
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class GaitMappingPanel:
    """GaitMappingPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _load_bodypart_mapping_from_first_file(self) -> None:
        if not self.view.state.selected_files:
            QMessageBox.information(
                self.view, "No input files", "Add left/right/bottom CSV files before loading body part labels."
            )
            return
        csv_path = self.view.inputs._selected_preview_file()
        try:
            self.view.state.raw_bodyparts = self.view.analysis.inputs.bodyparts(csv_path)
        except Exception as exc:
            self.view.state.raw_bodyparts = []
            self._refresh_bodypart_mapping_choices()
            self.view.mapping_status_label.setText("Could not read body part labels.")
            QMessageBox.critical(self.view, "Could not read body part labels", str(exc))
            return
        self._refresh_bodypart_mapping_choices()
        self._apply_auto_bodypart_mapping()
        self.view.mapping_status_label.setText(
            f"{len(self.view.state.raw_bodyparts)} labels loaded from {csv_path.name}."
        )

    def _open_label_matching_dialog(self) -> None:
        if not self.view.inputs._is_three_view_mode():
            self.view.settings_tabs.setCurrentWidget(self.view.mapping_tab)
            return
        view_set = self.view.inputs._selected_view_set()
        if view_set is None:
            QMessageBox.information(self.view, "CSV set required", self.view.inputs._input_requirement_message())
            return
        try:
            labels_by_view = {
                "left": self.view.analysis.inputs.bodyparts(view_set.left_csv),
                "right": self.view.analysis.inputs.bodyparts(view_set.right_csv),
                "bottom": self.view.analysis.inputs.bodyparts(view_set.bottom_csv),
            }
        except Exception as exc:
            QMessageBox.critical(self.view, "Could not read labels", str(exc))
            return
        dialog = LabelMappingDialog(
            view_set,
            labels_by_view,
            self.view.state.view_label_mappings.get(view_set.name, {}),
            self.view,
            include_forelimb=self.view.limb_scope_combo.currentText() == "Hindlimb + Forelimb",
        )
        if dialog.exec() != QDialog.Accepted:
            return
        mapping = dialog.mapping()
        if mapping:
            self.view.state.view_label_mappings[view_set.name] = mapping
        else:
            self.view.state.view_label_mappings.pop(view_set.name, None)
        selected_count = sum(len(view_mapping) for view_mapping in mapping.values())
        available_count = 27 if self.view.limb_scope_combo.currentText() == "Hindlimb + Forelimb" else 16
        self.view.mapping_status_label.setText(
            f"{selected_count}/{available_count} labels assigned for {view_set.name}."
        )
        self.view.rustlab_status_label.setText(f"RustLab1 label mapping updated for {view_set.name}.")
        self.view.controller._invalidate_stickplot_preview(f"Generate a stick-plot preview for {view_set.name}.")

    def _refresh_bodypart_mapping_choices(self) -> None:
        choices = ["(none)", *self.view.state.raw_bodyparts]
        for combo in self.view._bodypart_combos.values():
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(choices)
            if current in choices:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        self._update_mapping_enabled()

    def _apply_auto_bodypart_mapping(self) -> None:
        if not self.view.state.raw_bodyparts:
            return
        for standard_bodypart, combo in self.view._bodypart_combos.items():
            auto_label = auto_bodypart_label(self.view.state.raw_bodyparts, standard_bodypart)
            combo.setCurrentText(auto_label or "(none)")

    def _update_mapping_enabled(self) -> None:
        enabled = self.view.use_custom_mapping_checkbox.isChecked() and bool(self.view.state.raw_bodyparts)
        for combo in self.view._bodypart_combos.values():
            combo.setEnabled(enabled)

    def _collect_bodypart_mapping(self) -> dict[str, str] | None:
        if not self.view.use_custom_mapping_checkbox.isChecked():
            return None
        mapping: dict[str, str] = {}
        for standard_bodypart, combo in self.view._bodypart_combos.items():
            raw_bodypart = combo.currentText()
            if raw_bodypart and raw_bodypart != "(none)":
                mapping[raw_bodypart] = standard_bodypart
        return mapping or None

    def _collect_view_bodypart_mapping(self) -> dict[str, object] | None:
        if not self.view.inputs._is_three_view_mode():
            return None
        return self.view.state.view_label_mappings or None


def build_gait_marker_mapping(self, mapping_tab_layout):
    mapping_box = QGroupBox("Body part mapping")
    mapping_box.setMinimumHeight(220)
    mapping_layout = QVBoxLayout(mapping_box)
    mapping_layout.setSpacing(10)
    mapping_header = QHBoxLayout()
    self.use_custom_mapping_checkbox = QCheckBox("Use custom mapping")
    self.reload_mapping_button = QPushButton("Load from CSV")
    self.auto_mapping_button = QPushButton("Auto detect")
    set_tooltip(self.use_custom_mapping_checkbox, "Manually map raw DLC labels to the expected ALMA body parts.")
    set_tooltip(self.reload_mapping_button, "Load body-part labels from the first selected CSV.")
    set_tooltip(self.auto_mapping_button, "Automatically match common DLC body-part labels.")
    mapping_header.addWidget(self.use_custom_mapping_checkbox)
    mapping_header.addStretch(1)
    mapping_header.addWidget(self.reload_mapping_button)
    mapping_header.addWidget(self.auto_mapping_button)
    mapping_layout.addLayout(mapping_header)
    self.mapping_status_label = QLabel("Add a CSV to detect labels.")
    self.mapping_status_label.setObjectName("MutedLabel")
    self.mapping_status_label.setWordWrap(True)
    mapping_layout.addWidget(self.mapping_status_label)
    mapping_grid = QGridLayout()
    mapping_grid.setHorizontalSpacing(12)
    mapping_grid.setVerticalSpacing(8)
    for index, standard_bodypart in enumerate(STANDARD_BODYPARTS):
        row = index // 2
        column = index % 2 * 2
        label = QLabel(standard_bodypart)
        combo = QComboBox()
        combo.setMinimumWidth(150)
        combo.setEnabled(False)
        set_tooltip(combo, f"Raw DLC label to use as {standard_bodypart}.")
        self._bodypart_combos[standard_bodypart] = combo
        mapping_grid.addWidget(label, row, column)
        mapping_grid.addWidget(combo, row, column + 1)
    mapping_layout.addLayout(mapping_grid)
    mapping_tab_layout.addWidget(mapping_box)
    mapping_tab_layout.addStretch(1)
