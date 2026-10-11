"""Resolve each camera's scale independently; preserve shared values for old profiles."""

import math
from dataclasses import replace


def view_scale(settings, view, axis="x", fallback=None):
    node = (settings.view_calibration or {}).get(view, {})
    if isinstance(node, (int, float)):
        return float(node) if math.isfinite(node) and node > 0 else fallback
    if isinstance(node, dict):
        value = node.get(f"{axis}_pixels_per_cm", node.get("pixels_per_cm"))
        if value and math.isfinite(float(value)) and float(value) > 0:
            return float(value)
    return fallback


def settings_for_view(settings, view):
    scale = view_scale(settings, view)
    return (
        replace(settings, pixels_per_cm=scale, calibration_method="manual", calibration_map_path=None)
        if scale
        else settings
    )


def side_recording_scale(settings, normalized):
    """Estimate the requested segment in this camera, never in another view."""
    import numpy as np
    import pandas as pd

    if settings.pixels_per_cm is not None:
        scale = float(settings.pixels_per_cm)
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("Pixels per cm must be finite and greater than zero.")
        return scale
    if settings.calibration_method != "reference":
        raise ValueError("Set pixels per cm or import a calibration map for this camera.")
    first, second = settings.reference_segment.split("_", 1)
    keys = [f"{part} {coord}" for part in (first, second) for coord in ("x", "y")]
    if not all(key in normalized for key in keys):
        raise ValueError(
            f"Calibration needs {first} and {second} in this camera; check mapping or import its calibration map."
        )
    x1, y1, x2, y2 = [pd.to_numeric(normalized[key], errors="coerce").to_numpy(float) for key in keys]
    distance = np.hypot(x1 - x2, y1 - y2)
    valid = np.isfinite(distance) & (distance > 0)
    for part in (first, second):
        likelihood = pd.to_numeric(normalized[f"{part} likelihood"], errors="coerce").to_numpy(float)
        if settings.likelihood_threshold > 0:
            valid &= np.isfinite(likelihood) & (likelihood >= settings.likelihood_threshold)
    if not valid.any() or not math.isfinite(settings.reference_length_cm) or settings.reference_length_cm <= 0:
        raise ValueError(
            "The reference segment has no usable length at the selected confidence cutoff. Import this camera’s map or check its reference markers and length."
        )
    return float(np.median(distance[valid]) / settings.reference_length_cm)
