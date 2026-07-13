from __future__ import annotations

import json
import os

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from dlc_gait_assembly.gui.gait_analysis.window import AlmaKinematicsWidget
from dlc_gait_assembly.services.analysis_manifests import (
    knee_settings_from_manifest,
    read_analysis_manifest,
    read_knee_analysis_manifest,
    read_video_settings_manifest,
    video_settings_from_manifest,
    write_knee_analysis_manifest,
    write_video_settings_manifest,
)
from dlc_gait_assembly.services.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.services.domain.regions import CropRegion, NormalizedRect
from dlc_gait_assembly.services.domain.trimming import TrimRange
from dlc_gait_assembly.services.knee_correction import KneeCorrectionSettings
from dlc_gait_assembly.services.video_processing import ProcessingOptions


def test_manual_gait_analysis_button_exports_current_settings(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(AlmaKinematicsWidget, "_default_output_root", lambda _self: tmp_path)
    widget = AlmaKinematicsWidget()
    destination = tmp_path / "analysis_manifest.json"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "JSON files (*.json)"),
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


def test_video_settings_manifest_round_trips_processing_options(tmp_path):
    destination = tmp_path / "video_settings_manifest.json"
    write_video_settings_manifest(
        destination,
        ProcessingOptions(
            crop_enabled=True,
            crop_regions=(
                CropRegion(
                    "Left view",
                    NormalizedRect(0.1, 0.2, 0.3, 0.4),
                    flip_horizontal=True,
                    flip_vertical=True,
                    flip_horizontal_video_paths=frozenset({"/tmp/source.mp4"}),
                ),
            ),
            invert_enabled=True,
            invert_rects=(NormalizedRect(0.5, 0.6, 0.2, 0.1),),
            enhancements=EnhancementSettings(brightness=0.2, contrast=1.2),
        ),
        {"source.mp4": (TrimRange(100, 900),)},
    )

    manifest = read_video_settings_manifest(destination)
    options, trims = video_settings_from_manifest(destination)

    assert manifest["manifest_type"] == "dlc-gait-assembler.video-settings"
    assert options.crop_regions[0].name == "Left view"
    assert options.crop_regions[0].flip_horizontal is True
    assert options.invert_rects[0] == NormalizedRect(0.5, 0.6, 0.2, 0.1)
    assert options.enhancements.brightness == 0.2
    assert options.enhancements.contrast == 1.2
    assert trims["source.mp4"] == (TrimRange(100, 900),)

    processing_manifest = tmp_path / "processing_manifest.json"
    processing_manifest.write_text(
        json.dumps(
            {
                "format": {"crf": 16, "preset": "medium"},
                "operations": {
                    "crop_regions": [
                        {
                            "name": "Legacy",
                            "rect": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.5},
                        }
                    ],
                    "invert_regions": [],
                    "enhancements": {"brightness": 0.3},
                },
                "files": [
                    {
                        "input": str(tmp_path / "legacy.mp4"),
                        "trim_ranges": [{"start_ms": 50, "end_ms": 150}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    legacy_options, legacy_trims = video_settings_from_manifest(processing_manifest)
    assert legacy_options.crop_regions[0].name == "Legacy"
    assert legacy_options.crf == 16
    assert legacy_options.enhancements.brightness == 0.3
    assert legacy_trims["legacy.mp4"] == (TrimRange(50, 150),)


def test_knee_analysis_manifest_round_trips_settings(tmp_path):
    destination = tmp_path / "knee_analysis_manifest.json"
    settings = KneeCorrectionSettings(
        hip_knee_length_cm=1.5,
        knee_ankle_length_cm=1.7,
        pixels_per_cm=42.0,
        likelihood_threshold=0.6,
        knee_bodyparts=("patella",),
        hip_bodypart="hip",
        ankle_bodypart="ankle",
        output_knee_bodypart="knee_corrected",
        knee_direction="positive",
    )

    write_knee_analysis_manifest(destination, settings)

    manifest = read_knee_analysis_manifest(destination)
    assert manifest["manifest_type"] == "dlc-gait-assembler.knee-analysis"
    assert knee_settings_from_manifest(destination) == settings
