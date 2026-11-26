import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import SavedAutomaticRun
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_history_dialog import AutomaticRunHistoryDialog


def test_run_history_keeps_long_details_and_actions_inside_a_small_window(tmp_path):
    app = QApplication.instance() or QApplication([])
    message = "A long error message with diagnostic details.\n" * 200
    failed = SavedAutomaticRun(tmp_path / "failed", "Session A", "failed", 0, "2026-01-02T12:00:00", 1, message)
    completed = [
        SavedAutomaticRun(tmp_path / str(index), f"Session B {index}", "complete", 0, "2026-01-01T12:00:00", 1)
        for index in range(100)
    ]
    opened = []
    dialog = AutomaticRunHistoryDialog(None, [failed, *completed], open_outputs=opened.append)
    dialog.resize(400, 250)
    dialog.show()
    app.processEvents()

    assert dialog.width() == 400
    assert dialog.height() == 250
    assert dialog.details.verticalScrollBar().maximum() > 0
    assert dialog.runs.verticalScrollBar().maximum() > 0
    assert dialog.rect().contains(dialog.open_button.mapTo(dialog, dialog.open_button.rect().bottomRight()))
    assert message.strip() in dialog.details.toPlainText()
    assert dialog.details.isReadOnly()

    dialog.search.setText("COMPLETE")
    assert dialog.selected_run == completed[0]
    assert not dialog.resume_button.isEnabled()
    QTest.keyClick(dialog.search, Qt.Key_Return)
    QTest.keyClick(dialog.runs, Qt.Key_Down)
    assert dialog.selected_run == completed[1]
    dialog.open_button.click()
    assert opened == [completed[1].output_folder]

    dialog.search.setText("missing")
    assert dialog.selected_run is None
    assert not dialog.open_button.isEnabled()
    assert "No saved runs match" in dialog.details.toPlainText()

    dialog.search.setText("2026-01-02")
    assert dialog.selected_run == failed
    dialog.resume_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
