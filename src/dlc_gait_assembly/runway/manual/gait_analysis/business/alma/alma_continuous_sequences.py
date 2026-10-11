"""Select continuous accepted cycle sequences for scientific previews and summaries."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd


def findLongestSequence(A, k):
    """
    Function to find the maximum sequence of continuous 1's by replacing
    at most `k` zeroes by 1 using sliding window technique
    """
    left = 0
    count = 0
    window = 0
    leftIndex = 0
    for right in range(len(A)):
        if A[right] == 0:
            count = count + 1
        while count > k:
            if A[left] == 0:
                count = count - 1
            left = left + 1
        if right - left + 1 > window:
            window = right - left + 1
            leftIndex = left
    return (leftIndex, leftIndex + window - 1)


@dataclass(frozen=True)
class ContinuousStickplotData:
    parameters: object
    coordinates: object
    bodyparts: tuple[str, ...]
    stance: object
    x_coordinates: object
    y_coordinates: object
    start_frame: int
    end_frame: int
    dragging: object
    method: str = "ALMA (legacy)"
    timing_source: str = "Side toe"
    view_label: str = ""
    trusted: object = None
    axis_limits: object = None
    tracking_only: bool = False
    phase_confidence: object = None


def preview_cycle_rows(parameters, frame_count, include_rejected=False):
    if parameters.empty:
        return parameters
    starts = pd.to_numeric(parameters["stride_start (frame)"], errors="coerce")
    ends = pd.to_numeric(parameters["stride_end (frame)"], errors="coerce")
    valid = starts.notna() & ends.notna() & (starts >= 0) & (ends < frame_count) & (ends > starts)
    if not include_rejected:
        durations = pd.to_numeric(parameters["cycle duration (s)"], errors="coerce")
        valid &= durations.notna() & (durations > 0)
    return parameters.loc[valid]


def prepare_continuous_stickplot(
    parameters,
    coordinates,
    bodyparts,
    stance,
    n_continuous=10,
    drag_masks=None,
    starts=None,
    drag_min_consecutive_frames=4,
    *,
    include_rejected=False,
    allow_disjoint=False,
):
    if parameters.empty or parameters.isnull().all().all():
        return None
    durations = pd.to_numeric(parameters["cycle duration (s)"], errors="coerce").to_numpy(float)
    frame_starts = pd.to_numeric(parameters["stride_start (frame)"], errors="coerce").to_numpy(float)
    frame_ends = pd.to_numeric(parameters["stride_end (frame)"], errors="coerce").to_numpy(float)
    valid = np.isfinite(frame_starts) & np.isfinite(frame_ends)
    if not include_rejected:
        valid &= np.isfinite(durations) & (durations > 0)
    valid &= (frame_starts >= 0) & (frame_ends < len(coordinates)) & (frame_ends >= frame_starts)
    if not valid.any():
        return None
    # Consecutive table rows need not be consecutive source frames: detectors can
    # omit cycles across long confidence gaps. Never present that gap as a stride.
    groups = []
    for row in np.flatnonzero(valid):
        if groups and row == groups[-1][-1] + 1 and frame_starts[row] == frame_ends[groups[-1][-1]] + 1:
            groups[-1].append(row)
        else:
            groups.append([row])
    longest = list(np.flatnonzero(valid)) if allow_disjoint else max(groups, key=len)
    if allow_disjoint:
        count = min(max(1, int(n_continuous)), len(longest))
        # Center all methods on the same recording midpoint, not each method's
        # longest surviving run. Source-frame gaps remain gaps in the renderer.
        window = min(
            (longest[i : i + count] for i in range(len(longest) - count + 1)),
            key=lambda rows: abs((frame_starts[rows[0]] + frame_ends[rows[-1]]) / 2 - len(coordinates) / 2),
        )
        parameters = parameters.iloc[window].reset_index(drop=True)
        return _prepare_selected(
            parameters, coordinates, bodyparts, stance, drag_masks, starts, drag_min_consecutive_frames
        )
    start, end = longest[0], longest[-1]
    count = min(max(1, int(n_continuous)), end - start + 1)
    first = start + (end - start + 1 - count) // 2
    last = first + count - 1
    return_end = last + 1
    try:
        start_value = parameters.iloc[first]["stride_start (frame)"]
        end_value = parameters.iloc[last]["stride_end (frame)"]
        if (
            pd.isna(start_value)
            or pd.isna(end_value)
            or str(start_value).lower() == "nan"
            or str(end_value).lower() == "nan"
        ):
            return None
        start_frame, end_frame = int(float(start_value)), int(float(end_value))
        x = coordinates[[f"{marker} x" for marker in bodyparts]].copy()
        y = coordinates[[f"{marker} y" for marker in bodyparts]].copy()
        x.columns = y.columns = bodyparts
        drag = reconstruct_continuous_drag_mask(stance, drag_masks, starts, drag_min_consecutive_frames)
        attrs = coordinates.attrs
        return ContinuousStickplotData(
            parameters.iloc[first:return_end, :],
            coordinates,
            tuple(bodyparts),
            stance,
            x.T,
            y.T,
            start_frame,
            end_frame,
            drag,
            attrs.get("stride_method", "ALMA (legacy)"),
            attrs.get("timing_source", "Side toe"),
            attrs.get("view_label", ""),
            attrs.get("detection_diagnostics", {}).get("trusted"),
            phase_confidence=attrs.get("detection_diagnostics", {}).get("phase_confidence"),
        )
    except (IndexError, ValueError):
        return None


def _prepare_selected(
    parameters, coordinates, bodyparts, stance, masks=None, starts=None, drag_min_frames=4, *, tracking_only=False
):
    x = coordinates[[f"{marker} x" for marker in bodyparts]].copy()
    y = coordinates[[f"{marker} y" for marker in bodyparts]].copy()
    x.columns = y.columns = bodyparts
    first = int(float(parameters.iloc[0]["stride_start (frame)"])) if len(parameters) else 0
    last = int(float(parameters.iloc[-1]["stride_end (frame)"])) if len(parameters) else len(coordinates) - 1
    attrs = coordinates.attrs
    return ContinuousStickplotData(
        parameters,
        coordinates,
        tuple(bodyparts),
        stance,
        x.T,
        y.T,
        first,
        last,
        reconstruct_continuous_drag_mask(stance, masks, starts, drag_min_frames),
        attrs.get("stride_method", "ALMA (legacy)"),
        attrs.get("timing_source", "Side toe"),
        attrs.get("view_label", ""),
        attrs.get("detection_diagnostics", {}).get("trusted"),
        tracking_only=tracking_only,
        phase_confidence=attrs.get("detection_diagnostics", {}).get("phase_confidence"),
    )


def prepare_tracking_stickplot(coordinates, bodyparts):
    """Show the observed skeleton when no complete cycle exists; never label one."""
    if coordinates is None or len(coordinates) < 2:
        return None
    empty = pd.DataFrame(columns=["stride_start (frame)", "stride_end (frame)", "cycle duration (s)"])
    return _prepare_selected(empty, coordinates, bodyparts, np.full(len(coordinates), np.nan), tracking_only=True)


def reconstruct_continuous_drag_mask(stance, drag_masks, starts, minimum_frames):
    if drag_masks is None or starts is None or len(drag_masks) == 0:
        return None
    drag = np.zeros(len(stance), dtype=bool)
    for i, mask in enumerate(drag_masks):
        if len(mask) > 0 and i < len(starts):
            stride_start = starts[i]
            stride_end = starts[i + 1] if i + 1 < len(starts) else len(stance)
            stance_duration = 0
            for frame in range(stride_start, min(stride_end, len(stance))):
                if stance[frame] == 1:
                    stance_duration += 1
                else:
                    break
            for j, value in enumerate(mask):
                frame = stride_start + stance_duration + j
                if frame < len(drag) and frame < stride_end and stance[frame] == 0:
                    drag[frame] = value
    # The renderer formerly tested contiguous drag length for each plotted frame.
    accepted = drag.copy()
    for frame in np.flatnonzero(drag):
        left, right = frame, frame
        while left > 0 and drag[left - 1]:
            left -= 1
        while right < len(drag) - 1 and drag[right + 1]:
            right += 1
        if right - left + 1 < minimum_frames:
            accepted[frame] = False
    return accepted


def prepare_full_recording_stickplot(parameters, coordinates, bodyparts, stance):
    """Geometry is the full source recording, independent of detected/accepted cycles."""
    if coordinates is None or len(coordinates) < 2:
        return None
    rows = preview_cycle_rows(parameters, len(coordinates), include_rejected=True)
    prepared = _prepare_selected(rows, coordinates, bodyparts, stance, tracking_only=rows.empty)
    # Do not apply detector-dependent drag masks or crop to a cycle boundary.
    return replace(
        prepared,
        start_frame=0,
        end_frame=len(coordinates) - 1,
        dragging=None,
        axis_limits=stickplot_axis_limits(prepared),
    )


def stickplot_axis_limits(data):
    """Identical bounds in previews, comparisons and saved full-recording plots."""
    axes = []
    for values in (data.x_coordinates, data.y_coordinates):
        finite = values.to_numpy(float)
        finite = finite[np.isfinite(finite)]
        low, high = (float(finite.min()), float(finite.max())) if len(finite) else (0.0, 1.0)
        padding = max(1.0, (high - low) * 0.03)
        axes.append((low - padding, high + padding))
    return tuple(axes)
