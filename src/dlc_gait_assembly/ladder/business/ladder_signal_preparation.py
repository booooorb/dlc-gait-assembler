"""Prepare confidence-filtered paw signals and the detection baseline."""

from __future__ import annotations


def filter_predictions(peaks, properties, y, likelihood, likelihood_threshold, depth_threshold, np):
    """Faithful, bounds-safe port of ALMA ``filter_predictions``."""
    peaks = np.asarray(peaks, dtype=int)
    if len(peaks) == 0:
        empty = np.asarray([], dtype=int)
        return (empty, empty, empty)
    left_bases = np.asarray(properties["left_bases"], dtype=int).copy()
    right_bases = np.asarray(properties["right_bases"], dtype=int).copy()
    valid = [
        index
        for (index, peak) in enumerate(peaks)
        if np.isfinite(likelihood[peak]) and likelihood[peak] >= likelihood_threshold
    ]
    if not valid:
        empty = np.asarray([], dtype=int)
        return (empty, empty, empty)
    kept = [valid[0]]
    for valid_position, current_index in enumerate(valid[1:], start=1):
        previous_index = valid[valid_position - 1]
        previous_peak = int(peaks[previous_index])
        current_peak = int(peaks[current_index])
        between_positions = np.arange(previous_peak, current_peak, dtype=int)
        between_positions = between_positions[
            np.isfinite(y[between_positions]) & (likelihood[between_positions] >= likelihood_threshold)
        ]
        if len(between_positions):
            recovery_frame = int(between_positions[np.argmin(y[between_positions])])
            recovery_y = float(y[recovery_frame])
        else:
            recovery_frame = previous_peak
            recovery_y = float(y[previous_peak])
        previous_depth = float(y[previous_peak] - y[left_bases[previous_index]])
        if left_bases[current_index] > right_bases[previous_index]:
            kept.append(current_index)
        elif y[current_peak] - recovery_y >= depth_threshold * previous_depth:
            left_bases[current_index] = recovery_frame
            kept.append(current_index)
        elif y[current_peak] > y[previous_peak]:
            if kept:
                kept.pop()
            kept.append(current_index)
            left_bases[current_index] = left_bases[previous_index]
        else:
            right_bases[previous_index] = right_bases[current_index]
    selected_peaks = peaks[kept].copy()
    selected_left = left_bases[kept].copy()
    selected_right = right_bases[kept].copy()
    for index, start in enumerate(selected_left):
        if likelihood[start] < likelihood_threshold:
            selected_left[index] = max(0, selected_peaks[index] - 1)
            selected_right[index] = min(len(y) - 1, selected_peaks[index] + 1)
    return (selected_peaks, selected_left, selected_right)


def baseline_als(y, lam, asymmetry, np, sparse, spsolve, iterations=10):
    length = len(y)
    difference = sparse.csc_matrix(np.diff(np.eye(length), 2))
    weights = np.ones(length)
    for _ in range(iterations):
        weight_matrix = sparse.spdiags(weights, 0, length, length)
        system = weight_matrix + lam * difference.dot(difference.transpose())
        baseline = spsolve(system, weights * y)
        weights = asymmetry * (y > baseline) + (1 - asymmetry) * (y < baseline)
    return baseline
