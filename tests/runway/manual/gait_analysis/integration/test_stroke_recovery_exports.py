"""The main manual/automatic export operation must include the new research extraction types."""

from dataclasses import replace

import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import GaitAnalysisUseCases
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.stroke_recovery_parameter_definitions import (
    STROKE_STRIDE_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter
from tests.runway.manual.gait_analysis.infrastructure.test_single_gait_csv import recording


def test_real_recording_exports_calibrated_asymmetry_with_provenance_and_counts(tmp_path, alma_fixtures_dir):
    item = recording(tmp_path, alma_fixtures_dir, "stroke_mouse")
    item = replace(item, metadata=replace(item.metadata, lesion_hemisphere="right", timepoint="3 dpi"))
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        calibration_method="per_view",
        view_calibration={"left": 40.0, "right": 80.0, "bottom": 50.0},
        likelihood_threshold=0,
        no_outlier_filter=True,
        minimum_synchronized_cycles=1,
        generate_stickplot=False,
        generate_alma_representations=False,
        generate_rustlab1_parameters=False,
    )
    result = GaitAnalysisUseCases(GaitResultWriter()).run([item], tmp_path / "export", settings)[0]
    frames = {path.name: pd.read_csv(path) for path in result.output_files if path.suffix == ".csv"}
    left, right = (frames[f"{side}_stride_parameters.csv"] for side in ("left", "right"))
    assert set(STROKE_STRIDE_NAMES).issubset(left)
    assert len(left) == len(right) == 4
    pd.testing.assert_series_equal(left["stride_start (frame)"], right["stride_start (frame)"])
    general = frames["general_parameters.csv"].iloc[0]
    assert general["stride_length_symmetry_index (%)"] == pytest.approx(200 / 3)
    assert general["stride_length_lesion_asymmetry (%)"] == pytest.approx(200 / 3)
    assert general["step_height_symmetry_index (%)"] == pytest.approx(200 / 3)
    assert general["left__stride_length_valid_strides"] == 4
    assert general["contralesional_side"] == "left"
    assert general["timepoint"] == "3 dpi"
    dictionary = frames["parameter_dictionary.csv"]
    assert {"Swing-phase kinematics", "Bilateral asymmetry", "Stride variability"}.issubset(
        dictionary["extraction_type"]
    )
    row = dictionary.loc[dictionary["column"] == "stride_length_lesion_asymmetry (%)"].iloc[0]
    assert row["output_level"] == "recording" and row["unit"] == "%"
    assert "contralesional - ipsilesional" in row["formula"]
    assert "doi.org" in row["reference"]
    assert not dictionary.duplicated(["table", "column"]).any()
