"""Regression cases adapted from the supplied ALMA update, with no external runtime dependency."""

import json
import unittest
from types import SimpleNamespace

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_runway_analysis import analyze_runway, COLUMNS
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_joint_reconstruction import (
    interpolation_context,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_parameters import extract_parameters
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_drag_detection import find_drag
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import fix_column_names
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_joint_kinematics import angle

k = SimpleNamespace(
    extract_spontaneous_parameters=analyze_runway,
    extract_parameters=extract_parameters,
    find_drag=find_drag,
    fix_column_names=fix_column_names,
    angle=angle,
)


def synthetic_walk(fps=100, noise=0.15, scale=1.0, reverse=False, lift=15.0, seed=7, pause=None):
    rng = np.random.default_rng(seed)
    time = np.arange(10 * fps + 1) / fps
    delayed = np.clip(time - pause[0], 0.0, pause[1] - pause[0]) if pause else 0.0
    active = np.clip(time - 2.0 - delayed, 0.0, 6.0)
    period, stance, speed = 0.4, 0.25, 100.0
    cycle = np.floor(active / period + 1e-9)
    local = active - cycle * period
    fraction = np.clip((local - stance) / (period - stance), 0, 1)
    ease = fraction * fraction * (3 - 2 * fraction)
    toe_x = speed * period * cycle + 20.0 + speed * period * ease
    toe_y = 100.0 - lift * np.sin(np.pi * fraction)
    body_x = speed * active
    coords = {
        "toe": (toe_x, toe_y),
        "mtp": (toe_x + 3, toe_y - 4),
        "ankle": (body_x + 5, np.full(len(time), 82.0)),
        "knee": (body_x - 4, np.full(len(time), 72.0)),
        "hip": (body_x, np.full(len(time), 62.0)),
        "iliac crest": (body_x - 12, np.full(len(time), 50.0)),
    }
    data = pd.DataFrame({"bodyparts coords": np.arange(len(time))})
    for bp, (x, y) in coords.items():
        data[f"{bp} x"] = (x + rng.normal(0, noise, len(time))) * scale * (-1 if reverse else 1)
        data[f"{bp} y"] = (y + rng.normal(0, noise, len(time))) * scale
        data[f"{bp} likelihood"] = 1.0
        data.loc[(time < 1.0) | (time > 9.0), f"{bp} likelihood"] = 0.1
    return data


class TestUpdatedRunway(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = synthetic_walk()
        cls.baseline = k.extract_spontaneous_parameters(100, cls.data, 6, pixels_per_cm=50, drag_clearance_cm=0.1)

    def analyze(self, data=None, fps=100, **kwargs):
        return k.extract_spontaneous_parameters(
            fps, self.data if data is None else data, 6, **{"pixels_per_cm": 50, "drag_clearance_cm": 0.1, **kwargs}
        )

    def test_complete_cycles_have_known_synthetic_contact_timing(self):
        params = self.baseline[0]
        self.assertGreater(len(params), 8)
        self.assertTrue(params["cycle duration (s)"].notna().all())
        for start in params["stride_start (frame)"]:
            offset = (start / 100.0 - 2.0) / 0.4
            self.assertLess(abs(offset - round(offset)) * 0.4, 0.04)
        self.assertTrue((params["stride_end (frame)"] > params["stride_start (frame)"]).all())
        np.testing.assert_allclose(
            params["stance duration (s)"] + params["swing duration (s)"], params["cycle duration (s)"]
        )

    def test_no_intervals_are_created_during_stationary_or_invisible_tails(self):
        for interval in self.baseline[0].attrs["analysis_report"]["intervals"]:
            self.assertGreaterEqual(interval["start_frame"], 190)
            self.assertLessEqual(interval["end_frame"], 810)
        self.assertTrue((self.baseline[2][:100] == -1).all())
        self.assertTrue((self.baseline[2][900:] == -1).all())

    def test_stationary_tracking_noise_does_not_create_cycles(self):
        data = synthetic_walk()
        for bp in ("toe", "mtp", "ankle", "knee", "hip", "iliac crest"):
            data[f"{bp} x"] -= np.clip(np.arange(len(data)) / 100.0 - 2.0, 0.0, 6.0) * 100.0
        # Fix the foot to a supported position; leave only small tracking noise.
        rng = np.random.default_rng(11)
        data["toe x"] = 20 + rng.normal(0, 0.15, len(data))
        result = self.analyze(data)
        self.assertTrue(result[0].empty)
        self.assertEqual(result[0].attrs["analysis_report"]["status"], "no_usable_strides")

    def test_input_data_and_frame_axis_are_preserved(self):
        data = self.data.copy(deep=True)
        data.index = np.arange(4000, 4000 + len(data))
        before = data.copy(deep=True)
        a = self.analyze(data)
        b = self.analyze(data)
        pd.testing.assert_frame_equal(data, before, check_exact=True)
        pd.testing.assert_frame_equal(a[0], b[0], check_exact=True)
        self.assertEqual(len(a[1]), len(data))
        self.assertEqual(len(a[2]), len(data))
        np.testing.assert_array_equal(a[1]["runway phase"], a[2])
        self.assertTrue(a[1]["runway drag"].iloc[900:].isna().all())

    def test_rounding_is_not_required_for_detection(self):
        rounded = self.data.copy()
        rounded["toe x"] = (rounded["toe x"] / 0.25).round() * 0.25
        result = self.analyze(rounded)
        self.assertLessEqual(abs(len(result[0]) - len(self.baseline[0])), 1)
        for frame in result[5]:
            self.assertLessEqual(min(abs(frame - np.asarray(self.baseline[5]))), 3)

    def test_spatial_resolution_does_not_change_event_detection(self):
        result = self.analyze(synthetic_walk(scale=2.0), pixels_per_cm=100.0)
        np.testing.assert_array_equal(result[5], self.baseline[5])
        np.testing.assert_array_equal(result[2], self.baseline[2])
        np.testing.assert_allclose(result[0]["stride length (cm)"], self.baseline[0]["stride length (cm)"])

    def test_time_based_detection_scales_with_sampling_rate(self):
        high = self.analyze(synthetic_walk(fps=200), fps=200)
        self.assertLessEqual(abs(len(high[5]) - len(self.baseline[5])), 1)
        for time in np.asarray(high[5]) / 200:
            self.assertLess(min(abs(time - np.asarray(self.baseline[5]) / 100)), 0.04)

    def test_pause_inside_a_recording_splits_complete_cycles(self):
        result = self.analyze(synthetic_walk(pause=(4.0, 5.0)))
        self.assertGreater(len(result[0]), 5)
        self.assertTrue((result[2][420:480] == -1).all())
        for r in result[0].attrs["analysis_report"]["intervals"]:
            self.assertFalse(r["start_frame"] < 420 and r["end_frame"] > 480)

    def test_body_reference_can_fall_back_without_a_hip(self):
        data = self.data.drop(columns=["hip x", "hip y", "hip likelihood"])
        result = self.analyze(data)
        self.assertGreater(len(result[0]), 8)
        self.assertEqual(result[0].attrs["analysis_report"]["body_reference"], "iliac crest")

    def test_direction_mirroring_and_explicit_direction(self):
        mirrored = self.analyze(synthetic_walk(reverse=True))
        np.testing.assert_array_equal(mirrored[5], self.baseline[5])
        requested = self.analyze(synthetic_walk(reverse=True), right_to_left=True)
        np.testing.assert_array_equal(requested[5], mirrored[5])
        wrong = self.analyze(synthetic_walk(reverse=True), right_to_left=False)
        self.assertTrue(wrong[0].empty)
        self.assertTrue(any("direction" in s for s in wrong[0].attrs["analysis_report"]["warnings"]))

    def test_missing_knee_does_not_remove_timing_or_unrelated_angles(self):
        data = self.data.copy()
        data[["knee x", "knee y"]] = np.nan
        result = self.analyze(data)
        np.testing.assert_array_equal(result[5], self.baseline[5])
        np.testing.assert_array_equal(result[0]["cycle duration (s)"], self.baseline[0]["cycle duration (s)"])
        self.assertTrue(result[0]["knee joint extension (deg)"].isna().all())
        self.assertTrue(result[0]["ankle joint extension (deg)"].isna().all())
        self.assertTrue(result[0]["mtp joint extension (deg)"].notna().all())
        self.assertTrue(any(r["unavailable_metrics"] for r in result[0].attrs["analysis_report"]["intervals"]))

    def test_one_joint_gap_does_not_poison_the_entire_trial(self):
        data = self.data.copy()
        data.loc[490, "knee x"] = np.nan
        result = self.analyze(data)
        self.assertTrue(result[0]["knee joint extension (deg)"].isna().any())
        self.assertTrue(result[0]["knee joint extension (deg)"].notna().any())
        np.testing.assert_array_equal(result[5], self.baseline[5])

    def test_absent_optional_joints_are_explicitly_unavailable(self):
        data = self.data.drop(columns=["knee x", "knee y", "knee likelihood"])
        result = self.analyze(data)
        np.testing.assert_array_equal(result[5], self.baseline[5])
        self.assertTrue(result[0]["knee joint extension (deg)"].isna().all())

    def test_long_foot_gap_splits_bouts_without_compressing_time(self):
        data = self.data.copy()
        data.loc[460:490, "toe likelihood"] = 0.1
        result = self.analyze(data)
        for r in result[0].attrs["analysis_report"]["intervals"]:
            self.assertFalse(r["start_frame"] < 460 and r["end_frame"] > 490)
        self.assertEqual(len(result[1]), len(data))
        self.assertTrue((result[2][460:491] == -1).all())

    def test_short_detection_gap_is_flagged_but_not_used_for_angles(self):
        data = self.data.copy()
        data.loc[490, "toe likelihood"] = 0.1
        result = self.analyze(data)
        report = result[0].attrs["analysis_report"]
        self.assertEqual(report["tracking_confidence"]["toe"]["short_gap_frames_interpolated_for_detection"], 1)
        self.assertTrue(any(r["detection_interpolated_frames"] for r in report["intervals"]))
        self.assertTrue(result[0]["mtp joint extension (deg)"].isna().any())

    def test_truncated_recording_does_not_get_a_fabricated_final_cycle(self):
        data = self.data.iloc[:575].copy()
        result = self.analyze(data)
        self.assertTrue(all(r["end_frame"] < len(data) - 1 for r in result[0].attrs["analysis_report"]["intervals"]))
        self.assertGreater(result[0].attrs["analysis_report"]["discarded_edge_contacts"], 0)

    def test_zero_height_movement_is_not_assumed_to_be_normal_swing(self):
        result = self.analyze(synthetic_walk(noise=0.0, lift=0.0), drag_clearance_cm=0.2)
        self.assertGreater(len(result[0]), 5)
        self.assertTrue((result[0]["step height (cm)"] < 1e-8).all())
        np.testing.assert_allclose(result[0]["drag percentage (%)"], 1.0)
        excluded = self.analyze(synthetic_walk(noise=0.0, lift=0.0), step_height_min_cm=0.1)
        self.assertEqual(excluded[0].attrs["analysis_report"]["retained_intervals"], 0)

    def test_optional_range_bypass_does_not_bypass_motion_quality(self):
        result = self.analyze(stride_length_max_cm=0.00001, no_outlier_filter=True)
        self.assertGreater(result[0].attrs["analysis_report"]["retained_intervals"], 8)
        stationary = self.data.iloc[:180].copy()
        result = self.analyze(stationary, no_outlier_filter=True)
        self.assertTrue(result[0].empty)

    def test_optional_drag_filter_has_explicit_rejection_reasons(self):
        result = self.analyze(synthetic_walk(noise=0.0, lift=0.0), drag_clearance_cm=0.2, dragging_filter=True)
        report = result[0].attrs["analysis_report"]
        self.assertEqual(report["retained_intervals"], 0)
        self.assertTrue(all("near_continuous_dragging_filter" in r["rejection_reasons"] for r in report["intervals"]))

    def test_empty_return_schema_and_json_report(self):
        result = self.analyze(self.data.iloc[:10])
        self.assertEqual(len(result), 6)
        self.assertEqual(list(result[0]), COLUMNS)
        self.assertTrue(result[0].empty)
        self.assertEqual(result[4], [])
        self.assertEqual(result[5], [])
        json.dumps(result[0].attrs["analysis_report"], allow_nan=False)

    def test_calibration_and_invalid_inputs_are_not_silently_assumed(self):
        for settings, message in [
            ({"pixels_per_cm": None}, "Measured pixels per cm"),
            ({"pixels_per_cm": 0}, "Measured pixels per cm"),
            ({"confidence_threshold": 1}, "confidence threshold"),
            ({"max_gap_s": -1}, "Maximum gap"),
        ]:
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, message):
                self.analyze(**settings)
        with self.assertRaisesRegex(ValueError, "hip or iliac crest"):
            self.analyze(
                self.data.drop(columns=[f"{b} {c}" for b in ("hip", "iliac crest") for c in ("x", "y", "likelihood")])
            )
        with self.assertRaisesRegex(ValueError, "unique mapped"):
            self.analyze(pd.concat([self.data, self.data[["toe x"]]], axis=1))

    def test_source_frame_gaps_are_not_mistaken_for_consecutive_samples(self):
        data = self.data.copy()
        data.loc[500:, "bodyparts coords"] += 1
        with self.assertRaisesRegex(ValueError, "Source frame labels must be consecutive"):
            self.analyze(data)


class TestUpdatedJointMetrics(unittest.TestCase):
    def analyze(self, data, **settings):
        return k.extract_spontaneous_parameters(
            100.0, data, 6.0, pixels_per_cm=50.0, joint_interpolation="linear", **settings
        )

    def test_filter_context_includes_observed_samples_around_reconstruction(self):
        xy = np.ones((100, 2))
        xy[60:70] = np.nan
        filled = np.zeros(100, dtype=bool)
        filled[20] = True
        context = interpolation_context(xy, filled)
        self.assertTrue(context[:60].all())
        self.assertFalse(context[60:].any())

    def test_opt_in_with_no_gaps_preserves_all_parameter_values(self):
        data = synthetic_walk()
        observed = k.extract_spontaneous_parameters(100.0, data, 6.0, pixels_per_cm=50.0)
        reconstructed = self.analyze(data)
        pd.testing.assert_frame_equal(observed[0], reconstructed[0], check_exact=True)
        np.testing.assert_array_equal(observed[2], reconstructed[2])
        np.testing.assert_array_equal(observed[5], reconstructed[5])

    def test_short_joint_gap_recovers_angles_without_changing_phase_events(self):
        data = synthetic_walk()
        data.loc[490, ["knee x", "knee y"]] = np.nan
        before = data.copy(deep=True)
        observed = k.extract_spontaneous_parameters(100.0, data, 6.0, pixels_per_cm=50.0)
        result = self.analyze(data)
        np.testing.assert_array_equal(result[2], observed[2])
        np.testing.assert_array_equal(result[5], observed[5])
        affected = observed[0]["knee joint extension (deg)"].isna()
        self.assertTrue(affected.any())
        self.assertTrue(result[0].loc[affected, "knee joint extension (deg)"].notna().all())
        self.assertTrue(result[1].loc[490, "knee metric interpolated"])
        self.assertTrue(np.isnan(result[1].loc[490, "knee raw x"]))
        self.assertTrue(np.isnan(result[1].loc[490, "knee observed filtered x"]))
        self.assertEqual(result[1].loc[490, "knee likelihood"], 1.0)
        pd.testing.assert_frame_equal(data, before, check_exact=True)
        report = result[0].attrs["analysis_report"]
        interval = next(r for r in report["intervals"] if r["start_frame"] <= 490 < r["end_frame"])
        quality = interval["metric_quality"]["knee_angle"]
        self.assertEqual(quality["status"], "estimated")
        self.assertEqual(quality["interpolated_frames"], 1)
        self.assertIsInstance(quality["extension_at_interpolated_frame"], bool)
        self.assertIsNone(interval["observed_only_metrics"]["knee joint extension (deg)"])
        json.dumps(report, allow_nan=False)

    def test_per_metric_fraction_limit_keeps_timing_and_unrelated_angles(self):
        data = synthetic_walk()
        data.loc[490, "knee likelihood"] = 0.1
        result = self.analyze(data, joint_max_interpolated_fraction=0.0)
        intervals = result[0].attrs["analysis_report"]["intervals"]
        index = next(i for i, row in enumerate(intervals) if row["start_frame"] <= 490 < row["end_frame"])
        self.assertTrue(np.isnan(result[0].loc[index, "knee joint extension (deg)"]))
        self.assertTrue(np.isfinite(result[0].loc[index, "mtp joint extension (deg)"]))
        self.assertTrue(np.isfinite(result[0].loc[index, "cycle duration (s)"]))
        self.assertIn("fraction exceeds", intervals[index]["unavailable_metrics"]["knee joint extension (deg)"])

    def test_long_joint_gaps_leave_dependent_metrics_unavailable(self):
        data = synthetic_walk()
        data.loc[480:490, "knee likelihood"] = 0.1
        result = self.analyze(data)
        self.assertFalse(result[1].loc[480:490, "knee metric interpolated"].any())
        self.assertTrue(result[0]["knee joint extension (deg)"].isna().any())
        self.assertTrue(result[0]["cycle duration (s)"].notna().all())

    def test_invalid_joint_settings_are_explanatory(self):
        for settings in [
            {"joint_interpolation": "cubic"},
            {"joint_max_gap_s": None},
            {"joint_max_gap_s": 1 + 2j},
            {"joint_max_interpolated_fraction": 1.1},
            {"joint_max_segment_change": -1},
        ]:
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, "Joint"):
                k.extract_spontaneous_parameters(100.0, synthetic_walk(), 6.0, pixels_per_cm=50.0, **settings)


