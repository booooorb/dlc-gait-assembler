"""Calculate stride length, stance/swing durations, speed, and established trajectory comparisons."""

from __future__ import annotations

import numpy as np


def find_stride_len(toe_x, start, end):
    """
    difference between the starting and ending x-axis position of toe
    (in pixels)
    """
    return toe_x[end] - toe_x[start]


def find_swing_stance(elevation_angle_change, start, end):
    """
    return stance duration in frames, swing duration, stance duration
    """
    try:
        stance_dur = np.where(np.diff(np.sign(elevation_angle_change[start:end])) > 0)[0][0]
    except IndexError:
        stance_dur = end - start
    return (stance_dur, (end - start - stance_dur) / (end - start), stance_dur / (end - start))


def find_swing_stance_from_mask(is_stance, start, end, elevation_angle_change=None):
    cycle_dur = max(end - start, 1)
    stance_slice = np.asarray(is_stance[start:end], dtype=bool)
    if len(stance_slice) > 0 and stance_slice[0]:
        swing_onsets = np.where(~stance_slice)[0]
        if len(swing_onsets) > 0:
            stance_dur = int(swing_onsets[0])
        else:
            stance_dur = len(stance_slice)
        return (stance_dur, (cycle_dur - stance_dur) / cycle_dur, stance_dur / cycle_dur)
    if elevation_angle_change is not None:
        return find_swing_stance(elevation_angle_change, start, end)
    return (cycle_dur, 0, 1)


def find_euclidean_speed(x, y, frame_rate):
    """
    calculate speed in pixel/s
    """
    loc_changes = []
    for i in range(1, len(x)):
        loc_changes.append(np.sqrt((x[i] - x[i - 1]) ** 2 + (y[i] - y[i - 1]) ** 2) * frame_rate)
    return loc_changes


def parse_stride_lists(x, starts, ends, first_stride, n, adjust=False):
    """
    reshapes a continuous time series of bodypart location x into a list of n strides,
    each starting at starts[n] and ending at ends[n], with the first stride in the new list
    starting at starts[first_stride]
    starts / ends: index of the stride start and endpoints to use for parsing continuous time series x
    first_stride: index of the first stride to extract, based on the starts and ends lists
    n: number of strides to extract from x
    returns a list of strides
    """
    results = [np.array(x[starts[i] : ends[i] + 1]) for i in range(first_stride, first_stride + n)]
    if adjust:
        for n_sublist in range(len(results)):
            centers = results[n_sublist][0]
            results[n_sublist] = np.array(results[n_sublist] - centers).flatten()
    return results


def pairwise_dtw(iterable):
    """
    calculates stride-to-stride variability using mean absolute difference
    iterable: a list / array of time series (endpoint paths of a number of strides)
    returns:
    variability_result: a list of pairwise normalized differences
    e.g., iterable = [stride_a, stride_b, stride_c]
    -> variability_result = [diff_ab, diff_ac, diff_bc]

    Note: Replaced DTW with simpler normalized difference metric for better compatibility
    """
    variability_result = []
    for i in range(len(iterable) - 1):
        for j in range(i + 1, len(iterable)):
            stride_i = np.array(iterable[i])
            stride_j = np.array(iterable[j])
            is_2d = len(stride_i.shape) > 1 and stride_i.shape[1] > 1
            if is_2d:
                len_i = stride_i.shape[0]
                len_j = stride_j.shape[0]
                if len_i == len_j:
                    diff = np.mean(np.sqrt(np.sum((stride_i - stride_j) ** 2, axis=1)))
                else:
                    common_len = max(len_i, len_j)
                    stride_i_interp = np.zeros((common_len, stride_i.shape[1]))
                    stride_j_interp = np.zeros((common_len, stride_j.shape[1]))
                    for dim in range(stride_i.shape[1]):
                        stride_i_interp[:, dim] = np.interp(
                            np.linspace(0, 1, common_len), np.linspace(0, 1, len_i), stride_i[:, dim]
                        )
                        stride_j_interp[:, dim] = np.interp(
                            np.linspace(0, 1, common_len), np.linspace(0, 1, len_j), stride_j[:, dim]
                        )
                    diff = np.mean(np.sqrt(np.sum((stride_i_interp - stride_j_interp) ** 2, axis=1)))
            else:
                len_i = len(stride_i)
                len_j = len(stride_j)
                if len_i == len_j:
                    diff = np.mean(np.abs(stride_i - stride_j))
                else:
                    common_len = max(len_i, len_j)
                    stride_i_interp = np.interp(
                        np.linspace(0, 1, common_len), np.linspace(0, 1, len_i), stride_i.flatten()
                    )
                    stride_j_interp = np.interp(
                        np.linspace(0, 1, common_len), np.linspace(0, 1, len_j), stride_j.flatten()
                    )
                    diff = np.mean(np.abs(stride_i_interp - stride_j_interp))
            variability_result.append(diff)
    return variability_result


def convert_to_binary(A):
    list_valid = [0 if np.isnan(i) else 1 for i in A]
    return list_valid
