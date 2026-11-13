"""Resolve the selected calibration mode without borrowing another camera's scale."""

import math
from dataclasses import replace


def view_scale(settings, view, axis="x", fallback=None):
    if settings.calibration_method in {"manual", "map"}:
        return positive_scale(settings.pixels_per_cm) or fallback
    node = (settings.view_calibration or {}).get(view, {})
    if isinstance(node, (int, float)):
        return positive_scale(node)
    if isinstance(node, dict):
        value = node.get(f"{axis}_pixels_per_cm", node.get("pixels_per_cm"))
        return positive_scale(value)
    return None


def positive_scale(value):
    try:
        value = float(value) if not isinstance(value, bool) else float("nan")
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def settings_for_view(settings, view):
    if settings.calibration_method != "per_view":
        return settings
    scale = view_scale(settings, view)
    if scale is None:
        raise ValueError(f"Set a calibration map or pixels per cm for the {view} camera in Calibration by view.")
    return replace(
        settings, pixels_per_cm=scale, calibration_method="manual", calibration_map_path=None, view_calibration=None
    )


def side_recording_scale(settings, normalized):
    """Estimate the requested segment in this camera, never in another view."""
    if settings.calibration_method in {"manual", "map"}:
        scale = positive_scale(settings.pixels_per_cm)
        if scale is None:
            raise ValueError("Pixels per cm must be finite and greater than zero.")
        normalized.attrs["spatial_calibration"] = {"method": settings.calibration_method, "pixels_per_cm": scale}
        return scale
    if settings.calibration_method != "reference":
        raise ValueError("Set pixels per cm or import a calibration map for this camera.")
    first, second = settings.reference_segment.split("_", 1)
    keys = [f"{part} {coord}" for part in (first, second) for coord in ("x", "y")]
    if not all(key in normalized for key in keys):
        raise ValueError(
            f"Calibration needs {first} and {second} in this camera; check mapping or import its calibration map."
        )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_validation import (
        resolve_calibration,
    )

    calibration = resolve_calibration(normalized, "reference", reference_segment=settings.reference_segment,
                                      reference_length_cm=settings.reference_length_cm)
    normalized.attrs["spatial_calibration"] = calibration
    return calibration["pixels_per_cm"]
