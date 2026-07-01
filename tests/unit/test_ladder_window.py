from __future__ import annotations

import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.gui.gait_analysis.ladder_window import (
    LadderAnalysisWidget,
)
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget


def test_gait_analysis_opens_runway_directly_without_a_ladder_menu():
    app = QApplication.instance() or QApplication([])
    gait_widget = GaitAnalysisWidget()

    assert gait_widget.kinematics_widget.isVisibleTo(gait_widget)
    assert not hasattr(gait_widget, "selector_widget")
    assert not hasattr(gait_widget, "ladder_widget")
    assert not hasattr(gait_widget.kinematics_widget, "back_to_gait_button")

    gait_widget.release_resources()
    gait_widget.close()
    app.processEvents()


def test_paired_mode_exposes_independent_left_and_right_thresholds():
    app = QApplication.instance() or QApplication([])
    widget = LadderAnalysisWidget()

    widget.mode_combo.setCurrentText("Paired left + right cameras")
    widget.method_combo.setCurrentText("Threshold")
    widget.auto_threshold_checkbox.setChecked(False)
    widget.threshold_spin.setValue(125.0)
    widget.right_method_combo.setCurrentText("Threshold")
    widget.right_auto_threshold_checkbox.setChecked(False)
    widget.right_threshold_spin.setValue(480.0)

    assert widget.settings_tabs.isTabVisible(1)
    assert widget.bodyparts_tabs.isTabVisible(1)
    assert widget._settings("left").threshold == 125.0
    assert widget._settings("right").threshold == 480.0

    widget.close()
    app.processEvents()
