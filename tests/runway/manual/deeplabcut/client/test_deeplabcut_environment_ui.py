from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_controller import DeepLabCutController


from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
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


from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_controller import DEEPLABCUT_INSTALL_COMMAND


from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_view import DeepLabCutWidget


def _wait_for_animation(animation, timeout_ms: int = 1500) -> None:
    elapsed = 0
    while animation.state() == QAbstractAnimation.State.Running and elapsed < timeout_ms:
        QTest.qWait(20)
        elapsed += 20
    assert animation.state() == QAbstractAnimation.State.Stopped


from dlc_gait_assembly.app.app_bootstrap import create_deeplabcut_environment


def test_deeplabcut_check_and_install_show_animated_progress(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(DeepLabCutController, "_check_deeplabcut_available", lambda self: None)
    widget = DeepLabCutWidget(environment=create_deeplabcut_environment())
    widget.status_presenter._set_progress_busy("Checking for DeepLabCut…")
    assert widget.progress.minimum() == 0
    assert widget.progress.maximum() == 0
    assert widget.progress.format() == "Checking for DeepLabCut…"
    assert widget.progress._timer.isActive()
    widget._running_command = DEEPLABCUT_INSTALL_COMMAND
    widget.status_presenter._set_running(True)
    widget.status_presenter._set_progress_busy("Installing DeepLabCut…")
    assert widget.install_button.text() == "Installing..."
    assert widget.progress.format() == "Installing DeepLabCut…"
    assert widget.progress._timer.isActive()
    widget._process = None
    widget._running_command = None
    widget.status_presenter._set_running(False)
    widget.close()
