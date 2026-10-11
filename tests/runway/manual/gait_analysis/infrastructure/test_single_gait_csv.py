import numpy as np
import pandas as pd
import pytest

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
)


def recording(tmp_path, alma_fixtures_dir, name):
    side = alma_fixtures_dir / "alma_edge_cases_filtered.csv"
    frames = len(pd.read_csv(side, header=[0, 1, 2]))
    columns = pd.MultiIndex.from_product([["DLC"], ["lhpaw", "rhpaw", "lfpaw", "rfpaw"], ["x", "y", "likelihood"]])
    bottom = pd.DataFrame(index=range(frames), columns=columns, dtype=float)
    for index, paw in enumerate(("lhpaw", "rhpaw", "lfpaw", "rfpaw")):
        bottom["DLC", paw, "x"] = np.arange(frames) / 100.0
        bottom["DLC", paw, "y"] = index * 10.0
        bottom["DLC", paw, "likelihood"] = 1.0
    bottom_path = tmp_path / f"{name}_bottom.csv"
    bottom.to_csv(bottom_path, index=False)
    return AlmaViewCsvSet(name, side, side, bottom_path, StrokeStudyMetadata(animal_id=name))


@pytest.mark.parametrize("scope,count", [("Hindlimb", 53), ("Hindlimb + Forelimb", 75)])
def test_separate_csvs_contain_every_applicable_parameter_per_recording(tmp_path, alma_fixtures_dir, scope, count):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_bottom_windows import (
        BOTTOM_FORE_NAMES,
        BOTTOM_STRIDE_NAMES,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_recording_tables import side_feature_names

    inputs = [recording(tmp_path, alma_fixtures_dir, name) for name in ("mouse_01", "mouse_02")]
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        limb_scope=scope,
        pixels_per_cm=50.0,
        calibration_method="manual",
        likelihood_threshold=0.0,
        enabled_parameter_names=("left__stride length (cm)",),
        generate_rustlab1_parameters=False,
        generate_stickplot=True,
        generate_alma_representations=True,
    )
    folder = tmp_path / "outputs"
    results = run_alma_gait_analysis_in_process(inputs, folder, settings)
    assert not (folder / "gait_parameters.csv").exists()
    assert len(list(folder.rglob("*.csv"))) == 6
    assert len(list(folder.rglob("*_stickplot.svg"))) == 4
    assert len(list(folder.rglob("*_ALMA_*.svg"))) == 28
    assert {p for r in results for p in r.output_files} == {p for p in folder.rglob("*") if p.is_file()}
    for result, item in zip(results, inputs, strict=True):
        for side in ("left", "right"):
            path = next(p for p in result.output_files if p.name == f"{side}_stride_parameters.csv")
            table = pd.read_csv(path)
            assert len(table) == 4 and set(table["recording"]) == {item.name}
            assert set(table["animal_id"]) == {item.name}
            rust, custom = side_feature_names(side, scope)
            expected = {*ALMA_PARAMETER_NAMES, *rust, *custom, *BOTTOM_STRIDE_NAMES}
            if scope != "Hindlimb":
                expected.update(BOTTOM_FORE_NAMES)
            assert len(expected) == count
            assert expected.issubset(table)
            opposite_rust, opposite_custom = side_feature_names("right" if side == "left" else "left", scope)
            assert not set((*opposite_rust, *opposite_custom)).intersection(table)
            assert table.columns.is_unique
            assert not any("Variability " in name for name in table)
            assert table["variance_hindlimb_base_support"].notna().any()
            assert table["knee joint SD (deg)"].notna().any()
        general = pd.read_csv(next(p for p in result.output_files if p.name == "general_parameters.csv"))
        assert len(general) == 1 and set(general["recording"]) == {item.name}
        assert "hindlimb_same_phase (%)" in general


def test_removed_alma_variability_count():
    assert len(ALMA_REMOVED_VARIABILITY_NAMES) == 12
    assert len(ALMA_PARAMETER_NAMES) == 32
    assert all(not name.startswith("Variability ") for name in ALMA_PARAMETER_NAMES)
    assert sum(" SD" in name for name in ALMA_PARAMETER_NAMES) == 5


def test_right_view_uses_frame_overlap_not_row_number(tmp_path, alma_fixtures_dir):
    from dlc_gait_assembly.runway.manual.gait_analysis.business import gait_analysis_use_cases as module
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter

    item = recording(tmp_path, alma_fixtures_dir, "mouse")
    frames = pd.DataFrame(
        {"stride_start (frame)": [0, 20], "stride_end (frame)": [9, 29], "step height (cm)": [1.0, 3.0]}
    )
    right = pd.DataFrame(
        {"stride_start (frame)": [20, 0], "stride_end (frame)": [29, 9], "step height (cm)": [30.0, 10.0]}
    )
    calls = iter([frames, right])

    def calculate(*args):
        return next(calls), None, None, None, None, None, ()

    table, messages = module.calculate_recording_table(
        item,
        AlmaSettings(pixels_per_cm=50.0),
        GaitResultWriter(),
        pd,
        calculate=calculate,
    )
    assert table["right__step height (cm)"].tolist() == [10.0, 30.0]


def test_stationary_rows_keep_measurements_without_inventing_cycle_match():
    from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_cycle_alignment import (
        align_parameters_to_cycles,
    )

    cycles = pd.DataFrame({"stride_start (frame)": [np.nan, 0], "stride_end (frame)": [np.nan, 9]})
    other = pd.DataFrame({"stride_start (frame)": [0], "stride_end (frame)": [9], "knee joint SD (deg)": [2.5]})
    table = align_parameters_to_cycles(cycles, other, "right", pd, np)
    assert table["right__cycle_match_valid"].tolist() == [False, True]
    assert pd.isna(table.loc[0, "right__knee joint SD (deg)"])
    assert table.loc[1, "right__knee joint SD (deg)"] == 2.5


def test_automatic_review_previews_are_separate_from_parameter_export(tmp_path, alma_fixtures_dir):
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_preview_writer import (
        write_gait_stickplot_previews,
    )

    item = recording(tmp_path, alma_fixtures_dir, "review")
    settings = AlmaSettings(
        analysis_type="Spontaneous walking", pixels_per_cm=50.0, likelihood_threshold=0.0, n_continuous_strides=1
    )
    folder = tmp_path / "review_previews"
    results = write_gait_stickplot_previews([item], folder, settings)
    assert len(results) == 1
    assert len(results[0].output_files) == 2
    assert all(path.suffix == ".svg" and "<svg" in path.read_text() for path in results[0].output_files)
    assert not list(folder.glob("*.csv"))
