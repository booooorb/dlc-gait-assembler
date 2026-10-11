from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations


from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
    create_gait_preview,
)


(TOOL_SPECS, LADDER_TOOL_SPEC) = build_tool_specs()


from dlc_gait_assembly.shared.client.theme.theme_qt_palette import (
    application_palette as _dependency_theme_application_palette,
)


from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    application_stylesheet as _dependency_theme_application_stylesheet,
)


import os


from pathlib import Path


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from PySide6.QtCore import QAbstractAnimation, QPoint, Qt


from PySide6.QtTest import QTest


from PySide6.QtWidgets import (
    QApplication,
    QScrollArea,
)


import dlc_gait_assembly.shared.client.theme.theme_application_state as theme


from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_reference_catalog import gait_figure_catalog


from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_result_browser import OutputPreviewWidget


from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_stickplot_panel import (
    StickPlotPairPreviewWidget,
)


from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_worker import AlmaAnalysisThread


from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget


from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    auto_bodypart_label as _auto_bodypart_label,
)


from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult


from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings


from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)


def _wait_for_animation(animation, timeout_ms: int = 1500) -> None:
    elapsed = 0
    while animation.state() == QAbstractAnimation.State.Running and elapsed < timeout_ms:
        QTest.qWait(20)
        elapsed += 20
    assert animation.state() == QAbstractAnimation.State.Stopped


from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


from dlc_gait_assembly.app.app_bootstrap import create_gait_result_reader


def test_gait_parameter_reference_documents_and_filters_exported_parameters():
    app = QApplication.instance() or QApplication([])
    runway = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    runway.parameter_reference_button.click()
    app.processEvents()
    reference = runway.parameter_reference
    assert runway.workspace_stack.currentWidget() is reference
    assert reference.documentation_stack.currentWidget() is reference.parameter_documentation
    assert reference.parameter_tree.topLevelItemCount() == 140
    assert reference.count_label.text() == "Showing 140 of 140 gait parameters"
    reference.view_filter.setCurrentText("Single-view")
    app.processEvents()
    assert reference.parameter_tree.topLevelItemCount() == 32
    assert {reference.parameter_tree.topLevelItem(index).text(3) for index in range(32)} == {"ALMA"}
    assert all(reference.parameter_tree.topLevelItem(index).text(2) for index in range(32))
    assert [reference.parameter_tree.topLevelItem(index).text(0) for index in range(3)] == ["1", "2", "3"]
    reference.view_filter.setCurrentText("Multi-view")
    reference.source_filter.setCurrentText("RustLab1")
    app.processEvents()
    assert reference.parameter_tree.topLevelItemCount() == 64
    assert reference.count_label.text() == "Showing 64 of 64 gait parameters"
    rustlab_labels = [reference.parameter_tree.topLevelItem(index).text(1) for index in range(64)]
    assert len(set(rustlab_labels)) == 64
    assert not any("hindpaw angle" in label for label in rustlab_labels)
    assert "Left ankle average height (mm)" in rustlab_labels
    assert "Right hip displacement per step (cm)" in rustlab_labels
    assert "Left forelimb elbow angle — mean (deg)" in rustlab_labels
    assert "Right forelimb step duration (s)" in rustlab_labels
    reference.search_edit.setText("angle bottom")
    app.processEvents()
    assert reference.parameter_tree.topLevelItemCount() == 0
    reference.search_edit.setText("lfpaw")
    app.processEvents()
    assert reference.parameter_tree.topLevelItemCount() > 0
    runway.documentation_back_button.click()
    app.processEvents()
    assert runway.workspace_stack.currentIndex() == 0
    assert runway.parameter_reference_button.text() == "Parameter documentation"
    assert not runway.documentation_back_button.isVisible()
    runway.close()


def test_figure_creator_and_parameters_have_separate_full_width_documentation_pages():
    figures = gait_figure_catalog(create_gait_result_reader().preview_root)
    assert len(figures) == 25
    assert sum(figure.source == "ALMA" for figure in figures) == 7
    assert sum(figure.source == "RustLab1" for figure in figures) == 18
    assert all(figure.asset_path.is_file() for figure in figures)
    assert all(figure.asset_path.suffix == ".svg" for figure in figures)
    assert all(figure.purpose and figure.shows and figure.interpretation for figure in figures)
    excluded_text = " ".join(f"{figure.filename} {figure.title}" for figure in figures).casefold()
    assert "pca" not in excluded_text
    assert "random forest" not in excluded_text
    app = QApplication.instance() or QApplication([])
    runway = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    runway.resize(1440, 900)
    runway.show()
    runway.figure_reference_button.click()
    app.processEvents()
    reference = runway.parameter_reference
    assert runway.workspace_stack.currentWidget() is reference
    assert reference.documentation_stack.currentWidget() is reference.figure_documentation
    assert reference.parameter_documentation.isHidden()
    assert runway.documentation_back_button.isVisible()
    assert reference.figure_list.count() == 25
    assert reference.figure_preview.renderer().isValid()
    assert reference.figure_preview.width() >= 700
    assert reference.figure_preview.height() >= 210
    preview_bottom = (
        reference.figure_preview.mapTo(reference.figure_documentation, QPoint(0, 0)).y()
        + reference.figure_preview.height()
    )
    action_top = reference.open_figure_button.mapTo(reference.figure_documentation, QPoint(0, 0)).y()
    explanation = reference.findChild(QScrollArea, "FigureExplanationScroll")
    explanation_top = explanation.mapTo(reference.figure_documentation, QPoint(0, 0)).y()
    assert preview_bottom <= action_top
    assert action_top + reference.open_figure_button.height() <= explanation_top
    assert reference.figure_title_label.text() == "Gait-cycle timing"
    assert reference.figure_provenance_label.text().startswith("Generated by DLC Gait Assembler")
    reference.figure_source_filter.setCurrentText("RustLab1")
    app.processEvents()
    assert reference.figure_list.count() == 18
    assert reference.figure_source_badge.text() == "RustLab1"
    assert reference.figure_preview.renderer().isValid()
    assert "official RustLab1" in reference.figure_provenance_label.text()
    reference.figure_preview.clicked.emit()
    app.processEvents()
    assert reference._large_figure_dialog is not None
    assert reference._large_figure_dialog.figures[0].renderer().isValid()
    reference._large_figure_dialog.close()
    runway.parameter_reference_button.click()
    app.processEvents()
    assert reference.documentation_stack.currentWidget() is reference.parameter_documentation
    assert reference.figure_documentation.isHidden()
    assert reference.parameter_tree.width() > 700
    runway.close()


def test_gait_parameter_selection_is_enumerated_and_saved_in_analysis_settings():
    app = QApplication.instance() or QApplication([])
    runway = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    selection = runway.parameter_selection
    multi_names = selection.enabled_parameter_names()
    multi_alma_names = {
        name
        for name in multi_names
        if name.startswith(("left__", "right__")) and name.split("__", 1)[1] in ALMA_PARAMETER_NAMES
    }
    assert len(multi_alma_names) == 64
    assert sum(name.startswith("left__") for name in multi_alma_names) == 32
    assert sum(name.startswith("right__") for name in multi_alma_names) == 32
    assert not set(ALMA_PARAMETER_NAMES).intersection(multi_names)
    assert selection.count_label.text() == "100 of 100 parameters enabled"
    runway.limb_scope_combo.setCurrentText("Hindlimb + Forelimb")
    app.processEvents()
    assert selection.count_label.text() == "140 of 140 parameters enabled"
    assert runway.setup._collect_settings().limb_scope == "Hindlimb + Forelimb"
    runway.limb_scope_combo.setCurrentText("Hindlimb")
    app.processEvents()
    selection.clear_button.click()
    app.processEvents()
    first_visible_item = next(
        selection.tree.topLevelItem(index)
        for index in range(selection.tree.topLevelItemCount())
        if not selection.tree.topLevelItem(index).isHidden()
    )
    first_visible_item.setCheckState(1, Qt.Checked)
    app.processEvents()
    selected_name = first_visible_item.text(1)
    assert selection.count_label.text() == "100 of 100 parameters enabled"
    assert len(runway.setup._collect_settings().enabled_parameter_names) == 100
    assert not selection.clear_button.isVisible()
    runway.input_mode_combo.setCurrentText("Single side view")
    app.processEvents()
    single_names = runway.setup._collect_settings().enabled_parameter_names
    assert set(single_names) == set(ALMA_PARAMETER_NAMES)
    assert not any(name.startswith(("left__", "right__")) for name in single_names)
    assert selection.count_label.text() == "32 of 32 parameters enabled"
    runway.close()


def test_gait_settings_rows_accept_repeated_cross_row_clicks():
    app = QApplication.instance() or QApplication([])
    runway = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    runway.resize(1180, 700)
    runway.show()
    app.processEvents()
    (top_row, bottom_row) = runway.settings_section_rows
    click_sequence = ((bottom_row, 0), (top_row, 2), (bottom_row, 2), (top_row, 0)) * 3
    for row, row_index in click_sequence:
        settings_index = runway.settings_navigation_indices[runway.settings_section_rows.index(row)][row_index]
        QTest.mouseClick(row, Qt.LeftButton, pos=row.tabRect(row_index).center())
        app.processEvents()
        assert runway.settings_tabs.currentIndex() == settings_index
    runway.close()


def test_runway_light_mode_has_a_distinct_settings_tab_strip():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    runway = None
    try:
        theme.set_dark_mode(False)
        runway = AlmaKinematicsWidget(
            preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
        )
        stylesheet = runway.styleSheet()
        assert runway.settings_tabs.objectName() == "RunwaySettingsTabs"
        assert runway.settings_tabs.tabBar().isHidden()
        assert [row.count() for row in runway.settings_section_rows] == [4, 4]
        assert runway.settings_section_rows[0].property("activeRow") is True
        assert runway.settings_section_rows[1].property("activeRow") is False
        mapping_index = runway.settings_tabs.indexOf(runway.mapping_tab)
        assert mapping_index >= 0
        assert runway.settings_tabs.tabText(mapping_index) == "Mapping"
        assert _auto_bodypart_label(["iliac-crest"], "iliac crest") == "iliac-crest"
        assert "QTabBar#RunwaySettingsSectionRow::tab" in stylesheet
        assert f"background: {theme.PANEL};" in stylesheet
        assert f"background: {theme.SURFACE};" in stylesheet
    finally:
        if runway is not None:
            runway.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())


def test_gait_workspace_tabs_use_explicit_dark_mode_contrast():
    app = QApplication.instance() or QApplication([])
    previous_mode = theme.IS_DARK
    runway = None
    try:
        theme.set_dark_mode(True)
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())
        runway = AlmaKinematicsWidget(
            preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
        )
        stylesheet = runway.styleSheet()
        assert "QTabWidget#RunwayWorkspaceTabs QTabBar::tab" in stylesheet
        assert f"background: {theme.PANEL};" in stylesheet
        assert f"color: {theme.CONNECTOR};" in stylesheet
        assert f"background: {theme.SURFACE};" in stylesheet
        assert f"color: {theme.TEXT};" in stylesheet
        assert "border-bottom-color: transparent;" in stylesheet
        assert runway.workspace_tabs.tabBar()._accent == theme.TOOL_3
    finally:
        if runway is not None:
            runway.close()
        theme.set_dark_mode(previous_mode)
        app.setPalette(_dependency_theme_application_palette())
        app.setStyleSheet(_dependency_theme_application_stylesheet())


