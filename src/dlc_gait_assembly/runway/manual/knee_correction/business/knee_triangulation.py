"""Calculate knees from endpoint geometry, keeping confidence-aware local recovery explicit."""

from __future__ import annotations

import numpy as np

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_geometry_recovery import (
    MOUSE_FEMUR_TIBIA_RATIO,
    display_fallbacks,
    feasible_frame_lengths,
)


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
    *,
    adapt_infeasible_lengths: bool = True,
    fallback_femur_tibia_ratio: float = MOUSE_FEMUR_TIBIA_RATIO,
    fill_missing_coordinates: bool = True,
    diagnostics: dict | None = None,
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...]]:
    output = raw_knees.copy()
    corrected = np.zeros(len(output), dtype=bool)
    statuses = ["Not evaluated"] * len(output)
    methods = np.where(np.isfinite(raw_knees).all(axis=1), "retained_original", "unavailable").astype(object)
    frame_lengths = np.full((len(output), 2), np.nan)
    length_penalties = np.ones(len(output))
    previous: np.ndarray | None = None
    preferred_signs = []
    for hip, ankle, knee in zip(hips, ankles, raw_knees, strict=True):
        if np.isfinite(hip).all() and np.isfinite(ankle).all() and np.isfinite(knee).all():
            delta, offset = ankle - hip, knee - hip
            cross = delta[0] * offset[1] - delta[1] * offset[0]
            if cross != 0:
                preferred_signs.append(float(np.sign(cross)))
    preferred_sign = float(np.sign(np.median(preferred_signs))) if preferred_signs else 1.0
    for index, (hip, ankle, raw_knee) in enumerate(zip(hips, ankles, raw_knees, strict=True)):
        if not hip_coordinates_valid[index]:
            statuses[index] = "Missing hip coordinates"
            continue
        if not ankle_coordinates_valid[index]:
            statuses[index] = "Missing ankle coordinates"
            continue
        low_sources = []
        if not hip_likelihood_valid[index]:
            low_sources.append("hip")
        if not ankle_likelihood_valid[index]:
            low_sources.append("ankle")
        delta = ankle - hip
        distance = float(np.linalg.norm(delta))
        if not np.isfinite(distance) or distance <= 0:
            statuses[index] = "Zero hip–ankle distance" if distance == 0 else "Non-finite hip–ankle distance"
            continue
        femur, tibia = hip_knee_length, knee_ankle_length
        adjusted = distance > femur + tibia or distance < abs(femur - tibia)
        if adjusted:
            if not adapt_infeasible_lengths:
                statuses[index] = "Segment lengths cannot form a triangle"
                continue
            femur, tibia = feasible_frame_lengths(distance, femur, tibia, fallback_femur_tibia_ratio)
            length_penalties[index] = min(
                femur / hip_knee_length,
                hip_knee_length / femur,
                tibia / knee_ankle_length,
                knee_ankle_length / tibia,
            )
        unit = delta / distance
        along = (femur**2 - tibia**2 + distance**2) / (2 * distance)
        perpendicular_distance_sq = femur**2 - along**2
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
            chosen = min(candidates, key=lambda candidate: np.linalg.norm(candidate - raw_knee))
        elif previous is not None:
            chosen = min(candidates, key=lambda candidate: np.linalg.norm(candidate - previous))
        else:
            chosen = candidates[0] if preferred_sign >= 0 else candidates[1]
        output[index] = chosen
        corrected[index] = True
        methods[index] = "adjusted_geometry" if adjusted else "configured_geometry"
        frame_lengths[index] = femur, tibia
        details = []
        if adjusted:
            details.append("frame-local segment lengths adjusted")
        if low_sources:
            details.append("low-confidence " + "/".join(low_sources))
        statuses[index] = "Estimated: " + "; ".join(details) if details else "Corrected"
        if not low_sources and not adjusted:
            previous = chosen
    if fill_missing_coordinates:
        corrected |= display_fallbacks(output, statuses, methods)
    if diagnostics is not None:
        diagnostics.update(methods=methods, frame_lengths=frame_lengths, length_penalties=length_penalties)
    return output, corrected, tuple(statuses)
