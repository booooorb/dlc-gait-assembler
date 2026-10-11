from __future__ import annotations
from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations
from dlc_gait_assembly.app.app_bootstrap import create_gait_preview, create_ladder_use_cases, create_media_access
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from dlc_gait_assembly.ladder.client.ladder_analysis_view import LadderAnalysisWidget
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import GaitAnalysisWidget


def test_gait_analysis_opens_runway_directly_without_a_ladder_menu():
    app = QApplication.instance() or QApplication([])
    gait_widget = GaitAnalysisWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    assert gait_widget.kinematics_widget.isVisibleTo(gait_widget)
    assert not hasattr(gait_widget, "selector_widget")
    assert not hasattr(gait_widget, "ladder_widget")
    assert not hasattr(gait_widget.kinematics_widget, "back_to_gait_button")
    gait_widget.release_resources()
    gait_widget.close()
    app.processEvents()


def test_paired_mode_exposes_independent_left_and_right_thresholds():
    app = QApplication.instance() or QApplication([])
    widget = LadderAnalysisWidget(
        use_cases=create_ladder_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
    )
    widget.mode_combo.setCurrentText("Paired left + right cameras")
    widget.method_combo.setCurrentText("Threshold")
    widget.auto_threshold_checkbox.setChecked(False)
    widget.threshold_spin.setValue(125.0)
    widget.right_method_combo.setCurrentText("Threshold")
    widget.right_auto_threshold_checkbox.setChecked(False)
    widget.right_threshold_spin.setValue(480.0)
    assert widget.settings_tabs.isTabVisible(1)
    assert widget.bodyparts_tabs.isTabVisible(1)
    assert widget.controller._settings("left").threshold == 125.0
    assert widget.controller._settings("right").threshold == 480.0
    widget.close()
    app.processEvents()


from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace
