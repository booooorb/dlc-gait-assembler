from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
    create_automatic_workspace,
    create_main_window,
)


(TOOL_SPECS, LADDER_TOOL_SPEC) = build_tool_specs()


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from PySide6.QtCore import QAbstractAnimation, QSize, Qt


from PySide6.QtTest import QTest


from PySide6.QtWidgets import (
    QApplication,
    QLabel,
)


import dlc_gait_assembly.shared.client.theme.theme_application_state as theme


from dlc_gait_assembly.runway.automatic.review.client.automatic_review_stickplot_panel import render_svg_pixmap


def _wait_for_animation(animation, timeout_ms: int = 1500) -> None:
    elapsed = 0
    while animation.state() == QAbstractAnimation.State.Running and elapsed < timeout_ms:
        QTest.qWait(20)
        elapsed += 20
    assert animation.state() == QAbstractAnimation.State.Stopped


def test_automation_menus_keep_guidance_in_control_tooltips():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    widget = window._main_menu.automated_profiles
    assert not widget.findChildren(QLabel, "AutomatedProfileDescription")
    assert not widget.findChildren(QLabel, "ProfileStageDescription")
    assert not widget.findChildren(QLabel, "ProfileStageTitle")
    assert widget.automation_console.toPlainText() == "[Ready]"
    assert widget.pipeline_log_state.text() == "●  Ready"
    assert widget.pipeline_log_state.property("logState") == "ready"
    assert widget.run_readiness_label.text() == "●  Ready"
    assert widget.run_readiness_label.property("readinessState") == "ready"
    interactive_controls = [
        window._automation_run_button,
        window._automation_profiles_button,
        widget.profile_selector,
        widget.duplicate_profile_button,
        widget.open_profile_configuration_button,
        widget.upload_videos_button,
        widget.remove_videos_button,
        widget.clear_videos_button,
        widget.video_list,
        widget.automation_console,
        widget.run_pipeline_button,
        widget.back_to_automation_button,
        widget.new_profile_button,
        widget.configuration_profile_selector,
        widget.profile_name,
        widget.delete_profile_button,
        widget.manifest_upload_button,
        widget.calibration_upload_button,
        widget.analysis_manifest_upload_button,
        widget.knee_manifest_upload_button,
        widget.save_profile_button,
        widget.pipeline_review_video_list,
        widget.pipeline_component_tabs,
        widget.pipeline_change_settings_button,
        widget.pipeline_needs_changes_button,
        widget.pipeline_approve_button,
    ]
    assert all(control.toolTip().strip() for control in interactive_controls)
    assert all(
        widget.configuration_tabs.tabToolTip(index).strip() for index in range(widget.configuration_tabs.count())
    )
    window.close()
    app.processEvents()


