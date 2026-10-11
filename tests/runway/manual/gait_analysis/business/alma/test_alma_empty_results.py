"""Regression coverage for recordings with no detectable walking cycles."""

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")


@pytest.fixture
def kinematics():
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_spontaneous_parameters

    return alma_spontaneous_parameters


@pytest.mark.parametrize("with_markers", [False, True])
def test_spontaneous_no_cycles_preserves_result_contract(kinematics, alma_fixtures_dir, with_markers):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import fix_column_names

    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    frame, _, _ = fix_column_names(raw)
    # The real detector cannot locate cycles without confident toe samples.
    frame["toe likelihood"] = 0.0
    if not with_markers:
        frame = pd.DataFrame(index=frame.index)

    parameters, coords, stance, bodyparts, drag_masks, starts = kinematics.extract_spontaneous_parameters(
        120.0,
        frame,
        6.0,
        pixels_per_cm=50.0,
        right_to_left=False,
    )

    expected_columns = pd.read_csv(
        alma_fixtures_dir / "alma_edge_cases_filtered_parameters.csv",
        nrows=0,
    ).columns.tolist()
    assert parameters.empty
    assert parameters.columns.tolist() == expected_columns
    pd.testing.assert_frame_equal(coords, frame)
    assert bodyparts == ["toe", "mtp", "ankle", "knee", "hip", "iliac crest"]
    assert drag_masks is None
    assert starts is None
    # Stance describes movement between consecutive frames.
    assert len(stance) == (len(frame) - 1 if with_markers else 0)


@pytest.mark.parametrize("multiview", [False, True])
def test_no_cycles_exports_empty_parameters_without_crashing(tmp_path, alma_fixtures_dir, multiview):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
        run_alma_gait_analysis_in_process,
    )

    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[0, 1, 2])
    for column in raw.columns:
        if column[-1] in ("x", "y"):
            raw[column] = raw[column].iloc[0]
    input_path = tmp_path / "no_cycles.csv"
    raw.to_csv(input_path, index=False)
    recording = (
        AlmaViewCsvSet(name="no_cycles", left_csv=input_path, right_csv=input_path, bottom_csv=input_path)
        if multiview
        else input_path
    )
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        generate_rustlab1_parameters=False,
        stroke_analysis_enabled=False,
    )
    output = tmp_path / "results"

    results = run_alma_gait_analysis_in_process([recording], output, settings)

    assert len(results) == 1
    assert not (output / "gait_parameters.csv").exists()
    sides = ("left", "right") if multiview else ("side",)
    assert len(list(output.rglob("*.csv"))) == len(sides) + 1
    general = pd.read_csv(next(output.rglob("general_parameters.csv")))
    assert len(general) == 1
    from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
        ALMA_PARAMETER_NAMES,
    )

    assert len(ALMA_PARAMETER_NAMES) == 32
    for side in sides:
        table = pd.read_csv(next(output.rglob(f"{side}_stride_parameters.csv")))
        assert table.empty
        assert set(ALMA_PARAMETER_NAMES).issubset(table)
        assert general[f"{side}_stride_count"].iloc[0] == 0
