from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
    create_media_access,
    create_video_processing_use_cases,
)


(TOOL_SPECS, LADDER_TOOL_SPEC) = build_tool_specs()


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from PySide6.QtCore import QAbstractAnimation


from PySide6.QtTest import QTest


from PySide6.QtWidgets import (
    QApplication,
)


from dlc_gait_assembly.runway.manual.video_processing.client.video_processing_view import VideoEditorWidget


def _wait_for_animation(animation, timeout_ms: int = 1500) -> None:
    elapsed = 0
    while animation.state() == QAbstractAnimation.State.Running and elapsed < timeout_ms:
        QTest.qWait(20)
        elapsed += 20
    assert animation.state() == QAbstractAnimation.State.Stopped


from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


def test_video_export_quality_shares_operations_bar_and_sidebar_has_room():
    app = QApplication.instance() or QApplication([])
    editor = VideoEditorWidget(
        use_cases=create_video_processing_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
    )
    editor.resize(1440, 900)
    editor.show()
    app.processEvents()
    assert editor.export_quality_controls.parent().objectName() == "OperationsBar"
    assert editor.workspace_splitter.sizes()[0] >= 500
    assert editor.video_list.height() >= 180
    assert editor.settings_panel.height() >= 300
    editor.close()
