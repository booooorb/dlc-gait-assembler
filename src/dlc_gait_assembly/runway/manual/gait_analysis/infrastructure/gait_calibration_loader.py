"""Resolve file-backed calibration once, before preview or measurement."""

import math
from dataclasses import replace

from dlc_gait_assembly.shared.business.calibration_scale_resolution import resolve_calibration_scale
from dlc_gait_assembly.shared.infrastructure.calibration_map_codec import read_calibration_map


def positive_scale(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def camera_map_scales(path, view_index=None, *, require_camera=False):
    payload = read_calibration_map(path)
    conversion = payload.get("conversion_factor_map", payload)
    nodes = conversion.get("views", {})
    if require_camera and view_index is None:
        if len(nodes) > 1:
            raise ValueError(f"Choose the camera/view index for this separate calibration map: {path}")
        if nodes:
            view_index = next(iter(nodes))
    if view_index is not None and str(view_index) not in conversion.get("views", {}):
        raise ValueError(f"Calibration map has no view {view_index}: {path}")
    scalar, source = resolve_calibration_scale(payload, view_index)
    if positive_scale(scalar) is None:
        raise ValueError(f"Calibration must contain a finite, positive scale: {path}")
    node = (
        conversion.get("overall", {})
        if source == "overall"
        else conversion.get("views", {}).get(source.removeprefix("view "), {})
    )
    scales = {"pixels_per_cm": scalar}
    for axis in ("x", "y"):
        cm_per_px = positive_scale(node.get(f"recommended_{axis}_centimeters_per_pixel"))
        scales[f"{axis}_pixels_per_cm"] = 1 / cm_per_px if cm_per_px else scalar
    return scales, source


def resolve_calibration_settings(settings):
    """Saved numeric scales are snapshots; paths are loaded when no scale is saved."""
    changes = {}
    shared_path = getattr(settings, "calibration_map_path", None)
    if shared_path and settings.calibration_method == "manual" and positive_scale(settings.pixels_per_cm) is None:
        scales, _ = camera_map_scales(shared_path)
        changes.update(pixels_per_cm=scales["pixels_per_cm"], calibration_method="manual")
    views = dict(settings.view_calibration or {})
    for view, node in views.items():
        if not isinstance(node, dict) or not node.get("map_path"):
            continue
        if any(positive_scale(node.get(key)) for key in ("pixels_per_cm", "x_pixels_per_cm", "y_pixels_per_cm")):
            continue
        index = node.get("view_index")
        if index is None and str(node.get("source", "")).startswith("view "):
            index = str(node["source"]).removeprefix("view ")
        scales, source = camera_map_scales(node["map_path"], index, require_camera=True)
        # ALMA uses one isotropic scale per side; the bottom retains both axes.
        values = scales if view == "bottom" else {"pixels_per_cm": scales["pixels_per_cm"]}
        views[view] = {**node, **values, "source": source}
    changes["view_calibration"] = views or None
    return replace(settings, **changes)
