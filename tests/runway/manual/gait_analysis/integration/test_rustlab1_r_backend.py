"""Verify actual R execution against the user-supplied GX10564 reference outputs."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from dlc_gait_assembly.app.app_bootstrap import create_gait_preview, create_rustlab1_use_cases
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.rustlab1_r_executor import RustLab1RExecutor
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_coordinate_repository import (
    merge_multiview_rustlab1_dataframe,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_r_analysis import detect_r_gmm_phases
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommandResult

FIXTURE = Path(__file__).parents[4] / "fixtures" / "gait" / "rustlab1_r_reference"


@pytest.fixture(scope="module")
def reference_inputs():
    return AlmaViewCsvSet(
        "GX010564_M3_DPI7_seg5",
        FIXTURE / "left.csv",
        FIXTURE / "right.csv",
        FIXTURE / "bottom.csv",
        StrokeStudyMetadata(animal_id="M3", timepoint="7days", session_id="GX010564_M3_DPI7_seg5"),
    )


@pytest.fixture(scope="module")
def reference_settings():
    return RustLab1StandaloneSettings(
        frame_rate=239.76,
        filter_cutoff=6,
        likelihood_threshold=0.5,
        pixels_per_cm=31.3667,
        limb_scope="Hindlimb",
    )


@pytest.fixture(scope="module")
def r_runtime():
    executable = shutil.which("Rscript")
    if executable is None:
        pytest.skip("Rscript is not installed")
    check = subprocess.run(
        [executable, "-e", "library(dplyr);library(tidyr);library(jsonlite)"],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode:
        pytest.skip("R regression test needs dplyr, tidyr and jsonlite")
    return executable


@pytest.fixture(scope="module")
def actual_run(r_runtime, reference_inputs, reference_settings, tmp_path_factory):
    output = tmp_path_factory.mktemp("adapted_r_reference") / "output with spaces"
    result = create_rustlab1_use_cases().run([reference_inputs], output, reference_settings)[0]
    return result, result.output_files[0].parent


@pytest.mark.parametrize("filename", ("all_raw_data.csv", "all_summarized_data.csv", "Stride_detection.csv"))
def test_actual_r_tables_reproduce_reference(filename, actual_run):
    _result, folder = actual_run
    expected = pd.read_csv(FIXTURE / filename)
    actual = pd.read_csv(folder / filename)
    pd.testing.assert_frame_equal(actual, expected, check_exact=False, atol=1e-8, rtol=1e-9)
    assert actual.isna().equals(expected.isna())


def test_gmm_timing_is_recomputed_from_input_coordinates(reference_inputs, reference_settings):
    merged = merge_multiview_rustlab1_dataframe(reference_inputs, pd)
    phases = detect_r_gmm_phases(merged, reference_settings)
    pd.testing.assert_frame_equal(phases, pd.read_csv(FIXTURE / "Stride_detection.csv"))


def test_r_run_retains_full_catalog_and_distinct_side_cycles(actual_run):
    result, folder = actual_run
    raw = pd.read_csv(folder / "all_raw_data.csv")
    assert len(raw) == 106
    assert raw.Value.notna().sum() == 46
    assert raw.Value.isna().sum() == 60
    forelimb = raw.Measure.str.contains(r"front|wrist|elbow|ellbow|shoulder|^LF__|^RF__|^FLBR_RATIO$|^FRBL_RATIO$")
    assert forelimb.sum() == 46 and raw.loc[forelimb, "Value"].isna().all()
    canonical = pd.read_csv(folder / "diagnostics" / "canonical.csv")
    assert canonical.groupby("side").size().to_dict() == {"left": 5, "right": 5}
    assert canonical[canonical.side.eq("left")].start_frame.tolist() == [325, 410, 493, 580, 716]
    assert canonical[canonical.side.eq("right")].start_frame.tolist() == [233, 364, 458, 534, 626]
    assert all(path.is_file() for path in result.output_files)
    manifest = json.loads((folder / "analysis_manifest.json").read_text())
    assert manifest["backend"] == "adapted RustLab1 R"
    assert len(manifest["script_sha256"]) == 64
    assert "46 numeric catalog values" in (folder / "R_analysis.log").read_text()


def test_preview_and_export_use_r_coordinates_and_identical_gmm_boundaries(
    actual_run,
    reference_inputs,
    reference_settings,
):
    _result, folder = actual_run
    preview, _source, _messages = create_gait_preview().prepare_rustlab1(reference_inputs, reference_settings)
    for side, (_label, svg) in zip(("left", "right"), preview, strict=True):
        exported = (folder / f"Stickplot_{side}.svg").read_text()
        for pattern in (r'id="stride-start-\d+"', r'id="phase-\d+-\d+-\w+"', r'id="stick-frame-\d+-\w+-segment-\d+"'):
            assert re.findall(pattern, svg.decode()) == re.findall(pattern, exported)
        assert re.findall(r'<path d="([^"]+)"', svg.decode()) == re.findall(r'<path d="([^"]+)"', exported)
        assert "1135 frames" in svg.decode() and "5 strides" in svg.decode()
        with Image.open(folder / f"Stickplot_{side}.png") as image:
            assert image.size == (2520, 1080)


def test_r_accepts_other_frame_counts_fps_and_metadata(
    r_runtime,
    reference_inputs,
    reference_settings,
    tmp_path,
):
    paths = []
    for side in ("left", "right", "bottom"):
        source = pd.read_csv(getattr(reference_inputs, side + "_csv"), header=[0, 1, 2], index_col=0)
        path = tmp_path / (side + " shorter input.csv")
        source.iloc[:800].to_csv(path)
        paths.append(path)
    inputs = AlmaViewCsvSet("second_trial", *paths, StrokeStudyMetadata(animal_id="M9", timepoint="14days"))
    config = replace(reference_settings, frame_rate=120.0, generate_figures=False)
    result = create_rustlab1_use_cases().run([inputs], tmp_path / "results", config)[0]
    folder = result.output_files[0].parent
    phases = pd.read_csv(folder / "Stride_detection.csv")
    assert phases.groupby("parameter").size().tolist() == [800, 800]
    canonical = pd.read_csv(folder / "diagnostics" / "canonical.csv")
    np.testing.assert_allclose(
        canonical.cycle_duration_seconds,
        (canonical.next_touchdown_frame - canonical.start_frame) / 120,
    )
    raw = pd.read_csv(folder / "all_raw_data.csv")
    assert raw.full_id.eq("second_trial").all() and raw.mouse.eq("M9").all() and raw.day.eq("14days").all()


def test_missing_r_is_an_explicit_error(monkeypatch, reference_inputs, reference_settings):
    monkeypatch.setattr(shutil, "which", lambda _value: None)
    with pytest.raises(RuntimeError, match="requires Rscript"):
        RustLab1RExecutor().preview(reference_inputs, reference_settings)


def test_r_failure_never_substitutes_python_measurements(reference_inputs, reference_settings, tmp_path):
    class FailedSession:
        def run(self, command):
            assert command.arguments[-1] == "--no-stickplots"
            return ExternalCommandResult(1, "there is no package called 'dplyr'")

    executor = RustLab1RExecutor(rscript=shutil.which("python"), session_factory=FailedSession)
    with pytest.raises(RuntimeError, match="no package called 'dplyr'"):
        executor.run_recording(reference_inputs, tmp_path, reference_settings)
    assert not list(tmp_path.rglob("all_raw_data.csv"))
