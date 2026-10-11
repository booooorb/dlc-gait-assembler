"""Detect paw deviations, slips/falls, and their recovery intervals."""

from __future__ import annotations

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderEvent
from dlc_gait_assembly.ladder.business.ladder_signal_preparation import baseline_als as _baseline_als
from dlc_gait_assembly.ladder.business.ladder_signal_preparation import filter_predictions as _filter_predictions


def detect_bodypart(dataframe, bodypart, settings, np, find_peaks, sparse, spsolve) -> list[LadderEvent]:
    y_column = f"{bodypart} y"
    likelihood_column = f"{bodypart} likelihood"
    if y_column not in dataframe or likelihood_column not in dataframe:
        raise ValueError(f"{bodypart!r} does not have y and likelihood coordinates.")
    y = np.asarray(dataframe[y_column], dtype=float)
    likelihood = np.asarray(dataframe[likelihood_column], dtype=float)
    if settings.method == "Deviation":
        (peaks, properties) = find_peaks(y, height=-10000, prominence=(45, 100000))
    elif settings.method == "Baseline":
        valid_positions = np.flatnonzero(np.isfinite(y) & (likelihood >= settings.likelihood_threshold))
        if len(valid_positions) < 3:
            return []
        baseline = _baseline_als(y[valid_positions], 10**2, 0.1, np, sparse, spsolve)
        (peaks, properties) = find_peaks(baseline, prominence=(10, 100000))
        peaks = valid_positions[peaks]
        properties["left_bases"] = valid_positions[properties["left_bases"]]
        properties["right_bases"] = valid_positions[properties["right_bases"]]
    elif settings.method == "Threshold":
        threshold = settings.threshold
        if threshold is None:
            threshold = float(np.nanmean(y) + np.nanstd(y))
        adjusted = np.full(len(y), threshold, dtype=float)
        adjusted[y > threshold] = y[y > threshold]
        (peaks, properties) = find_peaks(adjusted, prominence=(10, 1000))
    else:
        raise ValueError(f"Unsupported ladder detection method: {settings.method}")
    (peaks, left_bases, right_bases) = _filter_predictions(
        peaks, properties, y, likelihood, settings.likelihood_threshold, settings.depth_threshold, np
    )
    if settings.method == "Baseline" and len(peaks):
        window = settings.baseline_window_frames
        if window is None:
            window = max(1, int(settings.frame_rate // 5))
        peaks = adjust_times(y, peaks, window, np)
    events: list[LadderEvent] = []
    for peak, start, end in zip(peaks, left_bases, right_bases, strict=False):
        peak = int(peak)
        start = int(start)
        end = int(end)
        depth = float((y[peak] - y[start] + (y[peak] - y[end])) / 2.0)
        events.append(
            LadderEvent(
                bodypart=bodypart,
                peak_frame=peak,
                start_frame=start,
                end_frame=end,
                peak_y_px=float(y[peak]),
                depth_px=depth,
                duration_s=round((end - start) / settings.frame_rate, 3),
            )
        )
    return events


def adjust_times(y, peaks, window, np):
    adjusted = np.asarray(peaks, dtype=int).copy()
    for index, peak in enumerate(adjusted):
        start = max(0, int(peak) - int(window))
        end = min(len(y), int(peak) + int(window))
        if end > start:
            adjusted[index] = start + int(np.nanargmax(y[start:end]))
    return adjusted
