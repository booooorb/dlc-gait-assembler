"""Detect treadmill stance intervals and canonical cycle boundaries."""

from __future__ import annotations

import numpy as np
from sklearn.mixture import GaussianMixture

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_stride_measurements import find_euclidean_speed


def robust_stance_segments_treadmill(pd_dataframe, frame_rate, cutoff_f, right_to_left):
    toe_x_raw = pd_dataframe["toe x"]
    toe_y_raw = pd_dataframe["toe y"]
    toe_lik = pd_dataframe["toe likelihood"]
    smooth_toe_x = butterworth_filter(toe_x_raw, frame_rate, cutoff_f)
    smooth_toe_y = butterworth_filter(toe_y_raw, frame_rate, cutoff_f)
    x_change = np.diff(smooth_toe_x)
    if right_to_left:
        dom = x_change >= 0
    else:
        dom = x_change <= 0
    speed = np.array(find_euclidean_speed(smooth_toe_x, smooth_toe_y, frame_rate))
    lik = np.array(toe_lik[1:])
    toe_y = np.array(smooth_toe_y[1:])
    y_valid = pd_dataframe["toe y"][pd_dataframe["toe likelihood"] > 0.5]
    y_filt = y_valid[
        (y_valid < np.mean(y_valid) + 1 * np.std(y_valid)) & (y_valid > np.mean(y_valid) - 1 * np.std(y_valid))
    ]
    (_, b) = np.histogram(y_filt, bins=100, density=True)
    gm = GaussianMixture(n_components=2, random_state=0).fit(np.array(b).reshape(-1, 1))
    stance_threshold = max(gm.means_).item()
    ind_stance_gaussian = np.argmax(gm.means_)
    treadmill_y = float(stance_threshold + np.sqrt(gm.covariances_[ind_stance_gaussian].item()))
    y_contact = toe_y > treadmill_y
    lik_good = lik > 0.6
    p35 = np.percentile(speed, 35)
    p65 = np.percentile(speed, 65)
    low_th = min(p35, p65)
    high_th = max(p35, p65)
    if high_th <= low_th:
        high_th = low_th * 1.2 + 0.001
    n = len(speed)
    is_stance = [False] * n
    prev = dom[0] and speed[0] <= high_th and (not lik_good[0] or y_contact[0])
    is_stance[0] = prev
    for t in range(1, n):
        if not lik_good[t]:
            is_stance[t] = prev
        elif speed[t] <= low_th and dom[t] and (y_contact[t] or speed[t] <= low_th * 0.8):
            is_stance[t] = True
        elif speed[t] >= high_th:
            is_stance[t] = False
        else:
            is_stance[t] = prev
        prev = is_stance[t]
    cleaned = is_stance[:]
    run_start = 0
    for t in range(1, n + 1):
        if t == n or is_stance[t] != is_stance[t - 1]:
            run_len = t - run_start
            if run_len < 3:
                fill = is_stance[t] if t < n else is_stance[run_start - 1] if run_start > 0 else False
                for k in range(run_start, t):
                    cleaned[k] = fill
            run_start = t
    is_stance = cleaned
    starts = []
    ends = []
    for i in range(1, len(is_stance)):
        if is_stance[i] and (not is_stance[i - 1]):
            starts.append(i)
    for i in range(1, len(starts)):
        ends.append(starts[i] - 1)
    ends.append(len(is_stance))
    return (is_stance, starts, ends, treadmill_y)
