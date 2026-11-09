"""Measured camera maps must survive profiles and reach real preview and CSV calculations."""

import json
import shutil
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_repository import (
    AutomatedProfileStore,
)
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_coordinator import AutomatedPipelineRun
from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_storage import AutomaticRunStorage
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import (
    CalibrationPoint,
    CalibrationStick,
)
from dlc_gait_assembly.runway.manual.calibration.business.calibration_use_cases import calculate_calibration_report
from dlc_gait_assembly.runway.manual.calibration.infrastructure.calibration_export_writer import (
    write_calibration_conversion_export,
)
from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import DlcAnalysisResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import settings_for_view
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
    camera_map_scales,
    resolve_calibration_settings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_preview_writer import (
    write_gait_stickplot_previews,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
    run_alma_gait_analysis_in_process,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    alma_settings_from_manifest,
    write_analysis_manifest,
)
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import (
    ProcessingOptions,
    ProcessingResult,
)
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import CropRegion, NormalizedRect
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    write_video_settings_manifest,
)
from tests.runway.automatic.profiles.client.test_automatic_profile_editor import _profile_sources
from tests.runway.manual.gait_analysis.infrastructure.test_single_gait_csv import recording


@pytest.fixture
def measured_camera_map(tmp_path):
    sticks = []
    for view, x_scale, y_scale in ((1, 25, 25), (2, 100, 100), (3, 80, 40)):
        sticks.extend(
            (
                CalibrationStick("x", view, CalibrationPoint(0, 0), CalibrationPoint(x_scale, 0), ()),
                CalibrationStick("y", view, CalibrationPoint(0, 0), CalibrationPoint(0, y_scale), ()),
            )
        )
    report = calculate_calibration_report(sticks)
    return write_calibration_conversion_export(tmp_path / "measured", sticks, report)["map"]


def per_camera_settings(path):
    return AlmaSettings(
        analysis_type="Spontaneous walking",
        calibration_method="per_view",
        pixels_per_cm=999,
        calibration_map_path="/inactive/shared.json",
        likelihood_threshold=0,
        no_outlier_filter=True,
        step_height_max_cm=100,
        stride_length_max_cm=100,
        generate_alma_representations=False,
        generate_rustlab1_parameters=False,
        view_calibration={
            camera: {"map_path": str(path), "view_index": index}
            for camera, index in (("left", 1), ("right", 2), ("bottom", 3))
        },
    )


