"""Assemble spontaneous-walking cycle measurements without altering canonical cycle boundaries."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_cycle_quality import (
    dragging_dominates_recording,
    spontaneous_cycle_accepted,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_drag_detection import find_drag
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_joint_kinematics import (
    find_angles,
    find_limb_length,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_spontaneous_cycles import (
    robust_stance_segments_from_toe as _robust_stance_segments_from_toe,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_stride_measurements import (
    find_euclidean_speed,
    find_stride_len,
    find_swing_stance_from_mask,
    pairwise_dtw,
    parse_stride_lists,
)


def extract_spontaneous_parameters(
    frame_rate,
    pd_dataframe,
    cutoff_f,
    pixels_per_cm=49.143,
    no_outlier_filter=False,
    dragging_filter=False,
    step_height_min_cm=0.0,
    step_height_max_cm=1.5,
    stride_length_min_cm=0.0,
    stride_length_max_cm=8.0,
    drag_clearance_cm=0.3,
    drag_min_consecutive_frames=4,
    right_to_left="auto",
    stride_detector=None,
):
    """
    pd_dataframe: contains raw coordinates (not adjusted for treadmill movement, unfiltered)
    bodypart: which bodypart to use for stride estimation
    """
    bodyparts = ["toe", "mtp", "ankle", "knee", "hip", "iliac crest"]
    drag_masks_left = []
    drag_masks_right = []
    starts_all = []
    ends_all = []
    limbs = []
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
    dtw_x_plane_5_means = []
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
    is_stances = []
    for direction in ["L", "R", ""]:
        if f"toe{direction} x" in pd_dataframe.columns:
            smooth_toe_x = butterworth_filter(pd_dataframe[f"toe{direction} x"], frame_rate, cutoff_f)
            smooth_mtp_x = butterworth_filter(pd_dataframe[f"mtp{direction} x"], frame_rate, cutoff_f)
            smooth_ankle_x = butterworth_filter(pd_dataframe[f"ankle{direction} x"], frame_rate, cutoff_f)
            smooth_knee_x = butterworth_filter(pd_dataframe[f"knee{direction} x"], frame_rate, cutoff_f)
            smooth_hip_x = butterworth_filter(pd_dataframe[f"hip{direction} x"], frame_rate, cutoff_f)
            smooth_crest_x = butterworth_filter(pd_dataframe[f"iliac crest{direction} x"], frame_rate, cutoff_f)
            smooth_toe_y = butterworth_filter(pd_dataframe[f"toe{direction} y"], frame_rate, cutoff_f)
            smooth_mtp_y = butterworth_filter(pd_dataframe[f"mtp{direction} y"], frame_rate, cutoff_f)
            smooth_ankle_y = butterworth_filter(pd_dataframe[f"ankle{direction} y"], frame_rate, cutoff_f)
            smooth_knee_y = butterworth_filter(pd_dataframe[f"knee{direction} y"], frame_rate, cutoff_f)
            smooth_hip_y = butterworth_filter(pd_dataframe[f"hip{direction} y"], frame_rate, cutoff_f)
            smooth_crest_y = butterworth_filter(pd_dataframe[f"iliac crest{direction} y"], frame_rate, cutoff_f)
            angles_toe_mtp_ankle = find_angles(
                smooth_toe_x, smooth_toe_y, smooth_mtp_x, smooth_mtp_y, smooth_ankle_x, smooth_ankle_y
            )
            angles_mtp_ankle_knee = find_angles(
                smooth_mtp_x, smooth_mtp_y, smooth_ankle_x, smooth_ankle_y, smooth_knee_x, smooth_knee_y
            )
            angles_ankle_knee_hip = find_angles(
                smooth_ankle_x, smooth_ankle_y, smooth_knee_x, smooth_knee_y, smooth_hip_x, smooth_hip_y
            )
            angles_knee_hip_crest = find_angles(
                smooth_knee_x, smooth_knee_y, smooth_hip_x, smooth_hip_y, smooth_crest_x, smooth_crest_y
            )
            elevation_angles = find_angles(
                smooth_mtp_x,
                smooth_mtp_y,
                smooth_crest_x,
                smooth_crest_y,
                smooth_crest_x,
                np.zeros(len(smooth_crest_y)),
            )
            elevation_angle_change = np.diff(elevation_angles)
            limb_lens = find_limb_length(smooth_toe_x, smooth_toe_y, smooth_hip_x, smooth_hip_y)
            velocities = find_euclidean_speed(smooth_toe_x, smooth_toe_y, frame_rate)
            if stride_detector is None and dragging_filter and dragging_dominates_recording(elevation_angle_change, np):
                limbs.append(direction)
                starts_all.append(np.nan)
                ends_all.append(np.nan)
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
                is_stances.append(np.nan)
            else:
                starts = []
                ends = []
                detector = stride_detector or _robust_stance_segments_from_toe
                (is_stance, starts, ends, treadmill_y) = detector(
                    smooth_toe_x, smooth_toe_y, pd_dataframe[f"toe{direction} likelihood"], frame_rate
                )
                starts_all.extend(starts)
                ends_all.extend(ends)
                is_stances.append(is_stance)
                if not np.isfinite(treadmill_y):
                    treadmill_y = float(np.nanmedian(smooth_toe_y))
                starts_included = []
                ends_included = []
                for i in range(len(starts)):
                    limbs.append(direction)
                    stride_len = abs(find_stride_len(smooth_toe_x, starts[i], ends[i]))
                    stride_len_cm = stride_len / pixels_per_cm
                    limb_len_max = max(limb_lens[starts[i] : ends[i]]) / pixels_per_cm
                    cycle_dur_frame = ends[i] - starts[i]
                    cycle_v = stride_len_cm / cycle_dur_frame * frame_rate
                    (stance_dur_frame, swing_perc, stance_perc) = find_swing_stance_from_mask(
                        is_stance, starts[i], ends[i], elevation_angle_change
                    )
                    swing_dur_sec = (cycle_dur_frame - stance_dur_frame) / frame_rate
                    if swing_dur_sec and stance_dur_frame > 0:
                        step_height = (
                            -(min(smooth_toe_y[starts[i] : ends[i]]) - max(smooth_toe_y[starts[i] : ends[i]]))
                            / pixels_per_cm
                        )
                    elif swing_dur_sec and stance_dur_frame == 0:
                        step_height = (
                            -(min(smooth_toe_y[starts[i] + stance_dur_frame : ends[i]]) - smooth_toe_y[starts[i]])
                            / pixels_per_cm
                        )
                    else:
                        step_height = 0
                    if spontaneous_cycle_accepted(
                        stride_len_cm,
                        step_height,
                        stride_length_min_cm,
                        stride_length_max_cm,
                        step_height_min_cm,
                        step_height_max_cm,
                        no_outlier_filter,
                    ):
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
                        cycle_vs.append(cycle_v)
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
                        (drag, drag_percent, drag_mask) = find_drag(
                            smooth_toe_y,
                            stance_dur_frame,
                            treadmill_y,
                            starts[i],
                            ends[i],
                            drag_clearance_px,
                            drag_min_consecutive_frames,
                        )
                        drag_ts.append(drag / frame_rate)
                        if direction == "L":
                            drag_masks_left.append(drag_mask)
                        elif direction == "R":
                            drag_masks_right.append(drag_mask)
                        if swing_dur_sec and stance_dur_frame > 0:
                            drag_percentages.append(drag / frame_rate / swing_dur_sec)
                        elif swing_dur_sec and stance_dur_frame == 0:
                            drag_percentages.append(np.nan)
                        else:
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
                    included_index = int(np.where(starts[i] == starts_included)[0].item())
                    if included_index <= len(starts_included) - 5:
                        toe_xs = parse_stride_lists(
                            smooth_toe_x, starts_included, ends_included, included_index, 5, True
                        )
                        pairwise_dtw_res_x_5 = pairwise_dtw(toe_xs)
                        dtw_x_plane_5_mean = np.mean(pairwise_dtw_res_x_5)
                        dtw_x_plane_5_sd = np.std(pairwise_dtw_res_x_5)
                        toe_ys = parse_stride_lists(
                            smooth_toe_y, starts_included, ends_included, included_index, 5, True
                        )
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
        else:
            pass
    # Empty recordings use the same six-value result and column schema as detected cycles.
    all_lists = [
        starts_all,
        ends_all,
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
    max_len = max(len(lst) for lst in all_lists)

    def pad_list(lst, target_len, pad_value=np.nan):
        return lst + [pad_value] * (target_len - len(lst))

    limbs = pad_list(limbs, max_len, "")
    starts_all = pad_list(starts_all, max_len)
    ends_all = pad_list(ends_all, max_len)
    cycle_dur_secs = pad_list(cycle_dur_secs, max_len)
    cycle_dur_frames = pad_list(cycle_dur_frames, max_len)
    cycle_vs = pad_list(cycle_vs, max_len)
    stride_lens = pad_list(stride_lens, max_len)
    stance_dur_secs = pad_list(stance_dur_secs, max_len)
    swing_dur_secs = pad_list(swing_dur_secs, max_len)
    swing_percentages = pad_list(swing_percentages, max_len)
    stance_percentages = pad_list(stance_percentages, max_len)
    limb_len_means = pad_list(limb_len_means, max_len)
    limb_len_maxs = pad_list(limb_len_maxs, max_len)
    limb_len_mins = pad_list(limb_len_mins, max_len)
    limb_len_sds = pad_list(limb_len_sds, max_len)
    step_heights = pad_list(step_heights, max_len)
    max_v_during_swings = pad_list(max_v_during_swings, max_len)
    mtp_joint_extensions = pad_list(mtp_joint_extensions, max_len)
    mtp_joint_flexions = pad_list(mtp_joint_flexions, max_len)
    mtp_joint_amplitudes = pad_list(mtp_joint_amplitudes, max_len)
    mtp_joint_sds = pad_list(mtp_joint_sds, max_len)
    ankle_joint_extensions = pad_list(ankle_joint_extensions, max_len)
    ankle_joint_flexions = pad_list(ankle_joint_flexions, max_len)
    ankle_joint_amplitudes = pad_list(ankle_joint_amplitudes, max_len)
    ankle_joint_sds = pad_list(ankle_joint_sds, max_len)
    knee_joint_extensions = pad_list(knee_joint_extensions, max_len)
    knee_joint_flexions = pad_list(knee_joint_flexions, max_len)
    knee_joint_amplitudes = pad_list(knee_joint_amplitudes, max_len)
    knee_joint_sds = pad_list(knee_joint_sds, max_len)
    hip_joint_extensions = pad_list(hip_joint_extensions, max_len)
    hip_joint_flexions = pad_list(hip_joint_flexions, max_len)
    hip_joint_amplitudes = pad_list(hip_joint_amplitudes, max_len)
    hip_joint_sds = pad_list(hip_joint_sds, max_len)
    drag_ts = pad_list(drag_ts, max_len)
    drag_percentages = pad_list(drag_percentages, max_len)
    dtw_x_plane_5_means = pad_list(dtw_x_plane_5_means, max_len)
    dtw_x_plane_5_sds = pad_list(dtw_x_plane_5_sds, max_len)
    dtw_y_plane_5_means = pad_list(dtw_y_plane_5_means, max_len)
    dtw_y_plane_5_sds = pad_list(dtw_y_plane_5_sds, max_len)
    dtw_xy_plane_5_means = pad_list(dtw_xy_plane_5_means, max_len)
    dtw_xy_plane_5_sds = pad_list(dtw_xy_plane_5_sds, max_len)
    dtw_x_plane_10_means = pad_list(dtw_x_plane_10_means, max_len)
    dtw_x_plane_10_sds = pad_list(dtw_x_plane_10_sds, max_len)
    dtw_y_plane_10_means = pad_list(dtw_y_plane_10_means, max_len)
    dtw_y_plane_10_sds = pad_list(dtw_y_plane_10_sds, max_len)
    dtw_xy_plane_10_means = pad_list(dtw_xy_plane_10_means, max_len)
    dtw_xy_plane_10_sds = pad_list(dtw_xy_plane_10_sds, max_len)
    return (
        pd.DataFrame(
            data=np.array(
                [
                    limbs,
                    starts_all,
                    ends_all,
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
                "limb (hind left / right)",
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
        np.array(is_stances).reshape(-1),
        bodyparts,
        None,
        None,
    )
