"""Known-contact synthetic walks exercise every method, beyond rendering checks."""

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    RUSTLAB1_METHOD,
    STRIDE_METHODS,
    bottom_detection,
    detect_strides,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.stride_candidates import ORIGINAL_ALMA


def variable_speed_walk(noisy=False):
    xs, ys, hips, phases = [], [], [], []
    position = 0.0
    for duration, distance in zip((60, 42, 55, 36, 50, 65, 40, 58), (65, 40, 75, 45, 85, 60, 50, 90), strict=True):
        stance_length = round(duration * 0.6)
        swing = np.linspace(0, 1, duration - stance_length, endpoint=False)
        xs.extend(np.r_[np.full(stance_length, position), position + distance * (1 - np.cos(np.pi * swing)) / 2])
        ys.extend(np.r_[np.full(stance_length, 100.0), 100 - 18 * np.sin(np.pi * swing)])
        hips.extend(np.linspace(position - 20, position + distance - 20, duration, endpoint=False))
        phases.extend(np.arange(duration) < stance_length)
        position += distance
    xs.extend(np.full(30, position))
    ys.extend(np.full(30, 100.0))
    hips.extend(position - 20 + np.arange(30))
    phases.extend(np.ones(30, bool))
    x, y, hip = np.array(xs), np.array(ys), np.array(hips)
    likelihood = np.ones(len(x))
    if noisy:
        rng = np.random.default_rng(17)
        x += rng.normal(0, 0.15, len(x))
        y += rng.normal(0, 0.15, len(x))
        likelihood[174:188] = 0.1  # Must never become a false spanning stride.
    return x, y, hip, likelihood, np.asarray(phases, bool)


def run_method(method, x, y, hip, confidence):
    cfg = AlmaSettings(
        frame_rate=120.0,
        likelihood_threshold=0.5,
        max_interpolation_gap_frames=3,
        stride_detection_method=method,
        stance_speed_threshold_px_frame=1.0,
    )
    if method == RUSTLAB1_METHOD:
        raw = pd.DataFrame({("lhpaw", "x"): x, ("lhpaw", "y"): y, ("lhpaw", "likelihood"): confidence})
        return bottom_detection(raw, "left", cfg)
    filtered_x, filtered_y, filtered_hip = (
        butterworth_filter(values, cfg.frame_rate, cfg.filter_cutoff) for values in (x, y, hip)
    )
    return detect_strides(
        filtered_x,
        filtered_y,
        confidence,
        cfg.frame_rate,
        method=method,
        relative_x=filtered_x - filtered_hip,
        original_x=x,
        right_to_left=False,
        maximum_gap=cfg.max_interpolation_gap_frames,
    )


@pytest.mark.parametrize("method", STRIDE_METHODS)
@pytest.mark.parametrize("noisy", (False, True))
def test_variable_speed_contacts_and_confidence_gaps(method, noisy):
    x, y, hip, confidence, expected = variable_speed_walk(noisy)
    stance, starts, ends, _ = run_method(method, x, y, hip, confidence)
    assert len(stance) == len(x)
    assert len(starts) == len(ends)
    assert all(0 <= start < end < len(x) - 1 for start, end in zip(starts, ends, strict=True))
    assert starts == sorted(set(starts))
    if noisy:
        assert all(not (start <= 187 and end >= 174) for start, end in zip(starts, ends, strict=True))
    else:
        assert 5 <= len(starts) <= 10
        # Contacts are known in this signal; a constant or inverted mask fails.
        agreement = np.mean(np.asarray(stance, bool) == expected)
        assert agreement >= 0.70, (method, agreement)


@pytest.mark.parametrize("method", STRIDE_METHODS)
@pytest.mark.parametrize("jitter", (0.0, 0.02))
def test_stationary_recording_never_fabricates_a_stride(method, jitter):
    n = 180
    _, starts, ends, _ = run_method(
        method,
        40 + np.random.default_rng(1).normal(0, jitter, n),
        100 + np.random.default_rng(2).normal(0, jitter, n),
        np.full(n, 70.0),
        np.ones(n),
    )
    assert starts == [] and ends == []


def test_original_alma_preserves_strict_displacement_and_spacing_rules():
    x, y, hip, confidence, _ = variable_speed_walk()
    _, original, _, _ = run_method(ORIGINAL_ALMA, x, y, hip, confidence)
    assert len(original) == 7
    # The historical >20 px gate is fixed, not a renamed adaptive threshold.
    _, small, _, _ = run_method(ORIGINAL_ALMA, x / 100, y, hip / 100, confidence)
    assert small == []
    confidence[:] = 0.6
    _, low, _, _ = run_method(ORIGINAL_ALMA, x, y, hip, confidence)
    assert low == []


@pytest.mark.parametrize("method", ("Paw excursion peaks", "Hip-relative velocity"))
def test_auto_direction_is_invariant_to_mirrored_camera(method):
    x, y, hip, confidence, _ = variable_speed_walk()
    x, y, hip = (butterworth_filter(a, 120.0, 6.0) for a in (x, y, hip))
    forward = detect_strides(x, y, confidence, 120.0, method=method, relative_x=x - hip)
    reverse = detect_strides(-x, y, confidence, 120.0, method=method, relative_x=hip - x)
    np.testing.assert_array_equal(forward[0], reverse[0])
    assert forward[1:3] == reverse[1:3]