def test_measured_maps_apply_to_preview_exports_and_bottom_axes(tmp_path, alma_fixtures_dir, measured_camera_map):
    from dlc_gait_assembly.app.app_bootstrap import create_gait_preview

    item = recording(tmp_path, alma_fixtures_dir, "calibrated")
    settings = per_camera_settings(measured_camera_map)
    manifest = write_analysis_manifest(tmp_path / "analysis.json", settings)
    measured_camera_map.unlink()
    settings = alma_settings_from_manifest(manifest, tmp_path / "inactive-global-map.json")
    assert settings.pixels_per_cm is settings.calibration_map_path is None
    assert settings.view_calibration["left"]["pixels_per_cm"] == 25
    assert settings.view_calibration["right"]["pixels_per_cm"] == 100
    inputs = tuple((camera.title(), getattr(item, f"{camera}_csv")) for camera in ("left", "right", "bottom"))
    plots, _, messages = create_gait_preview().prepare(inputs, settings)
    assert len(plots) == 2
    assert any("Left:" in message and "Calibration: 25.0 px/cm" in message for message in messages)
    assert any("Right:" in message and "Calibration: 100.0 px/cm" in message for message in messages)
    results = run_alma_gait_analysis_in_process([item], tmp_path / "results", settings)
    left = pd.read_csv(next(p for p in results[0].output_files if p.name == "left_stride_parameters.csv"))
    right = pd.read_csv(next(p for p in results[0].output_files if p.name == "right_stride_parameters.csv"))
    assert left["stride length (cm)"].notna().any()
    np.testing.assert_allclose(left["stride length (cm)"], right["stride length (cm)"] * 4, equal_nan=True)
    np.testing.assert_allclose(left["l-back-ankle__Movement"], right["r-back-ankle__Movement"] * 4, equal_nan=True)
    np.testing.assert_allclose(
        left["step height (cm)"], right["step height (cm)"] * 4, equal_nan=True
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.retired_custom_parameters import RETIRED_CUSTOM_NAMES
    assert not RETIRED_CUSTOM_NAMES.intersection(left)
    assert not RETIRED_CUSTOM_NAMES.intersection(right)
    general = pd.read_csv(next(p for p in results[0].output_files if p.name == "general_parameters.csv")).iloc[0]
    assert general["calibration_method"] == "per_view"
    assert (general["left_pixels_per_cm"], general["right_pixels_per_cm"]) == (25, 100)
    assert (general["bottom_x_pixels_per_cm"], general["bottom_y_pixels_per_cm"]) == (80, 40)


def test_profile_owns_camera_scale_snapshots_without_a_global_map(tmp_path, measured_camera_map):
    sources = _profile_sources(tmp_path)
    manifest = write_analysis_manifest(tmp_path / "per_camera.json", per_camera_settings(measured_camera_map))
    profile = AutomatedProfileStore(tmp_path / "profiles").save(
        "Per camera",
        sources["processing_manifest"],
        None,
        sources["deeplabcut_models"],
        analysis_manifest=manifest,
    )
    measured_camera_map.unlink()
    manifest.unlink()
    assert profile.calibration_map is None
    saved = AutomaticRunStorage().gait_settings(profile.analysis_manifest, profile.calibration_map)
    assert saved.calibration_method == "per_view"
    assert settings_for_view(saved, "left").pixels_per_cm == 25
    assert settings_for_view(saved, "right").pixels_per_cm == 100


def test_automatic_pipeline_runs_real_calibrated_preview_and_analysis(tmp_path, alma_fixtures_dir, measured_camera_map):
    regions = ("Left view", "Right view", "Bottom view")
    item = recording(tmp_path, alma_fixtures_dir, "source")
    video_manifest = write_video_settings_manifest(
        tmp_path / "video.json",
        ProcessingOptions(
            crop_enabled=True,
            crop_regions=tuple(CropRegion(name, NormalizedRect(i / 4, 0, 0.2, 0.8)) for i, name in enumerate(regions)),
        ),
    )
    manifest = write_analysis_manifest(tmp_path / "gait.json", per_camera_settings(measured_camera_map))
    profile = AutomatedPipelineProfile(
        "a" * 32,
        "Camera calibration",
        video_manifest,
        None,
        {region: tmp_path / "model" for region in regions},
        analysis_manifest=manifest,
    )
    source_video = tmp_path / "mouse.mp4"
    source_video.write_bytes(b"fixture video")

    def process(input_path, destination, options, **_):
        results = []
        for region in regions:
            output = destination / region / "mouse_processed.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"processed video")
            results.append(ProcessingResult(input_path, output, [], crop_region_name=region))
        return results

    def dlc(jobs, destination, progress=None):
        results = []
        for job in jobs:
            folder = destination / job.region
            folder.mkdir(parents=True)
            csv = folder / "mouse_processedDLC_fixture.csv"
            camera = job.region.split()[0].lower()
            shutil.copyfile(getattr(item, f"{camera}_csv"), csv)
            h5 = csv.with_suffix(".h5")
            h5.write_bytes(b"paired h5")
            results.append(DlcAnalysisResult(job.region, job.video_paths, (csv,), (h5,), ()))
        return results

    def label(jobs, results, destination, progress=None):
        labeled = []
        for result in results:
            path = destination / result.region / "mouse_processedDLC_fixture_labeled.mp4"
            path.write_bytes(b"labeled video")
            labeled.append(replace(result, labeled_video_paths=(path,)))
        return labeled

    operations = SimpleNamespace(
        video=SimpleNamespace(process_outputs=process),
        knee=None,
        deeplabcut_analysis=dlc,
        labeled_videos=label,
        stickplots=write_gait_stickplot_previews,
        gait=run_alma_gait_analysis_in_process,
    )
    run = AutomatedPipelineRun(
        profile, [source_video], tmp_path, tmp_path / "runs", operations=operations, storage=AutomaticRunStorage()
    )
    # A changed or removed source map after start cannot alter the approved preview's calibration.
    measured_camera_map.unlink()
    manifest.write_text("{}")
    for stage in range(6):
        run.run_stage(stage)
    assert len(run.stickplot_results) == len(run.gait_results) == 1
    assert len(run.stickplot_results[0].output_files) == 2
    assert all(path.stat().st_size > 100 for path in run.stickplot_results[0].output_files)
    report = next(p for p in run.gait_results[0].output_files if p.name == "export_report.txt").read_text()
    assert "Calibration mode: per_view" in report
    assert "Left calibration: 25.0" in report and "Right calibration: 100.0" in report
    tables = {
        side: pd.read_csv(
            next(p for p in run.gait_results[0].output_files if p.name == f"{side}_stride_parameters.csv")
        )
        for side in ("left", "right")
    }
    np.testing.assert_allclose(tables["left"]["stride length (cm)"], tables["right"]["stride length (cm)"] * 4)


def test_invalid_camera_never_falls_back_to_overall_or_shared_scale(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(
        json.dumps(
            {
                "overall": {"pixels_per_centimeter": 50},
                "views": {
                    "1": {"pixels_per_centimeter": -1},
                    "2": {"pixels_per_centimeter": 25},
                },
            }
        )
    )
    with pytest.raises(ValueError, match="no usable scale for view 1"):
        camera_map_scales(path, 1)
    settings = resolve_calibration_settings(
        AlmaSettings(calibration_method="per_view", pixels_per_cm=999, view_calibration={"left": 25})
    )
    with pytest.raises(ValueError, match="right camera"):
        settings_for_view(settings, "right")


@pytest.mark.parametrize("analysis_type", ("Treadmill", "Spontaneous walking"))
def test_reference_mode_ignores_stale_global_and_camera_scales(alma_fixtures_dir, analysis_type):
    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    settings = AlmaSettings(analysis_type=analysis_type, calibration_method="reference", likelihood_threshold=0)
    baseline = calculate_alma_recording(raw, settings)
    stale = replace(settings, pixels_per_cm=999, view_calibration={"left": 999}, calibration_map_path="/missing.json")
    actual = calculate_alma_recording(raw, resolve_calibration_settings(stale))
    assert actual[1].attrs["pixels_per_cm"] == baseline[1].attrs["pixels_per_cm"]
