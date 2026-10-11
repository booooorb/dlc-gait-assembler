"""Detect dragging frames and calculate per-cycle drag durations."""

from __future__ import annotations

import numpy as np


def find_drag(toe_y, stance_dur, threshold, start, end, clearance_px=0, min_consecutive_frames=4):
    """
    Detect dragging during swing phase with improved robustness.

    Args:
        toe_y: toe y-coordinates (vertical position)
        stance_dur: stance duration in frames
        threshold: fallback threshold (treadmill y level)
        start: stride start frame
        end: stride end frame
        clearance_px: minimum clearance above ground in pixels to not count as drag
        min_consecutive_frames: minimum consecutive frames of ground contact to count as dragging

    Returns:
        drag_frames: number of frames with dragging
        drag_fraction: fraction of swing phase with dragging
        drag_mask: boolean array indicating drag frames (for visualization)
    """
    swing_start = start + stance_dur
    swing_end = end
    swing_length = swing_end - swing_start
    if swing_length <= 0:
        return (0, 0, np.array([]))
    if stance_dur > 0:
        ground_level = np.percentile(toe_y[start:swing_start], 90)
    else:
        ground_level = threshold
    is_drag_raw = toe_y[swing_start:swing_end] >= ground_level - clearance_px
    is_drag = is_drag_raw.copy()
    if len(is_drag) >= min_consecutive_frames:
        for i in range(len(is_drag) - min_consecutive_frames + 1):
            if all(is_drag_raw[i : i + min_consecutive_frames]):
                is_drag[i : i + min_consecutive_frames] = True
            else:
                is_drag[i] = False
        for i in range(len(is_drag) - min_consecutive_frames + 1, len(is_drag)):
            is_drag[i] = False
    drag_frames = np.sum(is_drag)
    drag_fraction = drag_frames / swing_length if swing_length > 0 else 0
    return (drag_frames, drag_fraction, is_drag)