def test_updated_detector_native_exports_preserve_half_open_frames_and_provenance(tmp_path):
    from dataclasses import replace

    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import (
        calculate_alma_recording,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import (
        prepare_full_recording_stickplot,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import RUNWAY_METHOD
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
        run_alma_gait_analysis_in_process,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
        GaitStickplotRenderer,
    )

    data = synthetic_walk()
    raw = data.drop(columns="bodyparts coords")
    raw.columns = pd.MultiIndex.from_tuples([column.rsplit(" ", 1) for column in raw.columns])
    path = tmp_path / "walk.csv"
    raw.to_csv(path)
    # DLC has a scorer/header row before the bodypart/coordinate rows.
    content = path.read_text()
    path.write_text(",".join(["scorer"] * (len(raw.columns) + 1)) + "\n" + content)
    settings = AlmaSettings(
        input_mode="Single side view",
        output_format="alma",
        analysis_type="Spontaneous walking",
        stride_detection_method=RUNWAY_METHOD,
        frame_rate=100,
        right_to_left="auto",
        pixels_per_cm=50,
        generate_alma_representations=False,
    )
    result = run_alma_gait_analysis_in_process([path], tmp_path / "output", settings)[0]
    report_path = next(p for p in result.output_files if p.suffix == ".json")
    report = json.loads(report_path.read_text())
    assert report["detector"] == "bout_contact_v1"
    assert report["retained_intervals"] > 8
    assert report["interval_convention"] == "[start_frame, end_frame)"
    coords = pd.read_csv(next(p for p in result.output_files if p.name == "side_coordinates.csv"))
    assert len(coords) == len(raw)
    assert {"toe raw x", "toe event x", "toe analysis x", "runway phase", "knee metric interpolated"} <= set(coords)
    table = pd.read_csv(next(p for p in result.output_files if p.name == "side_stride_parameters.csv"))
    np.testing.assert_allclose(
        table["cycle duration (s)"], (table["stride_end (frame)"] - table["stride_start (frame)"]) / 100
    )
    svg = next(p for p in result.output_files if p.suffix == ".svg").read_text()
    assert "consecutive retained cycles" in svg and "tracked keypoints" in svg
    assert "Full recording shown" not in svg
    for source in ("tracked", "analysis"):
        recording = calculate_alma_recording(raw, replace(settings, runway_stickplot_source=source))
        prepared = prepare_full_recording_stickplot(recording[0], recording[1], recording[3], recording[2])
        assert prepared.native_alma
        image = GaitStickplotRenderer().render_preview(prepared)
        assert b"consecutive retained cycles" in image
    # Review source never changes analysis values or contact events.
    first = calculate_alma_recording(raw, settings)
    second = calculate_alma_recording(raw, replace(settings, runway_stickplot_source="analysis"))
    pd.testing.assert_frame_equal(first[0], second[0], check_exact=True)
    np.testing.assert_array_equal(first[2], second[2])


def test_metric_quality_explains_why_tracked_bones_can_have_unavailable_angles():
    data = synthetic_walk()
    data.loc[490, ["knee x", "knee y"]] = np.nan
    result = analyze_runway(100.0, data, 6.0, pixels_per_cm=50.0)
    interval = next(
        item
        for item in result[0].attrs["analysis_report"]["intervals"]
        if item["start_frame"] <= 490 < item["end_frame"]
    )
    knee = interval["metric_quality"]["knee_angle"]
    assert knee["status"] == "unavailable"
    assert knee["missing_observation_frames_by_body_part"]["knee"] == 1
    assert knee["valid_filtered_metric_frames"] < knee["interval_frames"]
    assert knee["unavailable_filtered_frames_by_body_part"]["knee"] >= 1
    assert interval["metric_quality"]["mtp_angle"]["status"] == "observed"
