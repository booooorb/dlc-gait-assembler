"""Detect spontaneous walking stance, swing, and dragging cycle boundaries."""

from __future__ import annotations

import math

import numpy as np
from sklearn.mixture import GaussianMixture

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter


def toe_contact_threshold(toe_y, toe_likelihood=None, likelihood_min=0.5):
    toe_y = np.asarray(toe_y, dtype=float)
    if toe_likelihood is None:
        toe_likelihood = np.ones(len(toe_y), dtype=float)
    else:
        toe_likelihood = np.asarray(toe_likelihood, dtype=float)
    n = min(len(toe_y), len(toe_likelihood))
    toe_y = toe_y[:n]
    toe_likelihood = toe_likelihood[:n]
    valid = np.isfinite(toe_y) & np.isfinite(toe_likelihood) & (toe_likelihood > likelihood_min)
    y_valid = toe_y[valid]
    if len(y_valid) < 6:
        y_valid = toe_y[np.isfinite(toe_y)]
    if len(y_valid) == 0:
        return (np.nan, np.nan)
    if len(y_valid) >= 8 and np.nanstd(y_valid) > 1e-06:
        try:
            gm = GaussianMixture(n_components=2, random_state=0).fit(y_valid.reshape(-1, 1))
            means = gm.means_.reshape(-1)
            ground_index = int(np.argmax(means))
            air_index = 1 - ground_index
            contact_threshold = float((means[ground_index] + means[air_index]) / 2)
            ground_sd = math.sqrt(float(gm.covariances_[ground_index].reshape(-1)[0]))
            return (contact_threshold, float(means[ground_index] + ground_sd))
        except ValueError:
            pass
    return (float(np.nanpercentile(y_valid, 60)), float(np.nanpercentile(y_valid, 90)))


def clean_short_boolean_runs(mask, min_run_frames=3):
    cleaned = [bool(value) for value in mask]
    if len(cleaned) < min_run_frames or min_run_frames <= 1:
        return cleaned
    run_start = 0
    for t in range(1, len(cleaned) + 1):
        if t == len(cleaned) or cleaned[t] != cleaned[t - 1]:
            run_len = t - run_start
            if run_len < min_run_frames:
                prev_value = cleaned[run_start - 1] if run_start > 0 else None
                next_value = cleaned[t] if t < len(cleaned) else None
                fill_value = prev_value if prev_value is not None else next_value
                if fill_value is not None:
                    for k in range(run_start, t):
                        cleaned[k] = fill_value
            run_start = t
    return cleaned


def robust_stance_segments_from_toe(toe_x, toe_y, toe_likelihood, frame_rate, likelihood_min=0.5, min_run_frames=3):
    toe_x = np.asarray(toe_x, dtype=float)
    toe_y = np.asarray(toe_y, dtype=float)
    toe_likelihood = np.asarray(toe_likelihood, dtype=float)
    n = min(len(toe_x), len(toe_y), len(toe_likelihood))
    toe_x = toe_x[:n]
    toe_y = toe_y[:n]
    toe_likelihood = toe_likelihood[:n]
    if n < 2:
        return ([], [], [], np.nan)
    speed = np.sqrt(np.diff(toe_x) ** 2 + np.diff(toe_y) ** 2) * frame_rate
    aligned_y = toe_y[1:]
    aligned_likelihood = toe_likelihood[1:]
    (contact_threshold, ground_y) = toe_contact_threshold(toe_y, toe_likelihood, likelihood_min)
    if np.isfinite(contact_threshold):
        toe_in_contact = aligned_y >= contact_threshold
    else:
        toe_in_contact = np.ones(len(speed), dtype=bool)
    finite_speed = np.isfinite(speed)
    good_likelihood = np.isfinite(aligned_likelihood) & (aligned_likelihood > likelihood_min)
    threshold_values = speed[finite_speed & good_likelihood]
    if len(threshold_values) < 4:
        threshold_values = speed[finite_speed]
    if len(threshold_values) == 0:
        return ([False] * len(speed), [], [], ground_y)
    low_speed = float(np.nanpercentile(threshold_values, 35))
    high_speed = float(np.nanpercentile(threshold_values, 70))
    if high_speed <= low_speed:
        high_speed = low_speed * 1.25 + 1e-06
    is_stance = [False] * len(speed)
    previous = bool(toe_in_contact[0] and speed[0] <= high_speed) if finite_speed[0] else False
    is_stance[0] = previous
    for t in range(1, len(speed)):
        if not finite_speed[t] or not good_likelihood[t]:
            current = previous
        elif toe_in_contact[t] and speed[t] <= low_speed:
            current = True
        elif toe_in_contact[t] and previous and (speed[t] <= high_speed):
            current = True
        elif not toe_in_contact[t] and speed[t] >= low_speed or speed[t] >= high_speed:
            current = False
        else:
            current = previous
        is_stance[t] = current
        previous = current
    is_stance = clean_short_boolean_runs(is_stance, min_run_frames)
    if not any(is_stance) or all(is_stance):
        return (is_stance, [], [], ground_y)
    starts = []
    if is_stance[0]:
        starts.append(0)
    for i in range(1, len(is_stance)):
        if is_stance[i] and (not is_stance[i - 1]):
            starts.append(i)
    ends = []
    for i in range(1, len(starts)):
        ends.append(starts[i] - 1)
    if starts:
        ends.append(len(is_stance))
    return (is_stance, starts, ends, ground_y)


def detect_dragging_movement_cycles(pd_dataframe, frame_rate, cutoff_f, right_to_left):
    """
    Alternative stride detection for dragging mice based on forward movement cycles.
    Instead of detecting stance/swing phases, detect forward movement cycles.
    """
    bodypart = "toe"
    x_coords = pd_dataframe[f"{bodypart} x"][pd_dataframe[f"{bodypart} likelihood"] > 0.5]
    x_change = np.diff(x_coords)
    x_change_smooth = butterworth_filter(np.concatenate([[0], x_change]), frame_rate, cutoff_f)
    zero_crossings = []
    for i in range(1, len(x_change_smooth)):
        if (
            x_change_smooth[i - 1] <= 0
            and x_change_smooth[i] > 0
            or (x_change_smooth[i - 1] >= 0 and x_change_smooth[i] < 0)
        ):
            zero_crossings.append(i)
    starts = []
    ends = []
    is_stance = [0] * len(pd_dataframe)
    if len(zero_crossings) >= 2:
        for i in range(0, len(zero_crossings) - 1, 2):
            if i + 1 < len(zero_crossings):
                start_idx = zero_crossings[i]
                end_idx = zero_crossings[i + 1]
                cycle_movement = np.sum(x_change_smooth[start_idx:end_idx])
                if cycle_movement > 5:
                    starts.append(start_idx)
                    ends.append(end_idx)
                    for j in range(start_idx, min(end_idx, len(is_stance))):
                        is_stance[j] = 1
    y_coords = pd_dataframe[f"{bodypart} y"][pd_dataframe[f"{bodypart} likelihood"] > 0.5]
    treadmill_y = np.median(y_coords) if len(y_coords) > 0 else 0
    return (is_stance, starts, ends, treadmill_y)
