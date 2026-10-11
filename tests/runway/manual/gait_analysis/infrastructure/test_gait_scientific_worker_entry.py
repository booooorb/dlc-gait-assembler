"""The scientific child executes the same installed package and preserves gait table schemas."""

import sys
from pathlib import Path

import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
    run_alma_gait_analysis_external,
    run_alma_gait_analysis_in_process,
)


def test_external_gait_worker_matches_in_process_tables(tmp_path, alma_fixtures_dir, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = alma_fixtures_dir / "alma_edge_cases_filtered.csv"
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        generate_rustlab1_parameters=False,
        stroke_analysis_enabled=False,
        generate_alma_representations=False,
        generate_stickplot=False,
    )
    expected = run_alma_gait_analysis_in_process([source], tmp_path / "in_process", settings)
    actual = run_alma_gait_analysis_external([source], tmp_path / "external", settings, Path(sys.executable))
    expected_tables = {
        path.relative_to(tmp_path / "in_process"): pd.read_csv(path)
        for path in expected[0].output_files
        if path.suffix == ".csv"
    }
    actual_tables = {
        path.relative_to(tmp_path / "external"): pd.read_csv(path)
        for path in actual[0].output_files
        if path.suffix == ".csv"
    }
    assert expected_tables.keys() == actual_tables.keys()
    for name in expected_tables:
        pd.testing.assert_frame_equal(
            actual_tables[name], expected_tables[name], check_exact=False, rtol=1e-8, atol=1e-8
        )
