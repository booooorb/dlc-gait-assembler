"""Context changes supported phase probabilities, never marker likelihood/geometry."""

from itertools import product

import numpy as np
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import detect_strides
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import (
    CONTEXT_MIXTURE_METHOD,
    contextual_stance_probability,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
    stickplot_phase_codes,
)


def infer(p, trusted=None, fps=120.0, context=60.0):
    p = np.asarray(p, float)
    return contextual_stance_probability(p, np.ones(len(p), bool) if trusted is None else trusted, fps, context)


def test_ambiguous_frame_gains_support_from_both_sides():
    p = np.full(21, 0.9)
    p[10] = 0.52
    posterior = infer(p)
    assert posterior[10] > 0.95
    assert posterior[10] > infer(p[:11])[-1]  # Future evidence matters too.
    assert p[10] == 0.52  # Never rewrite input scores.


def test_conflicting_neighbours_leave_transition_uncertain():
    p = np.r_[np.full(10, 0.99), 0.5, np.full(10, 0.01)]
    posterior = infer(p)
    assert posterior[10] == pytest.approx(0.5)
    assert posterior[8] > 0.95 and posterior[12] < 0.05
    np.testing.assert_allclose(posterior, 1 - infer(1 - p), atol=1e-12)


def test_context_removes_weak_flicker_but_keeps_real_short_swing():
    p = np.r_[np.full(20, 0.95), 0.45, np.full(20, 0.95), np.full(6, 0.001), np.full(20, 0.95)]
    posterior = infer(p)
    assert posterior[20] > 0.9
    assert np.all(posterior[41:47] < 0.1)
    assert np.sum(np.diff(posterior >= 0.5) != 0) == 2


def test_context_does_not_invent_certainty_for_no_evidence():
    np.testing.assert_allclose(infer(np.full(10000, 0.5)), 0.5, atol=1e-12)


def test_tracking_gaps_restart_inference_and_remain_unavailable():
    p = np.r_[np.full(20, 0.99), 0.9, 0.51]
    trusted = np.ones(len(p), bool)
    trusted[20] = False
    posterior = infer(p, trusted)
    assert np.isnan(posterior[20])
    assert posterior[21] == pytest.approx(0.51)
    np.testing.assert_allclose(posterior[:20], infer(p[:20]))
    p[20] = np.nan
    np.testing.assert_allclose(infer(p), posterior, equal_nan=True)


def test_zero_context_returns_unmodified_gmm_probabilities():
    p = np.array([0.0, 0.12, 0.51, 0.83, 1.0])
    np.testing.assert_array_equal(infer(p, context=0), p)


def test_forward_backward_matches_enumerated_chain_distribution():
    p = np.array([0.2, 0.65, 0.55, 0.9, 0.35])
    switch = 1 - np.exp(-1000 / (120 * 60))
    weighted = []
    for states in product((0, 1), repeat=len(p)):
        weight = np.prod([p[i] if state else 1 - p[i] for i, state in enumerate(states)])
        weight *= np.prod([1 - switch if a == b else switch for a, b in zip(states[:-1], states[1:], strict=True)])
        weighted.append((states, weight))
    normalizer = sum(weight for _, weight in weighted)
    expected = [sum(weight * state[i] for state, weight in weighted) / normalizer for i in range(len(p))]
    np.testing.assert_allclose(infer(p), expected, atol=1e-12)


@pytest.mark.parametrize("fps,context", [(0, 60), (120, -1), (float("nan"), 60), (120, float("inf"))])
def test_invalid_context_settings_are_rejected(fps, context):
    with pytest.raises(ValueError):
        infer([0.4, 0.6], fps=fps, context=context)


def test_phase_uncertainty_does_not_overwrite_dlc_confidence():
    frames = np.arange(360)
    x = frames * 0.3 + 15 * np.sin(frames * 2 * np.pi / 40)
    y = 100 - 8 * np.sin(frames * 2 * np.pi / 40)
    likelihood = np.ones(len(frames))
    likelihood[100:120] = 0.1
    before = likelihood.copy()
    diagnostics = {}
    stance, starts, ends, _ = detect_strides(
        x, y, likelihood, 120.0, method=CONTEXT_MIXTURE_METHOD, diagnostics=diagnostics
    )
    np.testing.assert_array_equal(likelihood, before)
    np.testing.assert_array_equal(diagnostics["confidence"], before)
    posterior = diagnostics["stance_probability"]
    assert np.isnan(posterior[100:120]).all()
    np.testing.assert_array_equal(np.asarray(stance)[diagnostics["trusted"]], posterior[diagnostics["trusted"]] >= 0.5)
    assert all(not (start <= 119 and end >= 100) for start, end in zip(starts, ends, strict=True))
    support = diagnostics["phase_confidence"]
    np.testing.assert_allclose(support, np.maximum(posterior, 1 - posterior), equal_nan=True)


def test_uncertain_frames_are_pale_without_changing_inferred_phase():
    inferred = np.array([True, True, False, False])
    rendered = stickplot_phase_codes(inferred, 4, phase_confidence=[0.6, 0.9, 0.8, np.nan])
    assert rendered.tolist() == ["unknown", "stance", "swing", "unknown"]
    assert inferred.tolist() == [True, True, False, False]
