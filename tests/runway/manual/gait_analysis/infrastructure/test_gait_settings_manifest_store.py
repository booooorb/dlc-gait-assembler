from __future__ import annotations


from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations


from dlc_gait_assembly.app.app_bootstrap import create_gait_preview


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget


from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    read_analysis_manifest,
)


from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


def test_manual_gait_analysis_button_exports_current_settings(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(AlmaKinematicsWidget, "_default_output_root", lambda _self: tmp_path)
    widget = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    destination = tmp_path / "analysis_manifest.json"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", lambda *_args, **_kwargs: (str(destination), "JSON files (*.json)")
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    widget.analysis_type_combo.setCurrentText("Spontaneous walking")
    widget.frame_rate_spin.setValue(240.0)
    widget.drag_clearance_spin.setValue(0.25)
    widget.export_manifest_button.click()
    manifest = read_analysis_manifest(destination)
    settings = manifest["analysis_settings"]
    assert settings["analysis_type"] == "Spontaneous walking"
    assert settings["frame_rate"] == 240.0
    assert settings["drag_clearance_cm"] == 0.25
    assert "Analysis manifest exported" in widget.log.toPlainText()
    widget.close()
    app.processEvents()


def test_analysis_manifest_reader_rejects_unrelated_json(tmp_path):
    unrelated = tmp_path / "not_an_analysis_manifest.json"
    unrelated.write_text('{"settings": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a gait analysis manifest"):
        read_analysis_manifest(unrelated)
