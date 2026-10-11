"""Brief confidence dips must not silently turn a walk into a one-row export."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import (
    AlmaSettings,
    settings_from_alma_config,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    cycles_from_stance,
    detect_strides,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import CONTEXT_MIXTURE_METHOD
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.tracking_gap_policy import tracking_gap_frames
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_stride_export import (
    validate_stride_rows,
    with_stride_details,
)
from tests.runway.manual.gait_analysis.integration.test_stride_comparison import variable_speed_walk


@pytest.mark.parametrize("method", ("Speed mixture (GMM)", CONTEXT_MIXTURE_METHOD, "Adaptive paw speed"))
def test_short_dropouts_preserve_cycles_but_explicit_zero_is_strict(method):
    x, y, bounds = variable_speed_walk()
    confidence = np.ones(len(x))
    expected = detect_strides(x, y, confidence, 120.0, method=method)
    for start in bounds[:-1]:
        confidence[start + 10 : start + 12] = 0.1
    strict = detect_strides(x, y, confidence, 120.0, method=method, maximum_gap=0)
    diagnostics = {}
    recovered = detect_strides(x, y, confidence, 120.0, method=method, diagnostics=diagnostics)
    assert len(expected[1]) >= 5
    assert len(strict[1]) < len(expected[1])
    assert recovered[1:3] == expected[1:3]
    assert diagnostics["maximum_gap_frames"] == 6
    assert not diagnostics["observed"][10]
    assert diagnostics["trusted"][10]
    confidence[80:105] = 0.1
    _, starts, ends, _ = detect_strides(x, y, confidence, 120.0, method=method)
    assert all(not (start <= 104 and end >= 80) for start, end in zip(starts, ends, strict=True))


def test_tracking_resumption_is_not_a_touchdown():
    # Real contacts at 0, 10 and 20; tracking resumes mid-stance at frame 3.
    stance = np.tile(np.r_[np.ones(5, bool), np.zeros(5, bool)], 3)
    trusted = np.ones(30, bool)
    trusted[:3] = False
    assert cycles_from_stance(stance & trusted, trusted, 3) == ([10], [19])


@pytest.mark.parametrize("fps,frames", ((30.0, 1), (120.0, 6), (239.8, 11), (300.0, 15)))
def test_default_gap_is_time_limited_and_explicit_settings_are_preserved(fps, frames):
    assert tracking_gap_frames(AlmaSettings().max_interpolation_gap_frames, fps) == frames
    assert settings_from_alma_config({}).max_interpolation_gap_frames == -1
    assert settings_from_alma_config({"max_interpolation_gap_frames": 0}).max_interpolation_gap_frames == 0
    assert settings_from_alma_config({"max_interpolation_gap_frames": 3}).max_interpolation_gap_frames == 3
    assert tracking_gap_frames(0, fps) == 0
    assert tracking_gap_frames(3, fps) == 3


def test_stride_metadata_includes_rejected_and_gap_affected_cycles():
    parameters = pd.DataFrame(
        {"stride_start (frame)": [0, 10], "stride_end (frame)": [9, 19], "cycle duration (s)": [0.1, np.nan]}
    )
    coords = pd.DataFrame(index=range(20))
    observed = np.ones(20, bool)
    observed[4:6] = False
    coords.attrs["detection_diagnostics"] = {"observed": observed.tolist()}
    table = with_stride_details((parameters, coords))[0]
    assert table["stride_number"].tolist() == [1, 2]
    assert table["timing_observed (%)"].tolist() == [80.0, 100.0]
    assert table["timing_gap_frames"].tolist() == [2, 0]
    assert table["passed_stride_filters"].tolist() == [True, False]
    validate_stride_rows(table, {"side": parameters})
    with pytest.raises(RuntimeError, match="losing or duplicating"):
        validate_stride_rows(table.iloc[:1], {"side": parameters})
    with pytest.raises(RuntimeError, match="losing or duplicating"):
        validate_stride_rows(pd.concat([table, table.iloc[:1]]), {"side": parameters})


def test_selected_detector_exports_all_stride_ids_and_matching_stickplot_boundaries(tmp_path, alma_fixtures_dir):
    from dlc_gait_assembly.app.app_bootstrap import create_gait_preview
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import GaitAnalysisUseCases
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter
    from tests.runway.manual.gait_analysis.infrastructure.test_single_gait_csv import recording
    import re

    item = recording(tmp_path, alma_fixtures_dir, "all strides")
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        likelihood_threshold=0.0,
        calibration_method="manual",
        pixels_per_cm=50.0,
        generate_alma_representations=False,
        generate_rustlab1_parameters=False,
    )
    folder = tmp_path / "chosen folder"
    GaitAnalysisUseCases(GaitResultWriter()).run([item], folder, settings)
    table = pd.read_csv(next(folder.rglob("left_stride_parameters.csv")))
    assert len(table) == 4
    for side in ("left", "right"):
        table = pd.read_csv(next(folder.rglob(f"{side}_stride_parameters.csv")))
        assert table["stride_number"].tolist() == [1, 2, 3, 4]
        svg = next(folder.rglob(f"{side}_stickplot.svg")).read_text()
        starts = [int(float(x)) for x in table["stride_start (frame)"]]
        assert [int(x) for x in re.findall(r'id="stride-start-(\d+)"', svg)] == starts
    # Strict, fully rejected ALMA filters retain every stride and clearly label it.
    strict = replace(settings, stride_length_min_cm=1000.0)
    GaitAnalysisUseCases(GaitResultWriter()).run([item], tmp_path / "filtered", strict)
    rejected = pd.read_csv(next((tmp_path / "filtered").rglob("left_stride_parameters.csv")))
    assert len(rejected) == 4 and not rejected["passed_stride_filters"].any()
    assert rejected["cycle duration (s)"].isna().all()
    inputs = [(side.title(), getattr(item, f"{side}_csv")) for side in ("left", "right", "bottom")]
    previews = create_gait_preview().prepare(inputs, settings)[0]
    for label, svg in previews:
        side = label.split(" · ")[0].lower()
        exported = next(folder.rglob(f"{side}_stickplot.svg")).read_bytes()
        assert re.findall(rb'id="stride-start-[^"]+"', svg) == re.findall(rb'id="stride-start-[^"]+"', exported)
