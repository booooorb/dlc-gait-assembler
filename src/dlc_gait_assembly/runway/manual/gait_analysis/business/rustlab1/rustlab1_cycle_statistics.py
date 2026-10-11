"""Calculate per-cycle RustLab1 statistics and apply selected parameter availability."""

from __future__ import annotations


def cycle_bounds(row, frame_count: int) -> tuple[int, int] | None:
    try:
        start = int(float(row["stride_start (frame)"]))
        end = int(float(row["stride_end (frame)"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if frame_count <= 0 or end < start:
        return None
    start = max(0, min(start, frame_count - 1))
    end = max(start, min(end, frame_count - 1))
    return (start, end)


def step_duration_seconds(stance, start: int, end: int, frame_rate: float, np) -> float:
    if stance is None or frame_rate <= 0:
        return np.nan
    stance = np.asarray(stance, dtype=bool)
    onsets = np.flatnonzero(stance & ~np.r_[False, stance[:-1]])
    if len(onsets) < 2:
        return np.nan
    intervals = np.diff(onsets).astype(float) / frame_rate
    overlaps = (onsets[:-1] <= end) & (onsets[1:] >= start)
    return safe_stat(np.nanmedian, intervals[overlaps], np)


def enabled_parameters(settings, available: tuple[str, ...]) -> tuple[str, ...]:
    selected = getattr(settings, "enabled_parameter_names", None)
    if selected is None:
        return available
    selected_set = set(selected)
    return tuple(name for name in available if name in selected_set)


def slice(series, marker, coord, cycle_slice):
    marker_series = series.get(marker)
    if not marker_series:
        return None
    values = marker_series.get(coord)
    return None if values is None else values[cycle_slice]


def safe_stat(function, values, np) -> float:
    if values is None or not np.isfinite(values).any():
        return np.nan
    return float(function(values))


def safe_percentile(values, percentile, np) -> float:
    if values is None or not np.isfinite(values).any():
        return np.nan
    return float(np.nanpercentile(values, percentile))
