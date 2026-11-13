"""Assemble treadmill cycle measurements using the established ALMA formulas and acceptance rules."""

from __future__ import annotations

import statistics as stat

import numpy as np
import pandas as pd
import scipy

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_drag_detection import find_drag
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_joint_kinematics import (
    compute_limb_joint_angles,
    find_limb_length,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_spontaneous_cycles import (
    detect_dragging_movement_cycles as _detect_dragging_movement_cycles,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_stride_measurements import (
    find_euclidean_speed,
    find_stride_len,
    find_swing_stance,
    pairwise_dtw,
    parse_stride_lists,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_correction import treadmill_correction
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_cycles import (
    robust_stance_segments_treadmill as _robust_stance_segments_treadmill,
)


def extract_parameters(
    frame_rate,
    pd_dataframe,
    cutoff_f,
    bodypart,
    cm_speed=None,
    right_to_left=True,
    step_height_min_cm=0.0,
    step_height_max_cm=1.5,
    stride_length_min_cm=0.0,
    stride_length_max_cm=8.0,
    drag_clearance_cm=0.3,
    drag_min_consecutive_frames=4,
    pixels_per_cm_override=None,
):
    """Validate input and preserve caller coordinates while collecting interval diagnostics."""
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_validation import (
        attach_report,
        prepare_input,
        resolve_calibration,
    )

    limits = dict(
        step_height_min_cm=step_height_min_cm,
        step_height_max_cm=step_height_max_cm,
        stride_length_min_cm=stride_length_min_cm,
        stride_length_max_cm=stride_length_max_cm,
        drag_clearance_cm=drag_clearance_cm,
        drag_min_consecutive_frames=drag_min_consecutive_frames,
    )
    working, report = prepare_input(pd_dataframe, frame_rate, cutoff_f, bodypart, cm_speed, right_to_left, limits)
    method = "belt_motion" if pixels_per_cm_override is None else "manual"
    calibration = resolve_calibration(working, method, pixels_per_cm_override)
    report["settings"]["calibration_method"] = method
    result = _extract_treadmill_parameters(
        frame_rate, working, cutoff_f, bodypart, cm_speed, right_to_left, _spatial_calibration=calibration, **limits
    )
    result[1].attrs["pixels_per_cm"] = result[1].attrs["_treadmill_calibration"]["pixels_per_cm"]
    result = attach_report(result, report)
    result[1].attrs["analysis_report"] = report
    return result


def _extract_treadmill_parameters(
    frame_rate,
    pd_dataframe,
    cutoff_f,
    bodypart,
    cm_speed=None,
    right_to_left=True,
    step_height_min_cm=0.0,
    step_height_max_cm=1.5,
    stride_length_min_cm=0.0,
    stride_length_max_cm=8.0,
    drag_clearance_cm=0.3,
    drag_min_consecutive_frames=4,
    _spatial_calibration=None,
):
    """
    pd_dataframe: contains raw coordinates (not adjusted for treadmill movement, unfiltered)
    bodypart: which bodypart to use for stride estimation

    """
    bodyparts = ["toe", "mtp", "ankle", "knee", "hip", "iliac crest"]  # modify this
    starts = []
    ends = []

    cycle_dur_secs = []
    cycle_dur_frames = []
    cycle_vs = []

    stride_lens = []
    stance_dur_secs = []
    swing_dur_secs = []
    swing_percentages = []
    stance_percentages = []

    limb_len_means = []
    limb_len_maxs = []
    limb_len_mins = []
    limb_len_sds = []

    step_heights = []
    max_v_during_swings = []

    mtp_joint_extensions = []
    ankle_joint_extensions = []
    knee_joint_extensions = []
    hip_joint_extensions = []

    mtp_joint_flexions = []
    ankle_joint_flexions = []
    knee_joint_flexions = []
    hip_joint_flexions = []

    mtp_joint_amplitudes = []
    ankle_joint_amplitudes = []
    knee_joint_amplitudes = []
    hip_joint_amplitudes = []

    mtp_joint_sds = []
    ankle_joint_sds = []
    knee_joint_sds = []
    hip_joint_sds = []

    drag_ts = []
    drag_percentages = []
    drag_masks = []  # For visualization in stickplot
    is_stance = []  # Initialize early for excessive dragging case

    dtw_x_plane_5_means = []  # dynamic time warping: measures spatial variability
    dtw_x_plane_5_sds = []
    dtw_y_plane_5_means = []
    dtw_y_plane_5_sds = []
    dtw_xy_plane_5_means = []
    dtw_xy_plane_5_sds = []

    dtw_x_plane_10_means = []
    dtw_x_plane_10_sds = []
    dtw_y_plane_10_means = []
    dtw_y_plane_10_sds = []
    dtw_xy_plane_10_means = []
    dtw_xy_plane_10_sds = []

    x_change = np.diff(pd_dataframe[f"{bodypart} x"][pd_dataframe[f"{bodypart} likelihood"] > 0.5])
    if len(x_change) == 0 or not np.any(x_change):
        raise ValueError(
            "No usable toe movement to estimate treadmill calibration. Check the tracking and recording segment."
        )
    x_change_filt = x_change[
        (x_change < np.mean(x_change) + 1 * np.std(x_change)) & (x_change > np.mean(x_change) - 1 * np.std(x_change))
    ]
    if len(x_change_filt) == 0:
        raise ValueError(
            "No usable treadmill-motion samples after filtering. Check toe tracking and the recording segment."
        )

    # Auto-detect walking direction if not specified
    if right_to_left == "auto" or right_to_left is None:
        # Check which direction has more movement (stance phase shows treadmill movement)
        positive_changes = x_change_filt[x_change_filt > 0]
        negative_changes = x_change_filt[x_change_filt < 0]

        if len(positive_changes) > len(negative_changes):
            right_to_left = True
            # Auto-detected walking direction: right-to-left
        else:
            right_to_left = False
            # Auto-detected walking direction: left-to-right

    # Detect treadmill speed based on walking direction
    # Right-to-left: mouse moves left (negative), treadmill moves right (positive during stance)
    # Left-to-right: mouse moves right (positive), treadmill moves left (negative during stance)
    if right_to_left:
        belt_samples = x_change_filt[x_change_filt > 0]
    else:
        belt_samples = x_change_filt[x_change_filt < 0]
    if len(belt_samples) == 0:
        raise ValueError(
            "No treadmill-motion samples match the selected walking direction. Check direction and toe tracking."
        )
    px_speed, _ = scipy.stats.norm.fit(belt_samples)
    if not right_to_left:
        px_speed = -px_speed  # Make positive for consistency

    if cm_speed is None:
        # cm_speed must be provided by user for treadmill analysis
        raise ValueError("cm_speed must be provided for treadmill analysis")

    pixels_per_cm = 1 / (cm_speed / px_speed / frame_rate)
    calibration_details = {"method": "belt_motion"}
    if _spatial_calibration is not None:
        calibration_details = _spatial_calibration.copy()
        pixels_per_cm = calibration_details["pixels_per_cm"]
    pd_dataframe.attrs["_treadmill_calibration"] = {
        **calibration_details,
        "pixels_per_frame": float(px_speed),
        "pixels_per_cm": float(pixels_per_cm),
        "right_to_left": bool(right_to_left),
        "motion_correction": "tracked_belt_motion_in_pixels",
        "tracking_implied_belt_speed_cm_s": float(px_speed * frame_rate / pixels_per_cm),
    }
    intervals = []
    pd_dataframe.attrs["_treadmill_intervals"] = intervals
    pd_dataframe_corrected = treadmill_correction(pd_dataframe, bodyparts, px_speed, right_to_left)

    smooth_toe_x = butterworth_filter(pd_dataframe_corrected["toe x"], frame_rate, cutoff_f)
    smooth_mtp_x = butterworth_filter(pd_dataframe_corrected["mtp x"], frame_rate, cutoff_f)
    smooth_ankle_x = butterworth_filter(pd_dataframe_corrected["ankle x"], frame_rate, cutoff_f)
    smooth_knee_x = butterworth_filter(pd_dataframe_corrected["knee x"], frame_rate, cutoff_f)
    smooth_hip_x = butterworth_filter(pd_dataframe_corrected["hip x"], frame_rate, cutoff_f)
    smooth_crest_x = butterworth_filter(pd_dataframe_corrected["iliac crest x"], frame_rate, cutoff_f)

    smooth_toe_y = butterworth_filter(pd_dataframe["toe y"], frame_rate, cutoff_f)
    smooth_mtp_y = butterworth_filter(pd_dataframe["mtp y"], frame_rate, cutoff_f)
    smooth_ankle_y = butterworth_filter(pd_dataframe["ankle y"], frame_rate, cutoff_f)
    smooth_knee_y = butterworth_filter(pd_dataframe["knee y"], frame_rate, cutoff_f)
    smooth_hip_y = butterworth_filter(pd_dataframe["hip y"], frame_rate, cutoff_f)
    smooth_crest_y = butterworth_filter(pd_dataframe["iliac crest y"], frame_rate, cutoff_f)

    (
        angles_toe_mtp_ankle,
        angles_mtp_ankle_knee,
        angles_ankle_knee_hip,
        angles_knee_hip_crest,
        elevation_angles,
        elevation_angle_change,
    ) = compute_limb_joint_angles(
        smooth_toe_x,
        smooth_toe_y,
        smooth_mtp_x,
        smooth_mtp_y,
        smooth_ankle_x,
        smooth_ankle_y,
        smooth_knee_x,
        smooth_knee_y,
        smooth_hip_x,
        smooth_hip_y,
        smooth_crest_x,
        smooth_crest_y,
    )

    limb_lens = find_limb_length(smooth_toe_x, smooth_toe_y, smooth_hip_x, smooth_hip_y)
    velocities = find_euclidean_speed(smooth_toe_x, smooth_toe_y, frame_rate)

    # Check if there's any meaningful forward movement at all
    if np.abs(stat.median(x_change)) < 0.1 and len(np.where(np.abs(x_change) < 0.5)[0]) / len(x_change) > 0.95:
        # No meaningful forward movement detected - mouse may be stationary

        starts.append(np.nan)
        ends.append(np.nan)
        cycle_dur_secs.append(np.nan)
        cycle_dur_frames.append(np.nan)
        stride_lens.append(np.nan)
        cycle_vs.append(np.nan)
        stance_dur_secs.append(np.nan)
        swing_dur_secs.append(np.nan)
        swing_percentages.append(np.nan)
        stance_percentages.append(np.nan)
        limb_len_means.append(np.mean(limb_lens) / pixels_per_cm)
        limb_len_maxs.append(np.nan)
        limb_len_mins.append(np.nan)
        limb_len_sds.append(np.std(limb_lens) / pixels_per_cm)
        step_heights.append(0)
        max_v_during_swings.append(np.nan)

        mtp_joint_extensions.append(np.nan)
        mtp_joint_flexions.append(np.nan)
        mtp_joint_amplitudes.append(np.nan)

        ankle_joint_extensions.append(np.nan)
        ankle_joint_flexions.append(np.nan)
        ankle_joint_amplitudes.append(np.nan)

        knee_joint_extensions.append(np.nan)
        knee_joint_flexions.append(np.nan)
        knee_joint_amplitudes.append(np.nan)

        hip_joint_extensions.append(np.nan)
        hip_joint_flexions.append(np.nan)
        hip_joint_amplitudes.append(np.nan)

        mtp_joint_sds.append(np.nan)
        ankle_joint_sds.append(np.nan)
        knee_joint_sds.append(np.nan)
        hip_joint_sds.append(np.nan)

        drag_ts.append(np.nan)
        drag_percentages.append(1)
        drag_masks.append(np.array([]))
        is_stance = [0] * len(pd_dataframe)  # All frames considered as invalid/unknown
        dtw_x_plane_5_means.append(np.nan)
        dtw_x_plane_5_sds.append(np.nan)
        dtw_y_plane_5_means.append(np.nan)
        dtw_y_plane_5_sds.append(np.nan)
        dtw_xy_plane_5_means.append(np.nan)
        dtw_xy_plane_5_sds.append(np.nan)
        dtw_x_plane_10_means.append(np.nan)
        dtw_x_plane_10_sds.append(np.nan)
        dtw_y_plane_10_means.append(np.nan)
        dtw_y_plane_10_sds.append(np.nan)
        dtw_xy_plane_10_means.append(np.nan)
        dtw_xy_plane_10_sds.append(np.nan)

        # Return early for excessive dragging case
        for bodypart in bodyparts:
            for coord in ["x", "y"]:
                pd_dataframe[f"{bodypart} {coord}"] = butterworth_filter(
                    pd_dataframe[f"{bodypart} {coord}"], frame_rate, cutoff_f
                )

        return (
            pd.DataFrame(
                data=np.array(
                    [
                        starts,
                        ends,
                        cycle_dur_secs,
                        cycle_dur_frames,
                        cycle_vs,
                        stride_lens,
                        stance_dur_secs,
                        swing_dur_secs,
                        swing_percentages,
                        stance_percentages,
                        limb_len_means,
                        limb_len_maxs,
                        limb_len_mins,
                        limb_len_sds,
                        step_heights,
                        max_v_during_swings,
                        mtp_joint_extensions,
                        mtp_joint_flexions,
                        mtp_joint_amplitudes,
                        mtp_joint_sds,
                        ankle_joint_extensions,
                        ankle_joint_flexions,
                        ankle_joint_amplitudes,
                        ankle_joint_sds,
                        knee_joint_extensions,
                        knee_joint_flexions,
                        knee_joint_amplitudes,
                        knee_joint_sds,
                        hip_joint_extensions,
                        hip_joint_flexions,
                        hip_joint_amplitudes,
                        hip_joint_sds,
                        drag_ts,
                        drag_percentages,
                        dtw_x_plane_5_means,
                        dtw_x_plane_5_sds,
                        dtw_y_plane_5_means,
                        dtw_y_plane_5_sds,
                        dtw_xy_plane_5_means,
                        dtw_xy_plane_5_sds,
                        dtw_x_plane_10_means,
                        dtw_x_plane_10_sds,
                        dtw_y_plane_10_means,
                        dtw_y_plane_10_sds,
                        dtw_xy_plane_10_means,
                        dtw_xy_plane_10_sds,
                    ]
                ).T,
                columns=[
                    "stride_start (frame)",
                    "stride_end (frame)",
                    "cycle duration (s)",
                    "cycle duration (no. frames)",
                    "cycle velocity (cm/s)",
                    "stride length (cm)",
                    "stance duration (s)",
                    "swing duration (s)",
                    "swing percentage (%)",
                    "stance percentage (%)",
                    "mean toe-to-crest distance (cm)",
                    "max toe-to-crest distance (cm)",
                    "min toe-to-crest distance (cm)",
                    "toe-to-crest distance SD (cm)",
                    "step height (cm)",
                    "max velocity during swing (cm/s)",
                    "mtp joint extension (deg)",
                    "mtp joint flexion (deg)",
                    "mtp joint amplitude (deg)",
                    "mtp joint SD (deg)",
                    "ankle joint extension (deg)",
                    "ankle joint flexion (deg)",
                    "ankle joint amplitude (deg)",
                    "ankle joint SD (deg)",
                    "knee joint extension (deg)",
                    "knee joint flexion (deg)",
                    "knee joint amplitude (deg)",
                    "knee joint SD (deg)",
                    "hip joint extension (deg)",
                    "hip joint flexion (deg)",
                    "hip joint amplitude (deg)",
                    "hip joint SD (deg)",
                    "drag duration (s)",
                    "drag percentage (%)",
                    "Variability x plane 5 strides mean",
                    "Variability x plane 5 strides SD",
                    "Variability y plane 5 strides mean",
                    "Variability y plane 5 strides SD",
                    "Variability xy plane 5 strides mean",
                    "Variability xy plane 5 strides SD",
                    "Variability x plane 10 strides mean",
                    "Variability x plane 10 strides SD",
                    "Variability y plane 10 strides mean",
                    "Variability y plane 10 strides SD",
                    "Variability xy plane 10 strides mean",
                    "Variability xy plane 10 strides SD",
                ],
            ),
            pd_dataframe,
            is_stance,
            bodyparts,
            drag_masks,
            starts,
        )

    else:
        # Try normal stance detection first
        is_stance, starts, ends, treadmill_y = _robust_stance_segments_treadmill(
            pd_dataframe, frame_rate, cutoff_f, right_to_left
        )

        # If no strides detected, try alternative detection for dragging mice
        if len(starts) == 0:
            # No strides detected with normal method - trying alternative detection for dragging mice
            # Use forward movement cycles instead of stance/swing phases
            is_stance, starts, ends, treadmill_y = _detect_dragging_movement_cycles(
                pd_dataframe, frame_rate, cutoff_f, right_to_left
            )

        if not starts:
            from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_validation import (
                PARAMETER_COLUMNS,
            )

            return pd.DataFrame(columns=PARAMETER_COLUMNS), pd_dataframe, is_stance, bodyparts, [], []

        starts_included = []
        ends_included = []

        for i in range(len(starts)):
            stride_len = find_stride_len(smooth_toe_x, starts[i], ends[i])  # in pixel
            stride_len_cm = stride_len / pixels_per_cm
            limb_len_max = max(limb_lens[starts[i] : ends[i]]) / pixels_per_cm
            cycle_dur_frame = ends[i] - starts[i]
            cycle_v = stride_len / cycle_dur_frame * frame_rate  # (px / frames) * (frames/s) = px/s

            stance_dur_frame, swing_perc, stance_perc = find_swing_stance(elevation_angle_change, starts[i], ends[i])
            swing_dur_sec = (cycle_dur_frame - stance_dur_frame) / frame_rate

            if swing_dur_sec and stance_dur_frame > 0:
                # min: image y axis starts from top
                step_height = (
                    -(
                        min(smooth_toe_y[starts[i] + stance_dur_frame : ends[i]])
                        - max(smooth_toe_y[starts[i] : starts[i] + stance_dur_frame])
                    )
                    / pixels_per_cm
                )
            elif swing_dur_sec and stance_dur_frame == 0:
                step_height = (
                    -(min(smooth_toe_y[starts[i] + stance_dur_frame : ends[i]]) - smooth_toe_y[starts[i]])
                    / pixels_per_cm
                )
            else:
                # no swing phase!
                step_height = 0

            # A minimum of zero retains zero-height dragging steps. A positive
            # user-selected minimum must be honored, rather than ignored.
            include_stride = (
                (stride_len_cm >= stride_length_min_cm)
                and (stride_len_cm <= stride_length_max_cm)
                and (step_height >= step_height_min_cm)
                and (step_height <= step_height_max_cm)
            )
            rejection_reasons = []
            if not np.isfinite(stride_len_cm) or not np.isfinite(step_height):
                rejection_reasons.append("non_finite_measurement")
            if stride_len_cm < stride_length_min_cm:
                rejection_reasons.append("stride_length_below_minimum")
            if stride_len_cm > stride_length_max_cm:
                rejection_reasons.append("stride_length_above_maximum")
            if step_height < 0:
                rejection_reasons.append("negative_step_height")
            if step_height < step_height_min_cm:
                rejection_reasons.append("step_height_below_minimum")
            if step_height > step_height_max_cm:
                rejection_reasons.append("step_height_above_maximum")
            intervals.append(
                {
                    "start_frame": int(starts[i]),
                    "end_frame": int(ends[i]),
                    "stride_length_cm": float(stride_len_cm) if np.isfinite(stride_len_cm) else None,
                    "step_height_cm": float(step_height) if np.isfinite(step_height) else None,
                    "retained": bool(include_stride),
                    "rejection_reasons": rejection_reasons,
                    "ends_at_recording_boundary": bool(ends[i] == len(pd_dataframe) - 1),
                }
            )
            if include_stride:
                starts_included.append(starts[i])
                ends_included.append(ends[i])

                limb_len_means.append(np.mean(limb_lens[starts[i] : ends[i]]) / pixels_per_cm)
                limb_len_maxs.append(limb_len_max)
                limb_len_mins.append(min(limb_lens[starts[i] : ends[i]]) / pixels_per_cm)
                limb_len_sds.append(np.std(limb_lens[starts[i] : ends[i]]) / pixels_per_cm)

                cycle_dur_secs.append(cycle_dur_frame / frame_rate)
                cycle_dur_frames.append(cycle_dur_frame)

                stride_lens.append(stride_len_cm)

                step_heights.append(step_height)

                cycle_vs.append(cycle_v / pixels_per_cm)  # (px/s) / (px/cm) = cm/s
                # or use averaged v from euclidean distance between every two frames?
                # (that would consider the entire trajectory of a stride, including vertical movement / lift,
                # not just the distance between start and end point)

                stance_dur_secs.append(stance_dur_frame / frame_rate)
                swing_dur_secs.append(swing_dur_sec)
                swing_percentages.append(swing_perc)
                stance_percentages.append(stance_perc)

                if stance_dur_frame == cycle_dur_frame:
                    max_v_during_swings.append(np.nan)
                else:
                    max_v_during_swings.append(max(velocities[starts[i] : ends[i]]) / pixels_per_cm)

                mtp_joint_extension = max(angles_toe_mtp_ankle[starts[i] : ends[i]])
                ankle_joint_extension = max(angles_mtp_ankle_knee[starts[i] : ends[i]])
                knee_joint_extension = max(angles_ankle_knee_hip[starts[i] : ends[i]])
                hip_joint_extension = max(angles_knee_hip_crest[starts[i] : ends[i]])

                mtp_joint_flexion = min(angles_toe_mtp_ankle[starts[i] : ends[i]])
                ankle_joint_flexion = min(angles_mtp_ankle_knee[starts[i] : ends[i]])
                knee_joint_flexion = min(angles_ankle_knee_hip[starts[i] : ends[i]])
                hip_joint_flexion = min(angles_knee_hip_crest[starts[i] : ends[i]])

                mtp_joint_amplitude = mtp_joint_extension - mtp_joint_flexion
                ankle_joint_amplitude = ankle_joint_extension - ankle_joint_flexion
                knee_joint_amplitude = knee_joint_extension - knee_joint_flexion
                hip_joint_amplitude = hip_joint_extension - hip_joint_flexion

                mtp_joint_sds.append(np.std(angles_toe_mtp_ankle[starts[i] : ends[i]]))
                ankle_joint_sds.append(np.std(angles_mtp_ankle_knee[starts[i] : ends[i]]))
                knee_joint_sds.append(np.std(angles_ankle_knee_hip[starts[i] : ends[i]]))
                hip_joint_sds.append(np.std(angles_knee_hip_crest[starts[i] : ends[i]]))

                mtp_joint_extensions.append(mtp_joint_extension)
                mtp_joint_flexions.append(mtp_joint_flexion)
                mtp_joint_amplitudes.append(mtp_joint_amplitude)

                ankle_joint_extensions.append(ankle_joint_extension)
                ankle_joint_flexions.append(ankle_joint_flexion)
                ankle_joint_amplitudes.append(ankle_joint_amplitude)

                knee_joint_extensions.append(knee_joint_extension)
                knee_joint_flexions.append(knee_joint_flexion)
                knee_joint_amplitudes.append(knee_joint_amplitude)

                hip_joint_extensions.append(hip_joint_extension)
                hip_joint_flexions.append(hip_joint_flexion)
                hip_joint_amplitudes.append(hip_joint_amplitude)

                drag_clearance_px = drag_clearance_cm * pixels_per_cm
                drag, drag_percent, drag_mask = find_drag(
                    smooth_toe_y,
                    stance_dur_frame,
                    treadmill_y,
                    starts[i],
                    ends[i],
                    drag_clearance_px,
                    drag_min_consecutive_frames,
                )
                drag_ts.append(drag / frame_rate)
                drag_masks.append(drag_mask)
                if swing_dur_sec and stance_dur_frame > 0:
                    drag_percentages.append((drag / frame_rate) / swing_dur_sec)
                elif swing_dur_sec and stance_dur_frame == 0:
                    drag_percentages.append(np.nan)
                else:
                    # no swing phase detected!
                    drag_percentages.append(1)

            else:
                cycle_dur_secs.append(np.nan)
                cycle_dur_frames.append(np.nan)
                stride_lens.append(np.nan)
                cycle_vs.append(np.nan)
                stance_dur_secs.append(np.nan)
                swing_dur_secs.append(np.nan)
                swing_percentages.append(np.nan)
                stance_percentages.append(np.nan)
                limb_len_means.append(np.nan)
                limb_len_maxs.append(np.nan)
                limb_len_mins.append(np.nan)
                limb_len_sds.append(np.nan)
                step_heights.append(np.nan)
                max_v_during_swings.append(np.nan)
                mtp_joint_extensions.append(np.nan)
                mtp_joint_flexions.append(np.nan)
                mtp_joint_amplitudes.append(np.nan)
                ankle_joint_extensions.append(np.nan)
                ankle_joint_flexions.append(np.nan)
                ankle_joint_amplitudes.append(np.nan)
                knee_joint_extensions.append(np.nan)
                knee_joint_flexions.append(np.nan)
                knee_joint_amplitudes.append(np.nan)
                hip_joint_extensions.append(np.nan)
                hip_joint_flexions.append(np.nan)
                hip_joint_amplitudes.append(np.nan)
                mtp_joint_sds.append(np.nan)
                ankle_joint_sds.append(np.nan)
                knee_joint_sds.append(np.nan)
                hip_joint_sds.append(np.nan)
                drag_ts.append(np.nan)
                drag_percentages.append(np.nan)
                drag_masks.append(np.array([]))

        starts_included = np.array(starts_included)
        ends_included = np.array(ends_included)

        for i in range(len(starts)):
            if starts[i] not in starts_included:
                dtw_x_plane_5_means.append(np.nan)
                dtw_x_plane_5_sds.append(np.nan)
                dtw_y_plane_5_means.append(np.nan)
                dtw_y_plane_5_sds.append(np.nan)
                dtw_xy_plane_5_means.append(np.nan)
                dtw_xy_plane_5_sds.append(np.nan)
                dtw_x_plane_10_means.append(np.nan)
                dtw_x_plane_10_sds.append(np.nan)
                dtw_y_plane_10_means.append(np.nan)
                dtw_y_plane_10_sds.append(np.nan)
                dtw_xy_plane_10_means.append(np.nan)
                dtw_xy_plane_10_sds.append(np.nan)

            else:
                included_index = int(np.array(np.where(starts[i] == starts_included)[0]).item())

                if included_index <= len(starts_included) - 5:
                    toe_xs = parse_stride_lists(smooth_toe_x, starts_included, ends_included, included_index, 5, True)
                    pairwise_dtw_res_x_5 = pairwise_dtw(toe_xs)
                    dtw_x_plane_5_mean = np.mean(pairwise_dtw_res_x_5)
                    dtw_x_plane_5_sd = np.std(pairwise_dtw_res_x_5)

                    toe_ys = parse_stride_lists(smooth_toe_y, starts_included, ends_included, included_index, 5, True)
                    pairwise_dtw_res_y_5 = pairwise_dtw(toe_ys)
                    dtw_y_plane_5_mean = np.mean(pairwise_dtw_res_y_5)
                    dtw_y_plane_5_sd = np.std(pairwise_dtw_res_y_5)

                    toe_xys = [np.append(toe_xs[j], toe_ys[j]).reshape(2, -1).T for j in range(5)]
                    pairwise_dtw_res_xy_5 = pairwise_dtw(toe_xys)
                    dtw_xy_plane_5_mean = np.mean(pairwise_dtw_res_xy_5)
                    dtw_xy_plane_5_sd = np.std(pairwise_dtw_res_xy_5)

                    if included_index <= len(starts_included) - 10:
                        toe_xs = parse_stride_lists(
                            smooth_toe_x, starts_included, ends_included, included_index, 10, True
                        )
                        pairwise_dtw_res_x_10 = pairwise_dtw(toe_xs)
                        dtw_x_plane_10_mean = np.mean(pairwise_dtw_res_x_10)
                        dtw_x_plane_10_sd = np.std(pairwise_dtw_res_x_10)

                        toe_ys = parse_stride_lists(
                            smooth_toe_y, starts_included, ends_included, included_index, 10, True
                        )
                        pairwise_dtw_res_y_10 = pairwise_dtw(toe_ys)
                        dtw_y_plane_10_mean = np.mean(pairwise_dtw_res_y_10)
                        dtw_y_plane_10_sd = np.std(pairwise_dtw_res_y_10)

                        toe_xys = [np.append(toe_xs[j], toe_ys[j]).reshape(2, -1).T for j in range(10)]
                        pairwise_dtw_res_xy_10 = pairwise_dtw(toe_xys)
                        dtw_xy_plane_10_mean = np.mean(pairwise_dtw_res_xy_10)
                        dtw_xy_plane_10_sd = np.std(pairwise_dtw_res_xy_10)

                        dtw_x_plane_10_means.append(dtw_x_plane_10_mean)
                        dtw_x_plane_10_sds.append(dtw_x_plane_10_sd)
                        dtw_y_plane_10_means.append(dtw_y_plane_10_mean)
                        dtw_y_plane_10_sds.append(dtw_y_plane_10_sd)
                        dtw_xy_plane_10_means.append(dtw_xy_plane_10_mean)
                        dtw_xy_plane_10_sds.append(dtw_xy_plane_10_sd)
                    else:
                        dtw_x_plane_10_means.append(np.nan)
                        dtw_x_plane_10_sds.append(np.nan)
                        dtw_y_plane_10_means.append(np.nan)
                        dtw_y_plane_10_sds.append(np.nan)
                        dtw_xy_plane_10_means.append(np.nan)
                        dtw_xy_plane_10_sds.append(np.nan)

                    dtw_x_plane_5_means.append(dtw_x_plane_5_mean)
                    dtw_x_plane_5_sds.append(dtw_x_plane_5_sd)
                    dtw_y_plane_5_means.append(dtw_y_plane_5_mean)
                    dtw_y_plane_5_sds.append(dtw_y_plane_5_sd)
                    dtw_xy_plane_5_means.append(dtw_xy_plane_5_mean)
                    dtw_xy_plane_5_sds.append(dtw_xy_plane_5_sd)

                else:
                    dtw_x_plane_5_means.append(np.nan)
                    dtw_x_plane_5_sds.append(np.nan)
                    dtw_y_plane_5_means.append(np.nan)
                    dtw_y_plane_5_sds.append(np.nan)
                    dtw_xy_plane_5_means.append(np.nan)
                    dtw_xy_plane_5_sds.append(np.nan)
                    dtw_x_plane_10_means.append(np.nan)
                    dtw_x_plane_10_sds.append(np.nan)
                    dtw_y_plane_10_means.append(np.nan)
                    dtw_y_plane_10_sds.append(np.nan)
                    dtw_xy_plane_10_means.append(np.nan)
                    dtw_xy_plane_10_sds.append(np.nan)

        for bodypart in bodyparts:
            for coord in ["x", "y"]:
                pd_dataframe[f"{bodypart} {coord}"] = butterworth_filter(
                    pd_dataframe[f"{bodypart} {coord}"], frame_rate, cutoff_f
                )

        return (
            pd.DataFrame(
                data=np.array(
                    [
                        starts,
                        ends,
                        cycle_dur_secs,
                        cycle_dur_frames,
                        cycle_vs,
                        stride_lens,
                        stance_dur_secs,
                        swing_dur_secs,
                        swing_percentages,
                        stance_percentages,
                        limb_len_means,
                        limb_len_maxs,
                        limb_len_mins,
                        limb_len_sds,
                        step_heights,
                        max_v_during_swings,
                        mtp_joint_extensions,
                        mtp_joint_flexions,
                        mtp_joint_amplitudes,
                        mtp_joint_sds,
                        ankle_joint_extensions,
                        ankle_joint_flexions,
                        ankle_joint_amplitudes,
                        ankle_joint_sds,
                        knee_joint_extensions,
                        knee_joint_flexions,
                        knee_joint_amplitudes,
                        knee_joint_sds,
                        hip_joint_extensions,
                        hip_joint_flexions,
                        hip_joint_amplitudes,
                        hip_joint_sds,
                        drag_ts,
                        drag_percentages,
                        dtw_x_plane_5_means,
                        dtw_x_plane_5_sds,
                        dtw_y_plane_5_means,
                        dtw_y_plane_5_sds,
                        dtw_xy_plane_5_means,
                        dtw_xy_plane_5_sds,
                        dtw_x_plane_10_means,
                        dtw_x_plane_10_sds,
                        dtw_y_plane_10_means,
                        dtw_y_plane_10_sds,
                        dtw_xy_plane_10_means,
                        dtw_xy_plane_10_sds,
                    ]
                ).T,
                columns=[
                    "stride_start (frame)",
                    "stride_end (frame)",
                    "cycle duration (s)",
                    "cycle duration (no. frames)",
                    "cycle velocity (cm/s)",
                    "stride length (cm)",
                    "stance duration (s)",
                    "swing duration (s)",
                    "swing percentage (%)",
                    "stance percentage (%)",
                    "mean toe-to-crest distance (cm)",
                    "max toe-to-crest distance (cm)",
                    "min toe-to-crest distance (cm)",
                    "toe-to-crest distance SD (cm)",
                    "step height (cm)",
                    "max velocity during swing (cm/s)",
                    "mtp joint extension (deg)",
                    "mtp joint flexion (deg)",
                    "mtp joint amplitude (deg)",
                    "mtp joint SD (deg)",
                    "ankle joint extension (deg)",
                    "ankle joint flexion (deg)",
                    "ankle joint amplitude (deg)",
                    "ankle joint SD (deg)",
                    "knee joint extension (deg)",
                    "knee joint flexion (deg)",
                    "knee joint amplitude (deg)",
                    "knee joint SD (deg)",
                    "hip joint extension (deg)",
                    "hip joint flexion (deg)",
                    "hip joint amplitude (deg)",
                    "hip joint SD (deg)",
                    "drag duration (s)",
                    "drag percentage (%)",
                    "Variability x plane 5 strides mean",
                    "Variability x plane 5 strides SD",
                    "Variability y plane 5 strides mean",
                    "Variability y plane 5 strides SD",
                    "Variability xy plane 5 strides mean",
                    "Variability xy plane 5 strides SD",
                    "Variability x plane 10 strides mean",
                    "Variability x plane 10 strides SD",
                    "Variability y plane 10 strides mean",
                    "Variability y plane 10 strides SD",
                    "Variability xy plane 10 strides mean",
                    "Variability xy plane 10 strides SD",
                ],
            ),
            pd_dataframe,
            is_stance,
            bodyparts,
            drag_masks,
            starts,
        )
