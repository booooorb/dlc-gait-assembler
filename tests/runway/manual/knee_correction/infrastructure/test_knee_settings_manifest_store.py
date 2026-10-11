from __future__ import annotations


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
    knee_settings_from_manifest,
)


from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
    read_knee_analysis_manifest,
)


from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
    write_knee_analysis_manifest,
)


from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings


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
