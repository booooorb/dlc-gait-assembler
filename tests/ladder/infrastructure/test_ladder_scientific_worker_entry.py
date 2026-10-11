"""The installed Ladder worker executes serialized requests and preserves detected events."""

import sys
from pathlib import Path

import pandas as pd

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderSettings
from dlc_gait_assembly.ladder.infrastructure.ladder_runtime_executor import run_external, run_in_process


def test_external_ladder_worker_matches_in_process_results(tmp_path, alma_fixtures_dir, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv"
    settings = LadderSettings(method="Deviation")
    expected = run_in_process(source, tmp_path / "in_process", settings, ["toe"])
    actual = run_external(source, tmp_path / "external", settings, ["toe"], Path(sys.executable))
    assert actual.events == expected.events
    pd.testing.assert_frame_equal(pd.read_csv(actual.output_file), pd.read_csv(expected.output_file))
