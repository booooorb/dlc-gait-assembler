"""Detect dragging frames and retain every frame in qualifying contact runs."""

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
        return 0, 0, np.array([])

    # Per-stride ground detection from stance phase
    if stance_dur > 0:
        ground_level = np.percentile(toe_y[start:swing_start], 90)
    else:
        ground_level = threshold

    # Detect dragging: toe is near/below ground during swing
    is_drag_raw = toe_y[swing_start:swing_end] >= (ground_level - clearance_px)

    # Require at least min_consecutive_frames consecutive frames to reduce noise
    # Retain whole qualifying runs, including their last frames. Short runs
    # must be rejected even when the entire swing is shorter than the minimum.
    if not isinstance(min_consecutive_frames, (int, np.integer)) or min_consecutive_frames < 1:
        raise ValueError("Consecutive drag frames must be a positive integer.")
    is_drag = np.zeros(len(is_drag_raw), dtype=bool)
    transitions = np.diff(np.r_[False, is_drag_raw, False].astype(np.int8))
    for run_start, run_end in zip(np.flatnonzero(transitions == 1), np.flatnonzero(transitions == -1), strict=False):
        if run_end - run_start >= min_consecutive_frames:
            is_drag[run_start:run_end] = True

    drag_frames = np.sum(is_drag)
    drag_fraction = drag_frames / swing_length if swing_length > 0 else 0

    return drag_frames, drag_fraction, is_drag
