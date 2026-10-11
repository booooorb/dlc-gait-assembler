"""Video-time alignment, independent side windows, and global synchronization."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import RecordingFigures
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_bottom_windows import BottomWindows
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_recording_tables import calculate_recording_tables
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_timing import (
    raw_on_timeline,
    read_view_track,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter


def coordinates(markers, count, fps=10.0):
    columns = pd.MultiIndex.from_product([markers, ("x", "y", "likelihood")])
    frame = pd.DataFrame(0.0, index=range(count), columns=columns)
    for i, marker in enumerate(markers):
        frame[marker, "x"] = np.arange(count) / fps
        frame[marker, "y"] = 20 + i * 5.0
        frame[marker, "likelihood"] = 1.0
    frame["bodyparts", "coords"] = np.arange(count)
    return frame


def test_source_frames_and_clip_times_are_used_instead_of_row_numbers():
    raw = coordinates(("toe",), 3)
    raw["bodyparts", "coords"] = [10, 11, 12]
    raw["toe", "x"] = [5.0, 6.0, 7.0]
    cfg = AlmaSettings(frame_rate=10.0, view_timing={"bottom": {"frame_rate": 20.0, "offset_s": 0.25}})
    track = read_view_track(raw, Path("clip-00.00.01.000-00.00.03.000.csv"), "bottom", cfg)
    np.testing.assert_allclose(track.times, [1.75, 1.80, 1.85])
    sampled = raw_on_timeline(track, [1.70, 1.775, 1.825, 1.90])
    np.testing.assert_allclose(sampled["toe", "x"], [np.nan, 5.5, 6.5, np.nan], equal_nan=True)


def test_explicit_csv_timestamps_override_filename_and_infer_native_fps():
    raw = coordinates(("toe",), 3)
    raw["time_s", "value"] = [10.0, 10.02, 10.04]
    track = read_view_track(raw, Path("clip-00.00.01.000-00.00.03.000.csv"), "left", AlmaSettings(frame_rate=120.0))
    assert track.frame_rate == pytest.approx(50.0)
    np.testing.assert_allclose(track.times, [10.0, 10.02, 10.04])
    assert track.source == "CSV video timestamps"


def test_millisecond_timestamps_work_with_read_only_pandas_arrays():
    raw = coordinates(("toe",), 3)
    raw["timestamp_ms", "value"] = [1000.0, 1020.0, 1040.0]
    track = read_view_track(raw, Path("left.csv"), "left", AlmaSettings())
    np.testing.assert_allclose(track.times, [1.0, 1.02, 1.04])


def test_missing_csv_rows_do_not_compress_video_time_or_get_extrapolated():
    raw = coordinates(("toe",), 3)
    raw["bodyparts", "coords"] = [0, 1, 3]
    track = read_view_track(raw, Path("bottom.csv"), "bottom", AlmaSettings(frame_rate=10.0))
    assert len(track.frame) == 4 and not track.present[2]
    sampled = raw_on_timeline(track, [0.0, 0.15, 0.2, 0.3, 0.4])
    assert sampled["toe", "x"].notna().tolist() == [True, False, False, True, False]


def test_duplicate_frame_ids_are_rejected():
    raw = coordinates(("toe",), 3)
    raw["bodyparts", "coords"] = [0, 1, 1]
    with pytest.raises(ValueError, match="unique, increasing"):
        read_view_track(raw, Path("left.csv"), "left", AlmaSettings())


def test_each_side_extracts_bottom_on_its_own_timestamp_windows(monkeypatch):
    from dlc_gait_assembly.runway.manual.gait_analysis.business import gait_recording_tables as module

    monkeypatch.setattr(module.alma_signal_filter, "butterworth_filter", lambda values, *_: np.asarray(values, float))
    side_raw = coordinates(("toe", "mtp", "ankle", "knee", "hip", "iliac crest"), 80)
    bottom_raw = coordinates(("lhpaw", "rhpaw", "lfpaw", "rfpaw"), 140, 20.0)
    bottom_raw["lhpaw", "y"] = 0.0
    bottom_raw["rhpaw", "y"] = 1 + np.arange(140) / 20.0
    paths = {"left": Path("left.csv"), "right": Path("right.csv"), "bottom": Path("bottom.csv")}

    class Reader(GaitResultWriter):
        def read_table(self, path, **_):
            return bottom_raw.copy() if path == paths["bottom"] else side_raw.copy()

    starts_by_side = iter(([20, 40], [30, 50, 60]))

    def calculate(*_args, **_kwargs):
        starts = next(starts_by_side)
        table = pd.DataFrame(1.0, index=range(len(starts)), columns=ALMA_PARAMETER_NAMES)
        table["stride_start (frame)"] = starts
        table["stride_end (frame)"] = np.array(starts) + 9
        coords = pd.DataFrame(index=range(80))
        coords.attrs["pixels_per_cm"] = 1.0
        return table, coords, [], [], [], starts, ()

    cfg = AlmaSettings(
        analysis_type="Spontaneous walking",
        frame_rate=10.0,
        pixels_per_cm=1.0,
        calibration_method="manual",
        likelihood_threshold=0.5,
        view_timing={"bottom": {"frame_rate": 20.0, "offset_s": 0.5}},
        swing_speed_threshold_cm_s=100.0,
    )
    item = AlmaViewCsvSet("recording", **{f"{s}_csv": p for s, p in paths.items()})
    tables, _ = calculate_recording_tables(item, cfg, Reader(), figures=RecordingFigures(), calculate=calculate)
    left, right = tables["left"], tables["right"]
    assert len(left) == 2 and len(right) == 3 and len(tables["general"]) == 1
    assert left["bottom_start_frame"].tolist() == [30, 70]
    assert left["bottom_end_frame"].tolist() == [49, 89]
    assert right["bottom_start_frame"].tolist() == [50, 90, 110]
    assert right["bottom_end_frame"].tolist() == [69, 109, 129]
    np.testing.assert_allclose(left["mean_hindlimb_base_support"], [2.975, 4.975])
    np.testing.assert_allclose(right["mean_hindlimb_base_support"], [3.975, 5.975, 6.975])
    assert not any(name.startswith("r-") for name in left)
    assert not any(name.startswith("l-") for name in right)
    np.testing.assert_allclose(left["hindlimb_stance_overlap_fraction"], 100.0)
    np.testing.assert_allclose(right["hindlimb_stance_overlap_fraction"], 100.0)


def test_opposite_phase_uses_real_onsets_and_general_uses_whole_time(monkeypatch):
    from dlc_gait_assembly.runway.manual.gait_analysis.business import gait_bottom_windows as module

    left = np.array([1, 1, 0, 0, 1, 1, 0, 0], bool)
    right = np.array([0, 1, 1, 0, 0, 1, 1, 0], bool)
    monkeypatch.setattr(module, "stance_mask", lambda _s, m, *_: left if m.endswith("left") else right)
    raw = coordinates(("lhpaw", "rhpaw", "lfpaw", "rfpaw"), 8, 1.0)
    cfg = AlmaSettings(frame_rate=1.0, calibration_method="manual", pixels_per_cm=1.0)
    track = read_view_track(raw, Path("bottom.csv"), "bottom", cfg)
    windows = BottomWindows(track, cfg, None, SimpleNamespace(butterworth_filter=lambda a, *_: a), raw)
    assert windows.stride(2.0, 6.0, "left")["opposite_hindlimb_phase_offset (%)"] == 75.0
    assert windows.stride(2.0, 6.0, "right")["opposite_hindlimb_phase_offset (%)"] == 50.0
    assert windows.stride(2.0, 6.0, "left")["hindlimb_stance_overlap_fraction"] == 25.0
    assert windows.stride(2.0, 6.0, "left")["hindlimb_swing_overlap_fraction"] == 25.0
    assert windows.stride(2.5, 5.5, "left")["hindlimb_stance_overlap_fraction"] == pytest.approx(100 / 6)
    assert windows.general(0.0, 8.0)["hindlimb_same_phase (%)"] == 50.0
    assert windows.general(0.0, 8.0)["hindlimb_stance_overlap (%)"] == 25.0
    assert windows.stride(-1.0, 2.0, "left")["bottom_alignment_coverage (%)"] == pytest.approx(200 / 3)
    assert np.isnan(windows.stride(-1.0, 2.0, "left")["hindlimb_stance_overlap_fraction"])
    assert np.isnan(windows.stride(-1.0, 2.0, "left")["hindlimb_swing_overlap_fraction"])


def test_no_shared_time_is_reported_instead_of_pairing_unrelated_frames(tmp_path, alma_fixtures_dir):
    from tests.runway.manual.gait_analysis.infrastructure.test_single_gait_csv import recording

    cfg = AlmaSettings(
        analysis_type="Spontaneous walking",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        view_timing={"bottom": {"offset_s": 1000.0}},
    )
    with pytest.raises(ValueError, match="timestamps do not overlap"):
        calculate_recording_tables(
            recording(tmp_path, alma_fixtures_dir, "mismatch"), cfg, GaitResultWriter(), figures=RecordingFigures()
        )


@pytest.mark.parametrize("method", ["Speed mixture (GMM)", "RustLab1 (bottom paw)"])
def test_preview_and_export_keep_identical_cycles_with_camera_timing(tmp_path, alma_fixtures_dir, method):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_use_cases import GaitPreviewUseCases
    from tests.runway.manual.gait_analysis.infrastructure.test_single_gait_csv import recording

    item = recording(tmp_path, alma_fixtures_dir, "timed")
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        likelihood_threshold=0.0,
        calibration_method="manual",
        pixels_per_cm=50.0,
        stride_detection_method=method,
        view_timing={
            "left": {"frame_rate": 100.0, "offset_s": 0.1},
            "right": {"frame_rate": 120.0, "offset_s": 0.2},
            "bottom": {"frame_rate": 110.0, "offset_s": 0.15},
        },
    )
    figures = RecordingFigures()
    calculate_recording_tables(item, settings, GaitResultWriter(), figures=figures)
    inputs = [(side.title(), getattr(item, f"{side}_csv")) for side in ("left", "right", "bottom")]
    preview = GaitPreviewUseCases(GaitResultWriter(), None)._recordings(inputs, settings)
    for label, result in preview:
        export = figures.sides[label.lower()]
        pd.testing.assert_frame_equal(
            result[0][["stride_start (frame)", "stride_end (frame)"]],
            export[0][["stride_start (frame)", "stride_end (frame)"]],
        )
        np.testing.assert_allclose(result[1].to_numpy(float), export[1].to_numpy(float), equal_nan=True)
        np.testing.assert_array_equal(result[2], export[2])
