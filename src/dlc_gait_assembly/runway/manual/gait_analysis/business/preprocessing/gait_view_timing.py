"""Align views in video time without confusing CSV row positions with frames."""

import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaPreprocessedCoordinates
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    coordinate_columns,
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
)


@dataclass
class ViewTrack:
    view: str
    path: Path
    frame: object
    times: object
    frame_ids: object
    present: object
    frame_rate: float
    source: str

    @property
    def stop_time(self):
        return self.times[-1] + 1 / self.frame_rate


def clip_start_seconds(path):
    stamp = r"(\d{2})[.:](\d{2})[.:](\d{2})[.:](\d{3})"
    match = re.search(stamp + r"[-_]" + stamp, Path(path).name)
    if match is None:
        return None
    hours, minutes, seconds, millis = map(int, match.groups()[:4])
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def read_view_track(raw, path, view, settings):
    """DLC frame IDs + FPS + clip start, or explicit video timestamps in seconds.

    Missing source rows become missing frames, never a compressed time axis.
    Explicit timestamps must lie on the source video's constant-rate frame grid.
    """
    config = (getattr(settings, "view_timing", None) or {}).get(view, {})
    coords = [
        c
        for c in raw
        if str(c[-1] if isinstance(c, tuple) else c.rsplit(" ", 1)[-1]).lower() in {"x", "y", "likelihood"}
    ]
    extras = [c for c in raw if c not in coords]

    def key(column):
        parts = column if isinstance(column, tuple) else (column,)
        return [str(p).strip().lower().replace(" ", "_") for p in parts]

    time_columns = [
        c
        for c in extras
        if any(
            p in {"timestamp", "timestamp_s", "timestamp_(s)", "time_s", "time_(s)", "timestamp_ms", "time_ms"}
            for p in key(c)
        )
    ]
    if len(time_columns) > 1:
        raise ValueError(f"{view.title()} CSV has multiple timestamp columns; keep one video-time column.")
    frame_columns = [
        c
        for c in extras
        if c not in time_columns
        and any(
            p in {"bodyparts", "frame", "frame_id", "frame_index", "frames"} or p.startswith("unnamed:") for p in key(c)
        )
    ]
    ids = (
        pd.to_numeric(raw[frame_columns[0]], errors="coerce").to_numpy(float)
        if frame_columns
        else np.arange(len(raw), dtype=float)
    )
    if not len(raw) or not np.isfinite(ids).all() or (np.diff(ids) <= 0).any():
        raise ValueError(f"{view.title()} CSV needs unique, increasing numeric source frame numbers.")
    fps = float(config.get("frame_rate") or settings.frame_rate)
    offset = float(config.get("offset_s", 0.0))
    if time_columns:
        times = pd.to_numeric(raw[time_columns[0]], errors="coerce").to_numpy(float, copy=True)
        if any(p.endswith("_ms") for p in key(time_columns[0])):
            times /= 1000.0
        if len(times) > 1 and not config.get("frame_rate"):
            fps = float(np.median(np.diff(ids) / np.diff(times)))
        source = "CSV video timestamps"
    else:
        start = clip_start_seconds(path)
        source = (
            "filename clip start + source frame / FPS"
            if start is not None
            else "shared clip origin + source frame / FPS"
        )
        times = (start or 0.0) + ids / fps
    times = times + offset
    if not np.isfinite(fps) or fps <= 0 or not np.isfinite(times).all() or (np.diff(times) <= 0).any():
        raise ValueError(f"{view.title()} needs a positive frame rate and strictly increasing video timestamps.")
    slots = np.rint((times - times[0]) * fps).astype(int)
    if not np.allclose(times, times[0] + slots / fps, atol=0.05 / fps, rtol=0) or len(set(slots)) != len(slots):
        raise ValueError(
            f"{view.title()} timestamps disagree with its frame rate. Set that view’s actual FPS in Setup → View timing."
        )
    size = int(slots[-1]) + 1
    frame = raw.loc[:, coords].copy()
    frame.index = slots
    frame = frame.reindex(range(size))
    present = np.zeros(size, bool)
    present[slots] = True
    for column in frame:
        if str(column[-1]).lower() == "likelihood":
            frame.loc[~present, column] = 0.0
    frame_ids = np.interp(np.arange(size), slots, ids)
    return ViewTrack(
        view,
        Path(path),
        frame.reset_index(drop=True),
        times[0] + np.arange(size) / fps,
        frame_ids,
        present,
        fps,
        source + (f"; offset {offset:+g} s" if offset else ""),
    )


def matching_samples(track, target_times):
    positions = (np.asarray(target_times) - track.times[0]) * track.frame_rate
    rounded = np.rint(positions)
    positions = np.where(np.abs(positions - rounded) < 1e-6, rounded, positions)
    lower = np.floor(positions).astype(int)
    upper = np.ceil(positions).astype(int)
    valid = (lower >= 0) & (upper < len(track.times))
    lower = np.clip(lower, 0, len(track.times) - 1)
    upper = np.clip(upper, 0, len(track.times) - 1)
    valid &= track.present[lower] & track.present[upper]
    return lower, upper, positions - np.floor(positions), valid


def resample_values(values, match, *, likelihood=False):
    lower, upper, weight, valid = match
    values = np.asarray(values, float)
    # Never extend a view past its real recording or interpolate across absent rows.
    result = (
        np.minimum(values[lower], values[upper])
        if likelihood
        else values[lower] * (1 - weight) + values[upper] * weight
    )
    return np.where(valid, result, np.nan)


def raw_on_timeline(track, times):
    match = matching_samples(track, times)
    return pd.DataFrame(
        {
            c: resample_values(pd.to_numeric(track.frame[c], errors="coerce"), match, likelihood=c[-1] == "likelihood")
            for c in track.frame
        }
    )


def aligned_features(tracks, reference, settings, mappings, filtering):
    """Filter at each camera's native FPS, then align to the chosen side's time axis."""
    target = tracks[reference]
    frames, series = {}, {}
    for view, track in tracks.items():
        native = align_multiview_coordinates({view: track.frame}, pd, mappings)
        prepared = prepare_alma_coordinates(native, replace(settings, frame_rate=track.frame_rate), filtering)
        match = matching_samples(track, target.times)
        frames[view] = raw_on_timeline(track, target.times)
        for marker, axes in prepared.series.items():
            series[marker] = {
                axis: None if values is None else resample_values(values, match) for axis, values in axes.items()
            }
    merged = align_multiview_coordinates(frames, pd, mappings)
    prepared = AlmaPreprocessedCoordinates(
        coordinate_columns(merged),
        series,
        len(merged),
        settings.likelihood_threshold,
        target.frame_rate,
        settings.filter_cutoff,
    )
    return merged, prepared


def stride_time_bounds(parameters, track):
    bounds = []
    for _, row in parameters.iterrows():
        try:
            start, end = (int(float(row[name])) for name in ("stride_start (frame)", "stride_end (frame)"))
            if not 0 <= start <= end < len(track.times):
                raise ValueError
            bounds.append((track.times[start], track.times[end] + 1 / track.frame_rate))
        except (ValueError, TypeError, OverflowError):
            bounds.append((np.nan, np.nan))
    return bounds
