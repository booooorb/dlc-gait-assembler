from __future__ import annotations

import csv
from dataclasses import replace
from pathlib import Path

import pytest

from dlc_gait_assembly.services.pipeline.ladder import (
    COMBINED_LADDER_OUTPUT_COLUMNS,
    LADDER_OUTPUT_COLUMNS,
    LadderEvent,
    LadderSettings,
    ladder_settings_from_alma_config,
    read_dlc_bodyparts,
    run_dual_view_ladder_analysis,
    run_ladder_analysis,
    suggested_ladder_bodyparts,
    write_ladder_events,
)


def test_ladder_settings_use_alma_config_keys():
    settings = ladder_settings_from_alma_config(
        {
            "frame_rate": 240,
            "likelihood_threshold": 0.6,
            "depth_threshold": 0.75,
            "threshold": "321.5",
        }
    )

    assert settings == LadderSettings(
        frame_rate=240.0,
        likelihood_threshold=0.6,
        depth_threshold=0.75,
        threshold=321.5,
    )


def test_dlc_header_reader_preserves_full_ladder_marker_names(alma_fixtures_dir):
    bodyparts = read_dlc_bodyparts(
        alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv"
    )

    assert bodyparts == ["toe", "mtp", "ankle", "knee", "hip", "iliac crest"]
    assert suggested_ladder_bodyparts(bodyparts) == ["toe"]


def test_deviation_detector_matches_alma_reference_results(tmp_path, alma_fixtures_dir, monkeypatch):
    pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    pytest.importorskip("scipy")
    monkeypatch.setenv("DLC_GAIT_ALMA_PIPELINE_CHILD", "1")
    input_file = alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv"

    result = run_ladder_analysis(
        input_file,
        tmp_path,
        LadderSettings(method="Deviation", frame_rate=120.0),
        ["toe"],
    )

    assert [event.peak_frame for event in result.events] == [551, 830, 1136, 1152, 1407, 1935, 1980]
    assert [event.start_frame for event in result.events] == [356, 643, 1135, 1151, 1406, 1934, 1979]
    assert [event.end_frame for event in result.events] == [641, 845, 1137, 1161, 1408, 1936, 1981]
    assert result.events[0].depth_px == pytest.approx(46.76214599609375)
    assert result.events[0].duration_s == 2.375
    assert result.output_file == tmp_path / f"{input_file.stem}_ladder_footfalls.csv"

    with result.output_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == LADDER_OUTPUT_COLUMNS
    assert rows[0]["time (frame)"] == "551"
    assert rows[0]["bodypart"] == "toe"


def test_detector_returns_empty_output_instead_of_alma_no_peak_crash(
    tmp_path, alma_fixtures_dir, monkeypatch
):
    pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    pytest.importorskip("scipy")
    monkeypatch.setenv("DLC_GAIT_ALMA_PIPELINE_CHILD", "1")

    result = run_ladder_analysis(
        alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv",
        tmp_path,
        LadderSettings(method="Threshold", threshold=1_000_000.0),
        ["toe"],
    )

    assert result.events == ()
    assert result.output_file.read_text(encoding="utf-8").strip() == ",".join(LADDER_OUTPUT_COLUMNS)


def test_reviewed_export_filters_rejections_and_writes_slip_classification(tmp_path):
    event = LadderEvent(
        bodypart="left-paw",
        peak_frame=15,
        start_frame=10,
        end_frame=20,
        peak_y_px=80.0,
        depth_px=25.0,
        duration_s=0.1,
        classification="slip",
    )
    rejected = replace(event, peak_frame=40, included=False, classification="fall")

    output = write_ladder_events([event, rejected], tmp_path / "reviewed.csv")

    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["slip or fall"] == "slip"
    assert rows[0]["duration (s)"] == "0.1"


def test_dual_view_analysis_uses_independent_settings_and_combines_sources(
    tmp_path, alma_fixtures_dir, monkeypatch
):
    pytest.importorskip("numpy")
    pytest.importorskip("pandas")
    pytest.importorskip("scipy")
    monkeypatch.setenv("DLC_GAIT_ALMA_PIPELINE_CHILD", "1")
    input_file = alma_fixtures_dir / "Demo_Mouse_Treadmill_30cm_s_650000_filtered.csv"

    result = run_dual_view_ladder_analysis(
        input_file,
        input_file,
        tmp_path,
        LadderSettings(method="Deviation"),
        LadderSettings(method="Threshold", threshold=1_000_000.0),
        ["toe", "mtp"],
        ["toe", "mtp"],
    )

    assert result.left_result.events
    assert result.right_result.events == ()
    assert result.left_result.output_file.parent == tmp_path / "left"
    assert result.right_result.output_file.parent == tmp_path / "right"
    assert result.events
    assert {event.view for event in result.events} == {"left"}
    assert {event.source_file for event in result.events} == {input_file.name}
    with result.output_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert tuple(rows[0]) == COMBINED_LADDER_OUTPUT_COLUMNS
    assert {row["view"] for row in rows} == {"left"}
    assert {row["source file"] for row in rows} == {input_file.name}


def test_dual_view_analysis_requires_two_markers_for_each_camera(tmp_path):
    with pytest.raises(ValueError, match="exactly two body parts per side"):
        run_dual_view_ladder_analysis(
            tmp_path / "left.csv",
            tmp_path / "right.csv",
            tmp_path,
            LadderSettings(),
            LadderSettings(),
            ["front-paw"],
            ["front-paw", "hind-paw"],
        )


def test_empty_combined_export_keeps_view_metadata_columns(tmp_path):
    output = write_ladder_events([], tmp_path / "combined.csv", combined=True)

    assert output.read_text(encoding="utf-8").strip() == ",".join(
        COMBINED_LADDER_OUTPUT_COLUMNS
    )
