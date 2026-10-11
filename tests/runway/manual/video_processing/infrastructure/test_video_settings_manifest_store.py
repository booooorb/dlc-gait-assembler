from __future__ import annotations


import json


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    read_video_settings_manifest,
)


from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    video_settings_from_manifest,
)


from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    write_video_settings_manifest,
)


from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings


from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import CropRegion


from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import NormalizedRect


from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange


from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions


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
    (options, trims) = video_settings_from_manifest(destination)
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
                    "crop_regions": [{"name": "Legacy", "rect": {"x": 0.2, "y": 0.3, "width": 0.4, "height": 0.5}}],
                    "invert_regions": [],
                    "enhancements": {"brightness": 0.3},
                },
                "files": [{"input": str(tmp_path / "legacy.mp4"), "trim_ranges": [{"start_ms": 50, "end_ms": 150}]}],
            }
        ),
        encoding="utf-8",
    )
    (legacy_options, legacy_trims) = video_settings_from_manifest(processing_manifest)
    assert legacy_options.crop_regions[0].name == "Legacy"
    assert legacy_options.crf == 16
    assert legacy_options.enhancements.brightness == 0.3
    assert legacy_trims["legacy.mp4"] == (TrimRange(50, 150),)
