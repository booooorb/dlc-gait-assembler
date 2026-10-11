"""Calculate candidate knee positions from the two segment lengths and endpoint geometry."""

from __future__ import annotations

import numpy as np


def triangulated_knees(
    hips: np.ndarray,
    ankles: np.ndarray,
    raw_knees: np.ndarray,
    hip_coordinates_valid: np.ndarray,
    ankle_coordinates_valid: np.ndarray,
    hip_likelihood_valid: np.ndarray,
    ankle_likelihood_valid: np.ndarray,
    hip_knee_length: float,
    knee_ankle_length: float,
    knee_direction: str,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    output = raw_knees.copy()
    corrected = np.zeros(len(output), dtype=bool)
    statuses = ["Not evaluated"] * len(output)
    previous: np.ndarray | None = None
    preferred_signs = []
    for hip, ankle, knee in zip(hips, ankles, raw_knees, strict=False):
        if np.isfinite(hip).all() and np.isfinite(ankle).all() and np.isfinite(knee).all():
            cross = np.cross(ankle - hip, knee - hip)
            if cross != 0:
                preferred_signs.append(float(np.sign(cross)))
    preferred_sign = float(np.sign(np.median(preferred_signs))) if preferred_signs else 1.0
    for index, (hip, ankle, raw_knee) in enumerate(zip(hips, ankles, raw_knees, strict=False)):
        if not hip_coordinates_valid[index]:
            statuses[index] = "Missing hip coordinates"
            continue
        if not ankle_coordinates_valid[index]:
            statuses[index] = "Missing ankle coordinates"
            continue
        if not hip_likelihood_valid[index]:
            statuses[index] = "Low-confidence hip"
            continue
        if not ankle_likelihood_valid[index]:
            statuses[index] = "Low-confidence ankle"
            continue
        delta = ankle - hip
        distance = float(np.linalg.norm(delta))
        if distance <= 0:
            statuses[index] = "Zero hip–ankle distance"
            continue
        if distance > hip_knee_length + knee_ankle_length:
            statuses[index] = "Segment lengths cannot form a triangle"
            continue
        if distance < abs(hip_knee_length - knee_ankle_length):
            statuses[index] = "Segment lengths cannot form a triangle"
            continue
        unit = delta / distance
        along = (hip_knee_length**2 - knee_ankle_length**2 + distance**2) / (2 * distance)
        perpendicular_distance_sq = hip_knee_length**2 - along**2
        if not np.isfinite(perpendicular_distance_sq) or perpendicular_distance_sq < -1e-08:
            statuses[index] = "No valid circle intersection"
            continue
        perpendicular_distance = float(np.sqrt(max(0.0, perpendicular_distance_sq)))
        base = hip + along * unit
        perpendicular = np.array([-unit[1], unit[0]])
        candidates = (base + perpendicular_distance * perpendicular, base - perpendicular_distance * perpendicular)
        if knee_direction == "positive":
            chosen = candidates[0]
        elif knee_direction == "negative":
            chosen = candidates[1]
        elif np.isfinite(raw_knee).all():
            reference = raw_knee
            chosen = min(candidates, key=lambda candidate: np.linalg.norm(candidate - reference))
        elif previous is not None:
            chosen = min(candidates, key=lambda candidate: np.linalg.norm(candidate - previous))
        else:
            chosen = candidates[0] if preferred_sign >= 0 else candidates[1]
        output[index] = chosen
        corrected[index] = True
        statuses[index] = "Corrected"
        previous = chosen
    return (output, corrected, tuple(statuses))
