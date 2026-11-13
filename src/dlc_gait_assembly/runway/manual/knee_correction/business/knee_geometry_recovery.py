"""Recover feasible frame-local knee geometry and explicitly untrusted display positions."""

from __future__ import annotations

import numpy as np

# Adult wild-type values: female 14.6/17.6 mm, male 15.0/18.2 mm.
# This is an editable fallback prior, not a measurement of an individual animal
# or a claim that projected 2-D segment lengths equal physical bone lengths.
MOUSE_FEMUR_TIBIA_RATIO = 0.83
MOUSE_RATIO_SOURCE = "https://www.jci.org/articles/view/6730"


def feasible_frame_lengths(distance: float, femur: float, tibia: float, ratio: float) -> tuple[float, float]:
    """Adjust only this frame, preserving the fallback femur/tibia ratio.

    For a fixed ratio, the triangle inequality bounds the *total* length on
    both sides. Too-distant endpoints require a larger total; too-close
    endpoints may require a smaller total. Increasing both lengths cannot
    repair every too-close configuration. A small margin avoids tangency.
    """
    femur_fraction = ratio / (1.0 + ratio)
    tibia_fraction = 1.0 / (1.0 + ratio)
    difference = abs(femur_fraction - tibia_fraction)
    margin = 0.01
    lower = distance * (1.0 + margin)
    upper = distance / difference * (1.0 - margin) if difference > 1e-12 else np.inf
    if upper <= lower:
        total = distance * 2.0 / (1.0 + difference)
    else:
        total = float(np.clip(femur + tibia, lower, upper))
    return total * femur_fraction, total * tibia_fraction


def display_fallbacks(coordinates, statuses, methods):
    """Fill unresolved positions from finite neighbours, with confidence assigned zero by the caller.

    Internal gaps are linearly interpolated; edges use the nearest available
    position. These are display placeholders and carry no measurement support.
    A recording with no finite knee anchors stays missing rather than inventing
    an arbitrary location.
    """
    finite = np.isfinite(coordinates).all(axis=1)
    if not finite.any():
        return np.zeros(len(coordinates), dtype=bool)
    missing = ~finite
    positions = np.arange(len(coordinates))
    for axis in (0, 1):
        coordinates[missing, axis] = np.interp(positions[missing], positions[finite], coordinates[finite, axis])
    for index in np.flatnonzero(missing):
        statuses[index] = f"Estimated: temporal display fallback ({statuses[index]})"
        methods[index] = "temporal_display"
    return missing
