"""Verify the saved bundle against the same calculations shown in the GUI."""

from dataclasses import replace
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.app.app_bootstrap import create_gait_preview
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import CONTEXT_MIXTURE_METHOD
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import GaitAnalysisUseCases
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter
from tests.runway.manual.gait_analysis.infrastructure.test_single_gait_csv import recording
from tests.runway.manual.gait_analysis.integration.test_stickplot_comparison import skeleton_geometry


def settings():
    return AlmaSettings(
        analysis_type="Spontaneous walking",
        pixels_per_cm=50.0,
        calibration_method="manual",
        likelihood_threshold=0.0,
        stride_detection_method=CONTEXT_MIXTURE_METHOD,
        no_outlier_filter=True,
        view_calibration={"left": 40.0, "right": 80.0, "bottom": 50.0},
    )


def test_complete_export_is_readable_and_matches_preview(tmp_path, alma_fixtures_dir):
    item = recording(tmp_path, alma_fixtures_dir, "paired recording")
    folder = tmp_path / "user chosen folder"
    results = GaitAnalysisUseCases(GaitResultWriter()).run([item], folder, settings())
    paths = results[0].output_files
    assert len(paths) == 52  # 3 CSVs + report + 2 stick plots + 14 ALMA + 32 RustLab1
    assert set(paths) == {p for p in folder.rglob("*") if p.is_file()}
    assert len(list(folder.rglob("*.csv"))) == 3
    assert not (folder / "gait_parameters.csv").exists()
    assert len(list(folder.rglob("*_ALMA_*.svg"))) == 14
    assert len(list(folder.rglob("rustlab1_figures/*_strides/*.svg"))) == 32
    for path in paths:
        assert path.stat().st_size > 0
        if path.suffix == ".svg":
            assert ET.parse(path).getroot().tag.endswith("svg")
    for name in ("6_2_sync_plots.svg", "9_1_PLOT_DURATION_of_STEPE.svg"):
        assert "No compatible data" not in next(folder.rglob(name)).read_text()
    tables = {side: pd.read_csv(next(folder.rglob(f"{side}_stride_parameters.csv"))) for side in ("left", "right")}
    assert len(tables["left"]) >= 1
    np.testing.assert_allclose(tables["left"]["stride length (cm)"], 2 * tables["right"]["stride length (cm)"])
    for table in tables.values():
        np.testing.assert_allclose(table["stance percentage (%)"] + table["swing percentage (%)"], 100.0)
    inputs = [(side.title(), getattr(item, f"{side}_csv")) for side in ("left", "right", "bottom")]
    for label, svg in create_gait_preview().prepare(inputs, settings())[0]:
        side = label.split(" · ")[0].lower()
        exported = next(folder.rglob(f"{side}_stickplot.svg")).read_bytes()
        assert skeleton_geometry(exported) == skeleton_geometry(svg)
        assert re.findall(rb'id="phase-[^"]+"', exported) == re.findall(rb'id="phase-[^"]+"', svg)
        assert re.findall(rb'id="stride-start-[^"]+"', exported) == re.findall(rb'id="stride-start-[^"]+"', svg)
        assert CONTEXT_MIXTURE_METHOD.encode() in exported
        for group in ET.fromstring(exported).iter("{http://www.w3.org/2000/svg}g"):
            if group.get("id", "").startswith("stick-frame-"):
                assert not list(group.iter("{http://www.w3.org/2000/svg}use"))  # no point markers
    assert "40.0 pixels/cm" in (folder / "export_report.txt").read_text()
    assert "80.0 pixels/cm" in (folder / "export_report.txt").read_text()


def test_export_does_not_report_success_when_renderer_writes_nothing(tmp_path, alma_fixtures_dir):
    class BrokenRenderer(GaitResultWriter):
        def render_stickplot(self, prepared, destination):
            pass

    item = recording(tmp_path, alma_fixtures_dir, "missing plot")
    cfg = replace(settings(), generate_alma_representations=False, generate_rustlab1_parameters=False)
    with pytest.raises(RuntimeError, match="nonempty file.*left_stickplot"):
        GaitAnalysisUseCases(BrokenRenderer()).run([item], tmp_path / "out", cfg)


def test_invalid_destination_fails_before_analysis(tmp_path, alma_fixtures_dir):
    destination = tmp_path / "not_a_folder"
    destination.write_text("Existing file must remain intact")
    with pytest.raises(FileExistsError):
        GaitAnalysisUseCases(GaitResultWriter()).run([Path("not-read.csv")], destination, settings())
    assert destination.read_text() == "Existing file must remain intact"


def test_no_detected_cycles_still_exports_tracking_and_complete_csv_headers(tmp_path, alma_fixtures_dir):
    item = recording(tmp_path, alma_fixtures_dir, "stationary")
    raw = pd.read_csv(item.left_csv, header=[0, 1, 2])
    for column in raw:
        if column[-1] in ("x", "y"):
            raw[column] = raw[column].iloc[0]
    path = tmp_path / "stationary_side.csv"
    raw.to_csv(path, index=False)
    item = replace(item, left_csv=path, right_csv=path)
    folder = tmp_path / "empty_cycles"
    result = GaitAnalysisUseCases(GaitResultWriter()).run([item], folder, settings())[0]
    for side in ("left", "right"):
        table = pd.read_csv(next(folder.rglob(f"{side}_stride_parameters.csv")))
        assert table.empty and "knee joint SD (deg)" in table
    assert len(pd.read_csv(next(folder.rglob("general_parameters.csv")))) == 1
    assert len(result.output_files) == 52
    for side in ("left", "right"):
        svg = next(folder.rglob(f"{side}_stickplot.svg")).read_text()
        assert "stick-frame-" in svg and "0 strides" in svg
        assert 'id="stride-start-' not in svg
    assert "Left: 0 stride rows" in (folder / "export_report.txt").read_text()
