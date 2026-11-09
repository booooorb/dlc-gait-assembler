"""Exercise the simplified workspace without losing scientific settings or results."""

import pytest
from pathlib import Path
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QPushButton, QSpinBox, QWidget

from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations, create_gait_preview
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget
from dlc_gait_assembly.shared.client.theme.theme_application_styles import application_stylesheet
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


def test_csv_upload_uses_the_available_height_and_does_not_silently_skip_extra_files(view, tmp_path):
    import shutil
    fixture = Path(__file__).resolve().parents[4] / "fixtures/gait/rustlab1_r_reference"
    paths = []
    for side in ("left", "right", "bottom"):
        path = tmp_path / f"mouse_{side}.csv"
        shutil.copy2(fixture / f"{side}.csv", path)
        paths.append(path)
    view.resize(1360, 900)
    view.inputs._add_csv_paths(paths)
    QApplication.processEvents()
    assert view.view_set_table.height() > 300
    assert view.inputs._has_valid_inputs()
    extra = tmp_path / "unclassified.csv"
    shutil.copy2(fixture / "left.csv", extra)
    view.inputs._add_csv_paths([extra])
    assert view.state.view_set_errors
    assert not view.inputs._has_valid_inputs()
    extra_row = next(view.view_set_table.topLevelItem(i) for i in range(view.view_set_table.topLevelItemCount())
                     if extra.name in view.view_set_table.topLevelItem(i).toolTip(1)
                     or str(extra) in (view.view_set_table.topLevelItem(i).data(0, Qt.UserRole + 1) or ()))
    view.view_set_table.clearSelection()
    extra_row.setSelected(True)
    view.remove_files_button.click()
    assert extra not in view.state.selected_files
    assert all(path.is_file() for path in paths)
    assert extra.is_file()
    assert view.inputs._has_valid_inputs()


@pytest.fixture
def view():
    app = QApplication.instance() or QApplication([])
    old_style = app.styleSheet()
    app.setStyleSheet(application_stylesheet())
    widget = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    widget.resize(1100, 760)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    app.setStyleSheet(old_style)
    app.processEvents()


def test_every_settings_section_is_visible_and_opens_with_one_click(view):
    assert not hasattr(view.settings_navigation, "more_button")
    visited = set()
    for row, indices in zip(view.settings_section_rows, view.settings_navigation_indices, strict=True):
        for local, index in enumerate(indices):
            assert row.isVisible() and row.isTabVisible(local)
            assert row.rect().contains(row.tabRect(local))
            QTest.mouseClick(row, Qt.LeftButton, pos=row.tabRect(local).center())
            QApplication.processEvents()
            assert view.settings_tabs.currentIndex() == index
            assert row.property("activeRow")
            visited.add(index)
    assert visited == set(range(8))


def test_timing_disclosure_keeps_camera_values_and_reveals_overrides(view):
    view.workflow_combo.setCurrentText("ALMA side + rust bottom")
    assert not view.view_timing_box.isVisible()
    view.view_fps_spins["right"].setValue(240)
    view.view_offset_spins["bottom"].setValue(0.125)
    assert view.view_timing_box.isVisible()
    settings = view.settings_snapshot()
    view.view_timing_disclosure.button.click()
    assert not view.view_timing_box.isVisible()
    assert view.settings_snapshot() == settings
    view.view_timing_disclosure.button.click()
    assert view.view_timing_box.isVisible()
    assert view.settings_snapshot() == settings


def test_results_survive_switching_to_preview_and_changing_settings(view, tmp_path):
    csv = tmp_path / "all_raw_data.csv"
    csv.write_text('Measure,Value\nleft__stride length (cm)__mean,1.234567890123456\n')
    view.controller._output_results_ready((AlmaRunResult(csv, (csv,)),))
    assert view.workspace_tabs.currentWidget() is view.results_page
    assert [view.workspace_tabs.tabText(i) for i in range(view.workspace_tabs.count())] == ["Files", "Preview", "Results", "Log"]
    view.workspace_tabs.setCurrentWidget(view.preview_page)
    view.filter_cutoff_spin.setValue(5)
    view.workspace_tabs.setCurrentWidget(view.results_page)
    assert view.output_preview_view.selected_path == csv
    assert view.output_preview_view.csv_preview.item(0, 1).toolTip() == "1.234567890123456"
    assert view.output_preview_view.csv_preview.item(0, 1).text() == "1.2345679"
    assert "1.234567890123456" in csv.read_text()


def test_open_file_uses_the_selected_result_and_destination_is_not_duplicated(view, tmp_path, monkeypatch):
    csv = tmp_path / "left_stride_parameters.csv"
    csv.write_text('stride length (cm)\n1.2\n')
    view.controller._output_results_ready((AlmaRunResult(csv, (csv,)),))
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(Path(url.toLocalFile())) or True)
    view.output_preview_view.open_file_button.click()
    assert opened == [csv]
    assert view.output_folder_edit is view.export_folder_edit
    assert view.output_folder_button is view.export_folder_button
    assert not view.inputs_page.isAncestorOf(view.output_folder_edit)


def test_common_controls_fit_the_narrow_settings_pane(view):
    view.workflow_combo.setCurrentText("ALMA side + rust bottom")
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    view.stride_method_combo.setCurrentText("Speed mixture (GMM)")
    view.calibration_method_combo.setCurrentIndex(view.calibration_method_combo.findData("per_view"))
    view.view_timing_disclosure.button.click()
    for index in range(view.settings_tabs.count()):
        view.settings_tabs.setCurrentIndex(index)
        QApplication.processEvents()
        scroll = view.controls_scroll
        viewport = scroll.viewport()
        for widget in scroll.widget().findChildren(QWidget):
            if isinstance(widget, (QComboBox, QSpinBox, QDoubleSpinBox, QPushButton)) and widget.isVisible():
                left = widget.mapTo(viewport, QPoint()).x()
                assert left >= 0, (index, widget.objectName(), widget.__class__.__name__)
                assert left + widget.width() <= viewport.width() + 1, (index, widget.objectName(), widget.__class__.__name__, left, widget.width(), viewport.width())
