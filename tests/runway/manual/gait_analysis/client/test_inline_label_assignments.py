"""All three camera assignments are editable in the left Labels panel without a dialog."""

from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialog

from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations, create_gait_preview
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import view_mappings_for_set
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


@pytest.fixture
def view(themed_gait_application):
    widget = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    widget.resize(1100, 700)
    widget.show()
    themed_gait_application.processEvents()
    yield widget
    widget.close()


def test_all_camera_fields_live_inside_the_labels_tab_and_are_reachable(view, themed_gait_application, monkeypatch):
    monkeypatch.setattr(QDialog, "exec", lambda *_args: pytest.fail("Label assignments must stay inline"))
    view.label_matching_button.click()
    themed_gait_application.processEvents()
    assert view.settings_tabs.currentWidget() is view.mapping_tab
    assert view.settings_tabs.tabText(4) == "Labels"
    assert {camera: len(combos) for camera, combos in view._view_bodypart_combos.items()} == {
        "left": 10, "right": 10, "bottom": 6,
    }
    scroll = view.settings_scrolls[view.mapping_tab]
    for camera, box in view.view_mapping_boxes.items():
        assert box.title() == camera.upper()
        assert view.mapping_tab.isAncestorOf(box)
        assert box.isVisible()
        for combo in view._view_bodypart_combos[camera].values():
            scroll.ensureWidgetVisible(combo)
            themed_gait_application.processEvents()
            assert combo.isEnabled()
            assert scroll.viewport().rect().contains(combo.mapTo(scroll.viewport(), combo.rect().center()))
    assert view.width() == 1100
    assert view.height() == 700


def test_labels_remain_available_in_standalone_rustlab(view):
    view.workflow_combo.setCurrentIndex(2)
    assert view.settings_tabs.isTabVisible(4)
    view.label_matching_button.click()
    assert view.settings_tabs.currentWidget() is view.mapping_tab
    assert all(box.isVisible() for box in view.view_mapping_boxes.values())
    view._view_bodypart_combos["bottom"]["back right"].setCurrentText("custom_paw")
    assert view_mappings_for_set(view.setup._collect_rustlab1_settings(), "recording")["bottom"] == {
        "custom_paw": "back right",
    }


def test_loading_and_switching_csv_sets_keeps_each_cameras_labels_and_edits(view):
    fixture = Path(__file__).resolve().parents[4] / "fixtures/gait/rustlab1_r_reference"
    paths = [fixture / f"{camera}.csv" for camera in ("left", "right", "bottom")]
    view.inputs._add_csv_paths(paths)
    view.state.manual_view_sets = [AlmaViewCsvSet("A", *paths), AlmaViewCsvSet("B", *paths)]
    view.inputs._refresh_view_sets()
    view.settings_tabs.setCurrentWidget(view.mapping_tab)
    for camera, path in zip(("left", "right", "bottom"), paths):
        labels = list(view.state.csv_bodyparts[path])
        combo = next(iter(view._view_bodypart_combos[camera].values()))
        assert all(combo.findText(label) >= 0 for label in labels)
        assert view.view_mapping_file_labels[camera].text() == path.name
    view._view_bodypart_combos["left"]["hip"].setCurrentText("hip_A")
    view.controller._select_view_set_row(1)
    view._view_bodypart_combos["left"]["hip"].setCurrentText("hip_B")
    view.controller._select_view_set_row(0)
    assert view._view_bodypart_combos["left"]["hip"].currentText() == "hip_A"
    settings = view.settings_snapshot()
    assert view_mappings_for_set(settings, "A")["left"]["hip_A"] == "hip"
    assert view_mappings_for_set(settings, "B")["left"]["hip_B"] == "hip"
    view.inputs._clear_files()
    view.label_matching_button.click()
    assert view.settings_tabs.currentWidget() is view.mapping_tab
    assert all(box.isVisible() for box in view.view_mapping_boxes.values())


def test_single_side_mode_keeps_its_mapping_controls(view):
    view.workflow_combo.setCurrentIndex(0)
    view.input_mode_combo.setCurrentText("Single side view")
    view.settings_tabs.setCurrentWidget(view.mapping_tab)
    assert view.single_mapping_box.isVisible()
    assert all(not box.isVisible() for box in view.view_mapping_boxes.values())
    view.use_custom_mapping_checkbox.setChecked(True)
    view._bodypart_combos["toe"].setCurrentText("custom_digit")
    assert view.settings_snapshot().custom_bodypart_mapping == {"custom_digit": "toe"}


def test_long_filenames_keep_dropdown_buttons_visible_and_clickable(view, themed_gait_application):
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle, QStyleOptionComboBox

    cameras = ("left", "right", "bottom")
    paths = [Path("/tmp") / (f"Mouse_Trial_{camera}_" + "longrecordingname_" * 9 + ".csv") for camera in cameras]
    name = "recording_" + "long_study_name_" * 12
    labels = ["very_long_raw_bodypart_" * 8, "toe", "hip", "alternate_marker"]
    view.state.selected_files = paths
    view.state.csv_bodyparts = {path: tuple(labels) for path in paths}
    view.state.manual_view_sets = [AlmaViewCsvSet(name, *paths)]
    view.inputs._refresh_view_sets()
    view.workspace_splitter.setSizes([380, 720])
    view.settings_tabs.setCurrentWidget(view.mapping_tab)
    themed_gait_application.processEvents()
    scroll = view.settings_scrolls[view.mapping_tab]
    assert scroll.widget().width() <= scroll.viewport().width()
    for camera in cameras:
        combos = view._view_bodypart_combos[camera]
        for combo in combos.values():
            scroll.ensureWidgetVisible(combo)
            themed_gait_application.processEvents()
            option = QStyleOptionComboBox()
            combo.initStyleOption(option)
            arrow = combo.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, combo)
            visible_arrow = QRect(combo.mapTo(scroll.viewport(), arrow.topLeft()), arrow.size())
            assert arrow.width() > 0
            assert visible_arrow.left() >= 0
            assert visible_arrow.right() < scroll.viewport().width()
            assert scroll.viewport().rect().contains(visible_arrow.center())
        standard = "back left" if camera == "bottom" else "toe"
        combo = combos[standard]
        scroll.ensureWidgetVisible(combo)
        themed_gait_application.processEvents()
        option = QStyleOptionComboBox()
        combo.initStyleOption(option)
        arrow = combo.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, combo)
        QTest.mouseClick(combo, Qt.LeftButton, pos=arrow.center())
        themed_gait_application.processEvents()
        assert combo.view().isVisible()
        target = combo.model().index(combo.findText("alternate_marker"), 0)
        combo.view().scrollTo(target)
        target_rect = combo.view().visualRect(target)
        target_point = QPoint(target_rect.left() + 20, target_rect.center().y())
        QTest.mouseMove(combo.view().viewport(), target_point)
        QTest.mouseClick(combo.view().viewport(), Qt.LeftButton, pos=target_point)
        themed_gait_application.processEvents()
        assert combo.currentText() == "alternate_marker"
        assert view.state.view_label_mappings[name][camera]["alternate_marker"] == standard
