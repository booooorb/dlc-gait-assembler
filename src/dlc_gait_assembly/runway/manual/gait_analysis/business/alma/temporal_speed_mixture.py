"""Neighbour-conditioned GMM probabilities without changing tracking coordinates.

The chain distribution is proportional to the product of each frame's GMM
probability and symmetric phase-persistence factors between adjacent frames.
Forward/backward inference returns marginals, not a forced certainty increase.
Scores describe this motion model; they are not calibrated contact accuracy.
"""

import numpy as np

CONTEXT_MIXTURE_METHOD = "Speed Mixture + Nearby Confidence"
PHASE_SUPPORT_THRESHOLD = 0.70


def contextual_stance_probability(probability, trusted, frame_rate, context_ms=60.0):
    """Use evidence on both sides, restarting at each untrusted/nonfinite gap.

    context_ms controls the persistence timescale, rather than a hard window.
    Zero disables context. The symmetric prior cannot invent a preferred phase
    for an entirely ambiguous trace. Normalization at every step avoids underflow.
    """
    probability = np.asarray(probability, float)
    trusted = np.asarray(trusted, bool)
    if probability.ndim != 1 or trusted.shape != probability.shape:
        raise ValueError("Phase probabilities and tracking mask must share one frame axis.")
    if not np.isfinite(frame_rate) or frame_rate <= 0 or not np.isfinite(context_ms) or context_ms < 0:
        raise ValueError("Frame rate must be positive and neighbour context nonnegative.")
    finite = trusted & np.isfinite(probability)
    if np.any((probability[finite] < 0) | (probability[finite] > 1)):
        raise ValueError("Phase probabilities must be between zero and one.")
    result = np.full(len(probability), np.nan)
    if context_ms == 0:
        result[finite] = probability[finite]
        return result
    switch = min(0.5, -np.expm1(-1000.0 / (frame_rate * context_ms)))
    transition = np.array([[1 - switch, switch], [switch, 1 - switch]])
    edges = np.diff(np.r_[False, finite, False].astype(int))
    for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
        p = np.clip(probability[start:stop], 1e-6, 1 - 1e-6)
        emission = np.column_stack((1 - p, p))
        forward = np.empty_like(emission)
        forward[0] = emission[0] / emission[0].sum()
        for frame in range(1, len(p)):
            forward[frame] = (forward[frame - 1] @ transition) * emission[frame]
            forward[frame] /= forward[frame].sum()
        backward = np.ones(2)
        for frame in range(len(p) - 1, -1, -1):
            posterior = forward[frame] * backward
            result[start + frame] = posterior[1] / posterior.sum()
            backward = transition @ (emission[frame] * backward)
            backward /= backward.sum()
    return result
