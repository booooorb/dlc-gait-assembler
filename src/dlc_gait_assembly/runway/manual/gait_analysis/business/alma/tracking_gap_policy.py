"""A frame-rate independent allowance for brief losses of the timing marker."""

import math

AUTO_TRACKING_GAP = -1
AUTO_TRACKING_GAP_MS = 50


def tracking_gap_frames(value, frame_rate):
    """Explicit zero is strict; automatic bridges at most 50 ms internally."""
    value = int(value)
    if value == AUTO_TRACKING_GAP:
        return max(0, math.floor(float(frame_rate) * AUTO_TRACKING_GAP_MS / 1000))
    if value < 0:
        raise ValueError("Tracking gap must be Auto (-1), zero, or a positive frame count.")
    return value
