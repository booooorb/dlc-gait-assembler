"""Exercise updated ALMA option selection and persistence through the real gait controls."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations, create_gait_preview
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import RUNWAY_METHOD
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_manifest_import import apply_manifest_settings
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    alma_settings_from_manifest,
    write_analysis_manifest,
)
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace
from dlc_gait_assembly.shared.client.qt_setting_help import INFO_SUFFIX


@pytest.fixture
def view():
    app = QApplication.instance() or QApplication([])
    widget = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    widget.show()
    widget.analysis_type_combo.setCurrentText("Spontaneous walking")
    widget.settings_tabs.setCurrentWidget(widget.stride_detection_tab)
    app.processEvents()
    yield widget
    widget.close()
    app.processEvents()


def test_updated_detector_is_additional_and_legacy_stays_default(view):
    assert view.stride_method_combo.currentText() == "ALMA (legacy)"
    assert view.stride_method_combo.findText(RUNWAY_METHOD) >= 0
    assert not view.runway_settings_box.isVisible()
    view.stride_method_combo.setCurrentText(RUNWAY_METHOD)
    assert view.runway_settings_box.isVisible()
    assert not view.legacy_gap_widget.isVisible()
    assert view.setup._collect_settings().runway_joint_interpolation == "none"
    view.analysis_type_combo.setCurrentText("Treadmill")
    assert view.stride_method_combo.currentText() == "ALMA (legacy)"
    assert not view.runway_settings_box.isVisible()
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    assert view.stride_method_combo.currentText() == RUNWAY_METHOD
    view.stride_method_combo.setCurrentText("ALMA (legacy)")
    view.analysis_type_combo.setCurrentText("Treadmill")
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    assert view.stride_method_combo.currentText() == "ALMA (legacy)"


def test_every_new_control_invalidates_preview_and_round_trips(view, tmp_path):
    view.stride_method_combo.setCurrentText(RUNWAY_METHOD)
    view.input_mode_combo.setCurrentText("Single side view")
    view.calibration_method_combo.setCurrentIndex(view.calibration_method_combo.findData("manual"))
    view.pixels_per_cm_spin.setValue(50.0)
    for name, spin in view.runway_spins.items():
        view.state.preview_validity.complete()
        spin.setValue(spin.value() + 0.01)
        assert not view.state.preview_validity.ready, name
    for combo, index in ((view.runway_joint_combo, 2), (view.runway_source_combo, 1)):
        view.state.preview_validity.complete()
        combo.setCurrentIndex(index)
        assert not view.state.preview_validity.ready
    view.state.preview_validity.complete()
    view.runway_joint_cutoff_spin.setValue(10.0)
    assert not view.state.preview_validity.ready
    expected = view.setup._collect_settings()
    path = write_analysis_manifest(tmp_path / "settings.json", expected)
    view.stride_method_combo.setCurrentText("ALMA (legacy)")
    view.runway_joint_cutoff_spin.setValue(0.0)
    apply_manifest_settings(view, alma_settings_from_manifest(path))
    assert view.setup._collect_settings() == expected
    assert view.runway_settings_box.isVisible()
    inherited = replace(expected, runway_joint_filter_cutoff=None, runway_joint_interpolation="none")
    apply_manifest_settings(view, inherited)
    assert view.setup._collect_settings() == inherited


def test_updated_detector_accepts_optional_missing_joints(view):
    view.input_mode_combo.setCurrentText("Single side view")
    view.state.raw_bodyparts = ["toe", "hip"]
    view.stride_method_combo.setCurrentText(RUNWAY_METHOD)
    assert view.inputs._missing_required_bodyparts(view.setup._collect_settings()) == []
    view.state.raw_bodyparts = ["toe", "crest"]
    assert view.inputs._missing_required_bodyparts(view.setup._collect_settings()) == []
    view.state.raw_bodyparts = ["toe"]
    assert view.inputs._missing_required_bodyparts(view.setup._collect_settings()) == ["hip or iliac crest"]


def test_runway_and_bottom_confidence_controls_explain_their_separate_scope(view):
    view.stride_method_combo.setCurrentText(RUNWAY_METHOD)
    view.likelihood_threshold_spin.setValue(0.3)
    assert not view.likelihood_threshold_spin.isEnabled()
    assert "0.60" in view.runway_confidence_link.text()
    assert view.setup._collect_settings().runway_confidence_threshold == 0.6
    view.runway_confidence_link.click()
    assert view.settings_tabs.currentWidget() is view.stride_detection_tab
    view.runway_spins["runway_confidence_threshold"].setValue(0.3)
    assert "0.30" in view.runway_confidence_link.text()
    assert view.setup._collect_settings().runway_confidence_threshold == 0.3
    view.workflow_combo.setCurrentText("ALMA side + rust bottom")
    assert view.likelihood_threshold_spin.isEnabled()
    assert view.likelihood_threshold_label.text() == "Bottom confidence min" + INFO_SUFFIX
    assert view.likelihood_threshold_label.toolTip() == view.likelihood_threshold_spin.toolTip()
    view.likelihood_threshold_spin.setValue(0.8)
    settings = view.setup._collect_settings()
    assert settings.likelihood_threshold == 0.8 and settings.runway_confidence_threshold == 0.3