def test_runway_preview_uses_selected_multiview_set_and_all_strides(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    captured: dict[str, object] = {}

    class _Signal:
        def connect(self, *_args):
            pass

    class _PreviewThread:
        progress_updated = _Signal()
        log_message = _Signal()
        preview_ready = _Signal()
        preview_failed = _Signal()
        finished = _Signal()

        def __init__(self, csv_files, settings, *, preview):
            captured["csvs"] = [Path(path).name for (_label, path) in csv_files]
            captured["strides"] = settings.n_continuous_strides

        def start(self):
            captured["started"] = True

        def isRunning(self):
            return False

    monkeypatch.setattr(
        "dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_controller.StickPlotPreviewThread",
        _PreviewThread,
    )
    widget = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    widget.inputs._missing_required_bodyparts = lambda _settings: []
    paths = [
        tmp_path / "first_left.csv",
        tmp_path / "first_right.csv",
        tmp_path / "first_bottom.csv",
        tmp_path / "second_left.csv",
        tmp_path / "second_right.csv",
        tmp_path / "second_bottom.csv",
    ]
    for path in paths:
        path.write_text("scorer,a,a,a\nbodyparts,toe,toe,toe\ncoords,x,y,likelihood\n", encoding="utf-8")
    widget.inputs._add_csv_paths(paths)
    widget.file_list.setCurrentRow(4)
    assert not hasattr(widget, "continuous_strides_spin")
    widget.controller._generate_stickplot_preview()
    assert len(widget.state.view_sets) == 2
    assert widget.view_set_table.topLevelItemCount() == 2
    assert widget.view_set_table.currentItem().text(0) == "second"
    assert captured == {
        "csvs": ["second_left.csv", "second_right.csv", "second_bottom.csv"],
        "strides": widget.setup._collect_settings().n_continuous_strides,
        "started": True,
    }
    assert widget.preview_stack.minimumHeight() >= 280
    assert widget.workspace_tabs.currentWidget() is widget.preview_page
    widget.close()
    app.processEvents()


def test_runway_requires_complete_left_right_bottom_csv_sets(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    left = tmp_path / "mouse_left.csv"
    right = tmp_path / "mouse_right.csv"
    for path in (left, right):
        path.write_text("scorer,a,a,a\nbodyparts,toe,toe,toe\ncoords,x,y,likelihood\n", encoding="utf-8")
    widget.inputs._add_csv_paths([left, right])
    assert widget.state.view_sets == []
    assert not widget.preview_button.isEnabled()
    assert "missing bottom" in widget.view_set_status_label.text().lower()
    assert widget.view_set_table.topLevelItemCount() == 1
    assert "Missing bottom" in widget.view_set_table.topLevelItem(0).text(4)
    widget.close()
    app.processEvents()


def test_runway_previews_generated_svg_figures_and_csv_tables(tmp_path):
    app = QApplication.instance() or QApplication([])
    csv_path = tmp_path / "mouse_parameter_summary.csv"
    csv_path.write_text(
        "parameter,mean,standard_deviation\nstride_length,4.2,0.3\nstep_height,1.1,0.1\n", encoding="utf-8"
    )
    figure_folder = tmp_path / "mouse_alma_figures"
    figure_folder.mkdir()
    svg_path = figure_folder / "1_ALMA_cycle_timing.svg"
    svg_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="white"/><path d="M10 80 L80 20 L190 70" stroke="black" fill="none"/></svg>',
        encoding="utf-8",
    )
    ignored_path = tmp_path / "analysis_metadata.json"
    ignored_path.write_text("{}", encoding="utf-8")
    preview = OutputPreviewWidget(reader=create_gait_result_reader(), max_csv_rows=1, max_csv_columns=2)
    preview.load_paths((csv_path, ignored_path, svg_path, tmp_path / "missing.csv"))
    assert preview.paths == (csv_path.resolve(), svg_path.resolve())
    assert preview.selected_path == svg_path.resolve()
    assert preview.svg_preview.renderer().isValid()
    preview.file_combo.setCurrentIndex(0)
    assert preview.selected_path == csv_path.resolve()
    assert preview.csv_preview.rowCount() == 1
    assert preview.csv_preview.columnCount() == 2
    assert preview.csv_preview.horizontalHeaderItem(0).text() == "parameter"
    assert preview.csv_preview.item(0, 0).text() == "stride_length"
    runway = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    runway.controller._output_results_ready(
        (AlmaRunResult(input_file=tmp_path / "mouse_left.csv", output_files=(csv_path, ignored_path, svg_path)),)
    )
    assert runway.preview_stack.currentWidget() is runway.output_preview_view
    assert runway.workspace_tabs.currentWidget() is runway.preview_page
    assert runway.output_preview_view.selected_path == svg_path.resolve()
    assert "Loaded 2 generated output previews" in runway.log.toPlainText()
    preview.close()
    runway.close()
    app.processEvents()


def test_gait_stickplots_use_full_width_tabs_and_click_to_expand():
    app = QApplication.instance() or QApplication([])
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300"><rect width="800" height="300" fill="white"/></svg>'
    preview = StickPlotPairPreviewWidget()
    preview.load_plots((("Left", svg), ("Right", svg)))
    preview.resize(700, 360)
    preview.show()
    app.processEvents()
    assert preview.tabs.count() == 2
    assert preview.tabs.tabText(0) == "Left"
    assert preview.tabs.tabText(1) == "Right"
    assert preview._panels[0][1].renderer().aspectRatioMode() == Qt.KeepAspectRatio
    QTest.mouseClick(preview._panels[0][1], Qt.LeftButton)
    app.processEvents()
    assert preview._large_preview_dialog is not None
    assert preview._large_preview_dialog.tabs.count() == 2
    preview._large_preview_dialog.close()
    preview.close()
    app.processEvents()


def test_runway_worker_hands_generated_outputs_to_preview_signal(tmp_path, monkeypatch):
    result = AlmaRunResult(input_file=tmp_path / "mouse_left.csv", output_files=(tmp_path / "mouse_parameters.csv",))
    monkeypatch.setattr(
        "dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor.run_alma_gait_analysis",
        lambda *_args, **_kwargs: [result],
    )
    worker = AlmaAnalysisThread(
        [result.input_file], tmp_path, AlmaSettings(), analyze=create_gait_analysis_operations().analyze_alma
    )
    emitted_results = []
    completions = []
    worker.results_ready.connect(emitted_results.append)
    worker.analysis_completed.connect(lambda success, message: completions.append((success, message)))
    worker.run()
    assert emitted_results == [(result,)]
    assert completions == [(True, f"Analysis complete. Results saved to:\n{tmp_path}")]
