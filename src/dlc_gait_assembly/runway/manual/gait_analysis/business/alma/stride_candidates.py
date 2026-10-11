"""Experimental phase estimators. They label frames; none may transform plot geometry.

Original ALMA reference: sollan/alma, 89f7be705a730fc0c0acf90817357b6449535df0,
Functions/KinematicsFunctions.py:1084–1103 (GPL-3.0; resources/licenses/ALMA-LICENSE).
The original threshold and onset gates are retained; frame alignment, confidence-gap
exclusion and omission of the unfinished final cycle are explicit wrapper changes.
"""

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import (
    CONTEXT_MIXTURE_METHOD,
    contextual_stance_probability,
)

ORIGINAL_ALMA = "ALMA (original 2021)"
EXPERIMENTAL_METHODS = (
    ORIGINAL_ALMA,
    "Speed histogram (Otsu)",
    "Speed mixture (GMM)",
    CONTEXT_MIXTURE_METHOD,
    "Paw height mixture (GMM)",
    "Hip-relative velocity",
    "Height + speed contact",
    "Temporal speed + height",
)
RELATIVE_METHODS = ("Paw excursion peaks", "Hip-relative velocity")


def original_alma_detection(x, likelihood, trusted):
    x = np.asarray(x, float)
    # A displacement into frame t is attached to source frame t, not t-1.
    delta = np.diff(x)
    stance = np.r_[False, np.abs(delta) <= 0.001] & trusted
    starts = []
    for i in range(2, len(x)):
        source_index = i - 1
        if stance[i] and not stance[i - 1] and likelihood[source_index] > 0.6:
            if not starts or abs(x[starts[-1] - 1] - x[source_index]) > 20:
                starts.append(i)
    complete = [
        (a, b - 1) for a, b in zip(starts[:-1], starts[1:], strict=True) if trusted[a : b + 1].all() and b - a > 1
    ]
    return stance, [a for a, _ in complete], [b for _, b in complete]


def _mixture_probability(values, trusted, *, high_is_contact=False):
    finite = trusted & np.isfinite(values)
    if finite.sum() < 6 or np.ptp(values[finite]) < 1e-5:
        return np.ones(len(values))
    model = GaussianMixture(n_components=2, random_state=0, reg_covar=1e-5, n_init=3)
    model.fit(values[finite, None])
    component = int(np.argmax(model.means_) if high_is_contact else np.argmin(model.means_))
    probability = np.zeros(len(values))
    probability[finite] = model.predict_proba(values[finite, None])[:, component]
    return probability


def _otsu_threshold(values):
    histogram, edges = np.histogram(values, bins=64)
    centers = (edges[:-1] + edges[1:]) / 2
    weight = np.cumsum(histogram).astype(float)
    total = weight[-1]
    mean_sum = np.cumsum(histogram * centers)
    denominator = weight * (total - weight)
    between = np.divide(
        (mean_sum[-1] * weight - mean_sum * total) ** 2, denominator, out=np.zeros_like(weight), where=denominator > 0
    )
    return centers[int(np.argmax(between))]


def _local_range(values, trusted, fps):
    window = max(7, round(fps * 0.5) | 1)
    series = pd.Series(np.where(trusted, values, np.nan))
    low = series.rolling(window, center=True, min_periods=3).quantile(0.1)
    high = series.rolling(window, center=True, min_periods=3).quantile(0.9)
    lo = low.fillna(float(np.quantile(values[trusted], 0.1))).to_numpy()
    hi = high.fillna(float(np.quantile(values[trusted], 0.9))).to_numpy()
    return np.clip((values - lo) / np.maximum(hi - lo, 0.01), 0, 1)


def _temporal_labels(contact_probability, trusted):
    """Two-state dynamic programming; 2.5 log-cost penalty per phase transition.

    Restart at every untrusted interval so a dropout cannot dictate the next phase.
    This is a transparent motion model, not a trained or validated contact classifier.
    """
    stance = np.zeros(len(trusted), bool)
    edges = np.diff(np.r_[False, trusted, False].astype(int))
    for start, stop in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
        p = np.clip(contact_probability[start:stop], 0.02, 0.98)
        emissions = -np.log(np.column_stack((1 - p, p)))
        cost = emissions[0]
        back = np.zeros((len(p), 2), int)
        for frame in range(1, len(p)):
            candidates = cost[:, None] + np.array([[0, 2.5], [2.5, 0]])
            back[frame] = candidates.argmin(axis=0)
            cost = candidates.min(axis=0) + emissions[frame]
        state = int(cost.argmin())
        for frame in range(len(p) - 1, -1, -1):
            stance[start + frame] = state == 1
            state = back[frame, state]
    return stance


def candidate_stance(method, x, y, speed, trusted, fps, relative_x, direction, *, diagnostics=None, context_ms=60.0):
    log_speed = np.log1p(speed)
    if method == "Speed histogram (Otsu)":
        return log_speed <= _otsu_threshold(log_speed[trusted])
    if method in ("Speed mixture (GMM)", CONTEXT_MIXTURE_METHOD):
        probability = _mixture_probability(log_speed, trusted)
        if method == CONTEXT_MIXTURE_METHOD:
            # Degenerate mixtures do not identify two phases. Preserve uncertainty.
            if trusted.sum() < 6 or np.ptp(log_speed[trusted]) < 1e-5:
                probability = np.full(len(speed), 0.5)
            posterior = contextual_stance_probability(probability, trusted, fps, context_ms)
            if diagnostics is not None:
                diagnostics.update(
                    raw_stance_probability=np.where(trusted, probability, np.nan),
                    stance_probability=posterior,
                    phase_confidence=np.maximum(posterior, 1 - posterior),
                    mixture_context_ms=context_ms,
                )
            return posterior >= 0.5
        return probability >= 0.5
    if method == "Paw height mixture (GMM)":
        # Image y increases downwards: the lower spatial cluster is contact.
        return _mixture_probability(y, trusted, high_is_contact=True) >= 0.5
    if method == "Hip-relative velocity":
        if relative_x is None:
            raise ValueError("Hip-relative velocity requires a tracked hip reference.")
        velocity = np.gradient(relative_x) * direction
        return velocity <= 0
    speed_fraction = _local_range(speed, trusted, fps)
    height_fraction = _local_range(y, trusted, fps)
    if method == "Height + speed contact":
        return (height_fraction >= 0.55) & (speed_fraction <= 0.55)
    if method == "Temporal speed + height":
        probability = 0.6 * (1 - speed_fraction) + 0.4 * height_fraction
        return _temporal_labels(probability, trusted)
    raise ValueError(f"Unknown stride detection method: {method}")
