"""Apply the established ALMA marker interpolation and Butterworth-filtering calculations."""

from __future__ import annotations

from scipy.signal import butter, filtfilt


def butterworth_filter(bodypart_loc, frame_rate, cutoff_f):
    w = cutoff_f / (frame_rate / 2)
    (b, a) = butter(5, w, "low")
    filtered_bodypart_loc = filtfilt(b, a, bodypart_loc)
    return filtered_bodypart_loc
