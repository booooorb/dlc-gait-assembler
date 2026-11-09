"""Check native CSV contracts, original R measurements and per-session statistics."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
    ALMA_REMOVED_VARIABILITY_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
    run_alma_gait_analysis_in_process,
    settings_from_json,
    settings_to_json,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.rustlab_bottom_executor import RustLabBottomExecutor
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommandResult

FIXTURE = Path(__file__).parents[4] / "fixtures" / "gait"
RAW_HEADER = '"","full_id","day","mouse","Measure","Value","ParameterGroup"'
SUMMARY_HEADER = '"","day","Measure","ParameterGroup","Mean","median","sd","sem"'


@pytest.fixture(scope="module")
def r_runtime():
    executable = shutil.which("Rscript")
    if executable is None:
        pytest.skip("Rscript is not installed")
    result = subprocess.run(
        [executable, "-e", "library(dplyr);library(tidyr);library(jsonlite)"], capture_output=True, text=True
    )
    if result.returncode:
        pytest.skip("R regression needs dplyr, tidyr and jsonlite")
    return executable


def reference_inputs():
    folder = FIXTURE / "rustlab1_r_reference"
    return AlmaViewCsvSet(
        "native_session", *(folder / f"{side}.csv" for side in ("left", "right", "bottom")),
        StrokeStudyMetadata(animal_id="M3", timepoint="7days", session_id="session_1"),
    )


def native_settings(**options):
    return replace(AlmaSettings(
        output_format="alma_side_rust_bottom", analysis_type="Spontaneous walking",
        stride_detection_method="Speed mixture (GMM)", frame_rate=239.76, pixels_per_cm=31.3667,
        generate_stickplot=False, generate_alma_representations=False, no_outlier_filter=True,
    ), **options)


@pytest.fixture(scope="module")
def native_run(r_runtime, tmp_path_factory):
    item, settings = reference_inputs(), native_settings()
    result = run_alma_gait_analysis_in_process([item], tmp_path_factory.mktemp("native_gait"), settings)[0]
    return item, settings, result


def test_native_alma_csvs_equal_upstream_writer_minus_variability(native_run):
    item, settings, result = native_run
    folder = result.output_files[0].parent
    for side in ("left", "right"):
        raw = pd.read_csv(getattr(item, f"{side}_csv"), header=[1, 2])
        expected = calculate_alma_recording(raw, settings)[0].drop(columns=list(ALMA_REMOVED_VARIABILITY_NAMES))
        actual_path = folder / f"{side}_stride_parameters.csv"
        assert actual_path.read_text() == expected.to_csv()
        assert "swing_phase" not in actual_path.read_text()
        assert "reference_view" not in actual_path.read_text()
    assert {path.name for path in result.output_files} == {
        "left_stride_parameters.csv", "right_stride_parameters.csv", "all_raw_data.csv",
        "all_summarized_data.csv", "Rust_bottom_R.log",
    }


def test_all_alma_session_means_and_sample_sd_use_every_side_stride(native_run):
    _item, _settings, result = native_run
    folder = result.output_files[0].parent
    assert (folder / "all_raw_data.csv").read_text().splitlines()[0] == RAW_HEADER
    assert (folder / "all_summarized_data.csv").read_text().splitlines()[0] == SUMMARY_HEADER
    raw = pd.read_csv(folder / "all_raw_data.csv", index_col=0)
    assert raw.full_id.eq("session_1").all() and raw.mouse.eq("M3").all() and raw.day.eq("7days").all()
    assert len(raw) == 20 + 2 * 2 * len(ALMA_PARAMETER_NAMES)
    assert len(raw.loc[raw.ParameterGroup.ne("ALMA_sidePersp")]) == 20
    stats = raw.set_index("Measure").Value
    for side in ("left", "right"):
        table = pd.read_csv(folder / f"{side}_stride_parameters.csv", index_col=0)
        for name in ALMA_PARAMETER_NAMES:
            values = pd.to_numeric(table[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
            np.testing.assert_allclose(stats[f"{side}__{name}__mean"], values.mean(), equal_nan=True)
            np.testing.assert_allclose(stats[f"{side}__{name}__sd"], values.std(ddof=1), equal_nan=True)


def test_default_figures_and_stickplots_are_reported_as_real_artifacts(native_run, tmp_path):
    item, settings, _result = native_run
    result = run_alma_gait_analysis_in_process(
        [item], tmp_path, replace(settings, generate_stickplot=True, generate_alma_representations=True)
    )[0]
    assert len(result.output_files) == 21
    assert sum(path.suffix == ".svg" for path in result.output_files) == 16
    assert sum(path.suffix == ".csv" for path in result.output_files) == 4
    assert all(path.is_file() and path.stat().st_size for path in result.output_files)


def test_plain_alma_never_reads_bottom_or_runs_r(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Plain ALMA invoked the underside R analysis")

    monkeypatch.setattr(RustLabBottomExecutor, "run", forbidden)
    item = replace(reference_inputs(), bottom_csv=tmp_path / "absent_bottom.csv")
    result = run_alma_gait_analysis_in_process([item], tmp_path / "out", native_settings(output_format="alma"))[0]
    assert {path.name for path in result.output_files} == {"left_stride_parameters.csv", "right_stride_parameters.csv"}


def synthetic_bottom(path):
    """Four offset paw cycles and measured centers; golden output comes from the original Rmd."""
    frames, values, parts = np.arange(360), {}, []
    for i, paw in enumerate(("d-back-left", "d-back-right", "d-front-left", "d-front-right")):
        x = 100 + np.cumsum(np.where((frames + i * 10) % 40 < 20, 1.0, 11.0)) + i * 5
        parts.append(x)
        for axis, data in (("x", x), ("y", 140.0 + i * 5), ("likelihood", 1.0)):
            values["scorer", paw, axis] = np.broadcast_to(data, frames.shape)
    for marker, children in (("d-center-back", (0, 1)), ("d-center-front", (2, 3))):
        for axis, data in (("x", np.mean([parts[i] for i in children], axis=0)), ("y", 155.0), ("likelihood", 1.0)):
            values["scorer", marker, axis] = np.broadcast_to(data, frames.shape)
    frame = pd.DataFrame(values)
    frame.to_csv(path)
    return path


def test_all_twenty_bottom_values_match_original_rustlab_r_notebook(r_runtime, tmp_path):
    bottom = synthetic_bottom(tmp_path / "bottom.csv")
    item = AlmaViewCsvSet("7days_Mouse_M1", bottom, bottom, bottom, StrokeStudyMetadata(animal_id="M1", timepoint="7days"))
    sides = {}
    for side, sample in (("left", [1.0, 2.0, 5.0]), ("right", [np.nan, 4.0, np.nan])):
        sides[side] = tmp_path / f"{side}.csv"
        pd.DataFrame({name: sample for name in ALMA_PARAMETER_NAMES}).to_csv(sides[side])
    settings = native_settings(frame_rate=60, pixels_per_cm=31.37)
    paths, _notes = RustLabBottomExecutor().run(item, tmp_path, settings, sides)
    expected = pd.read_csv(FIXTURE / "rust_bottom" / "original_20.csv")
    actual = pd.read_csv(paths[0])
    pd.testing.assert_frame_equal(actual.iloc[:20], expected, atol=1e-10, rtol=1e-10)
    statistics = actual.set_index("Measure").Value
    assert statistics["right__stride length (cm)__mean"] == 4.0
    assert pd.isna(statistics["right__stride length (cm)__sd"])
    assert statistics["left__stride length (cm)__sd"] == pytest.approx(np.std([1, 2, 5], ddof=1))


def test_r_failure_is_reported_without_python_substitution(tmp_path):
    class FailedSession:
        def run(self, command):
            assert Path(command.arguments[1]).name == "Run_ALMA_Side_Rust_Bottom.R"
            return ExternalCommandResult(1, "missing R dependency")

    item = reference_inputs()
    executor = RustLabBottomExecutor(rscript=shutil.which("python"), session_factory=FailedSession)
    with pytest.raises(RuntimeError, match="missing R dependency"):
        executor.run(item, tmp_path, native_settings(), {"left": tmp_path / "left.csv", "right": tmp_path / "right.csv"})
    assert not (tmp_path / "all_raw_data.csv").exists()


def test_missing_markers_calibration_and_empty_stride_statistics_remain_na(r_runtime, tmp_path):
    bottom = synthetic_bottom(tmp_path / "bottom.csv")
    frame = pd.read_csv(bottom, header=[0, 1, 2], index_col=0)
    frame.loc[:, frame.columns.get_level_values(1).isin(("d-back-left", "d-back-right"))].to_csv(bottom)
    item = replace(reference_inputs(), bottom_csv=bottom)
    sides = {side: tmp_path / f"{side}.csv" for side in ("left", "right")}
    for side, sample in (("left", []), ("right", [4.0])):
        pd.DataFrame({name: sample for name in ALMA_PARAMETER_NAMES}).to_csv(sides[side])
    settings = native_settings(
        calibration_method="per_view", pixels_per_cm=None, view_calibration={"left": 20, "right": 80}
    )
    paths, notes = RustLabBottomExecutor().run(item, tmp_path, settings, sides)
    values = pd.read_csv(paths[0]).set_index("Measure").Value
    assert values[["FLBR_RATIO", "FRBL_RATIO", "avg_stride_length", "stride_length_sd_diff"]].isna().all()
    assert values.filter(regex="^[LR][BF]__").isna().all()
    assert values.filter(like="left__").isna().all()
    assert values.filter(regex="^right__.*__sd$").isna().all()
    assert values.filter(regex="^right__.*__mean$").eq(4.0).all()
    assert any("Missing underside markers" in note for note in notes)
    assert any("calibration is unset" in note for note in notes)


def test_bottom_timing_and_distance_use_its_own_camera_settings(r_runtime, tmp_path):
    bottom = synthetic_bottom(tmp_path / "bottom.csv")
    item = replace(reference_inputs(), bottom_csv=bottom)
    sides = {side: tmp_path / f"{side}.csv" for side in ("left", "right")}
    for path in sides.values():
        pd.DataFrame({name: [1.0, 2.0] for name in ALMA_PARAMETER_NAMES}).to_csv(path)
    settings = native_settings(
        frame_rate=60, calibration_method="per_view", pixels_per_cm=None,
        view_calibration={"left": 20, "right": 80, "bottom": {"x_pixels_per_cm": 62.74}},
        view_timing={"bottom": {"frame_rate": 120}},
    )
    paths, _notes = RustLabBottomExecutor().run(item, tmp_path, settings, sides)
    values = pd.read_csv(paths[0]).set_index("Measure").Value
    original = pd.read_csv(FIXTURE / "rust_bottom" / "original_20.csv").set_index("Measure").Value
    for name in ("avg_duration", "duration_sd_diff", "avg_stance_time", "avg_swing_time", "avg_stride_length", "stride_length_sd_diff"):
        assert values[name] == pytest.approx(original[name] / 2)


def test_left_and_right_native_files_use_independent_camera_fps(tmp_path):
    item = replace(reference_inputs(), bottom_csv=tmp_path / "unused.csv")
    settings = native_settings(output_format="alma", view_timing={"left": {"frame_rate": 120}, "right": {"frame_rate": 240}})
    result = run_alma_gait_analysis_in_process([item], tmp_path / "outputs", settings)[0]
    folder = result.output_files[0].parent
    for side, fps in (("left", 120), ("right", 240)):
        raw = pd.read_csv(getattr(item, f"{side}_csv"), header=[1, 2])
        expected = calculate_alma_recording(raw, replace(settings, frame_rate=fps))[0].drop(columns=list(ALMA_REMOVED_VARIABILITY_NAMES))
        assert (folder / f"{side}_stride_parameters.csv").read_text() == expected.to_csv()


def test_combined_mode_requires_both_sides_and_survives_runtime_serialization(tmp_path):
    settings = native_settings()
    assert settings_from_json(settings_to_json(settings)) == settings
    with pytest.raises(ValueError, match="requires matched"):
        run_alma_gait_analysis_in_process([reference_inputs().left_csv], tmp_path, settings)