def test_automated_workspace_has_clear_input_activity_and_run_hierarchy(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    widget = window._main_menu.automated_profiles
    assert window.findChild(QLabel, "AppMark") is None
    assert window.findChild(QLabel, "AutomationPageSubtitle") is None
    assert not window.findChildren(QLabel, "AutomationPanelSubtitle")
    assert widget.run_status_bar.objectName() == "RunStatusBar"
    assert widget.upload_videos_button.text() == "Add videos"
    assert not widget.upload_videos_button.icon().isNull()
    assert widget.upload_videos_button.parent() is widget.video_list.viewport()
    assert widget.upload_videos_button.isVisibleTo(widget.video_list)
    assert widget.duplicate_profile_button.parentWidget().objectName() == "ProfileManagementPanel"
    assert not widget.remove_videos_button.icon().isNull()
    assert not widget.clear_videos_button.icon().isNull()
    assert not widget.open_profile_configuration_button.icon().isNull()
    assert not widget.pipeline_change_settings_button.icon().isNull()
    assert widget.run_readiness_label.objectName() == "RunReadinessBadge"
    assert widget.run_readiness_label.text() == "●  Ready"
    assert widget.run_readiness_label.property("readinessState") == "ready"
    assert "QPushButton#RemoveButton, QPushButton#ClearButton" in widget.styleSheet()
    assert "QLabel#PipelineLogState {\n    background: transparent;\n    border: 0;" in widget.styleSheet()
    assert (
        "QLabel#ProfileStatusLabel, QLabel#RunReadinessBadge {\n    background: transparent;\n    border: 0;"
        in widget.styleSheet()
    )
    assert theme.STATUS_ERROR in widget.styleSheet()
    assert not widget.remove_videos_button.isEnabled()
    assert not widget.clear_videos_button.isEnabled()
    assert "Drop source videos" in widget.video_list.accessibleDescription()
    video = tmp_path / "mouse_walk.mp4"
    video.write_bytes(b"fixture")
    widget.queue._add_video_paths([video])
    assert widget.video_count_label.text() == "1 video"
    assert widget.remove_videos_button.isEnabled()
    assert widget.clear_videos_button.isEnabled()
    assert widget.video_list.item(0).toolTip() == str(video.resolve())
    widget.queue._clear_videos()
    assert not widget.remove_videos_button.isEnabled()
    assert not widget.clear_videos_button.isEnabled()
    window.close()


def test_pipeline_geometry_stays_constant_through_stickplot_review():
    app = QApplication.instance() or QApplication([])
    window = create_main_window()
    window.show()
    window.resize(1180, 700)
    app.processEvents()
    widget = window._main_menu.automated_profiles
    window.routes._show_automated_pipeline()
    app.processEvents()
    initial_geometry = {
        "window": window.geometry(),
        "workspace": window._main_menu._content.geometry(),
        "pipeline": widget.geometry(),
        "input": widget.automation_input_stack.geometry(),
        "console": widget.automation_console_panel.geometry(),
    }
    preview_hint = widget.pipeline_stickplot_preview.sizeHint()
    widget.set_pipeline_running(True)
    assert widget.run_readiness_label.text() == "●  Running"
    assert widget.run_readiness_label.property("readinessState") == "running"
    widget.set_pipeline_stage(4, progress=100)
    widget.reviews._pause_for_pipeline_review(4)
    app.processEvents()
    assert widget.run_readiness_label.text() == "●  Review required"
    assert widget.run_readiness_label.property("readinessState") == "review"
    assert window.geometry() == initial_geometry["window"]
    assert window._main_menu._content.geometry() == initial_geometry["workspace"]
    assert widget.geometry() == initial_geometry["pipeline"]
    assert widget.automation_input_stack.geometry() == initial_geometry["input"]
    assert widget.automation_console_panel.geometry() == initial_geometry["console"]
    assert widget.pipeline_stickplot_preview.sizeHint() == preview_hint
    window.close()


def test_pipeline_stickplot_preserves_aspect_ratio_and_opens_on_click():
    app = QApplication.instance() or QApplication([])
    widget = create_automatic_workspace()
    preview = widget.pipeline_stickplot_preview
    preview.resize(360, 240)
    widget.reviews._populate_pipeline_review_preview(4)
    app.processEvents()
    assert widget._pipeline_stickplot_path.name == "stickplot.svg"
    assert widget.pipeline_review_layout.stretch(0) == 2
    assert widget.pipeline_review_layout.stretch(1) == 1
    svg_text = widget._pipeline_stickplot_path.read_text(encoding="utf-8")
    assert "matplotlib.axis_1" in svg_text
    assert "Demo stickplot preview" not in svg_text
    rendered = preview.pixmap()
    assert preview._source_svg_data is not None
    assert rendered.size() == preview.contentsRect().size()
    high_dpi = render_svg_pixmap(preview._source_svg_data, QSize(360, 240), device_pixel_ratio=2.0)
    assert high_dpi.size() == QSize(720, 480)
    assert high_dpi.devicePixelRatio() == 2.0
    QTest.mouseClick(preview, Qt.LeftButton, pos=preview.rect().center())
    app.processEvents()
    assert widget._large_review_dialog is not None
    assert widget._large_review_dialog.image_loaded
    assert widget._large_review_dialog.preview._source_svg_data is not None
    widget._large_review_dialog.close()
    widget.close()
    app.processEvents()


def test_automatic_surface_split_preserves_original_stylesheet_cascade():
    import hashlib
    from dlc_gait_assembly.runway.automatic.client.automatic_workspace_styles import AUTOMATED_PIPELINE_QSS

    assert (
        hashlib.sha256(AUTOMATED_PIPELINE_QSS.encode()).hexdigest()
        == "085bba4e35864952d214ecd0ba2a6ee59b38b60e54895875b4ce87ec44a40a57"
    )
