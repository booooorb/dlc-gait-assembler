"""Resolve file-backed calibration once, before preview or measurement."""

from dataclasses import replace

from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import positive_scale
from dlc_gait_assembly.shared.business.calibration_scale_resolution import resolve_calibration_scale
from dlc_gait_assembly.shared.infrastructure.calibration_map_codec import read_calibration_map


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


def resolve_calibration_settings(settings, *, allow_unscaled=False):
    """Resolve only the active mode; saved numbers are portable map snapshots."""
    method = settings.calibration_method
    if method not in {"reference", "manual", "map", "per_view", "treadmill"}:
        raise ValueError(f"Unsupported calibration method: {method}")
    if method in {"reference", "treadmill"}:
        return replace(settings, pixels_per_cm=None, calibration_map_path=None, view_calibration=None)
    if method in {"manual", "map"}:
        scale = positive_scale(settings.pixels_per_cm)
        if method == "map" and scale is None and settings.calibration_map_path:
            scales, _ = camera_map_scales(settings.calibration_map_path)
            scale = scales["pixels_per_cm"]
        # Legacy path-only manual settings still load their explicitly supplied map.
        if method == "manual" and scale is None and settings.calibration_map_path:
            scales, _ = camera_map_scales(settings.calibration_map_path)
            scale = scales["pixels_per_cm"]
            method = "map"
        if scale is None:
            # Standalone RustLab1 may intentionally export uncalibrated pixel data.
            if allow_unscaled and method == "manual" and settings.pixels_per_cm is None:
                return replace(settings, view_calibration=None)
            raise ValueError("Set a finite, positive pixels-per-cm scale or import a calibration map.")
        return replace(
            settings,
            pixels_per_cm=scale,
            calibration_method=method,
            view_calibration=None,
            calibration_map_path=settings.calibration_map_path if method == "map" else None,
        )
    views = dict(settings.view_calibration or {})
    for view, node in views.items():
        if isinstance(node, (int, float)):
            if positive_scale(node) is None:
                raise ValueError(f"Invalid {view} calibration: pixels per cm must be finite and positive.")
            continue
        if not isinstance(node, dict):
            raise ValueError(f"Invalid {view} calibration settings.")
        keys = ("pixels_per_cm", "x_pixels_per_cm", "y_pixels_per_cm")
        for key in keys:
            if key in node and positive_scale(node[key]) is None:
                raise ValueError(f"Invalid {view} {key}: the scale must be finite and positive.")
        complete = positive_scale(node.get("pixels_per_cm")) is not None or all(
            positive_scale(node.get(f"{axis}_pixels_per_cm")) for axis in ("x", "y")
        )
        if complete or not node.get("map_path"):
            continue
        index = node.get("view_index")
        if index is None and str(node.get("source", "")).startswith("view "):
            index = str(node["source"]).removeprefix("view ")
        scales, source = camera_map_scales(node["map_path"], index, require_camera=True)
        # ALMA uses one isotropic scale per side; the bottom retains both axes.
        values = scales if view == "bottom" else {"pixels_per_cm": scales["pixels_per_cm"]}
        views[view] = {**node, **values, "source": source}
    return replace(settings, pixels_per_cm=None, calibration_map_path=None, view_calibration=views or None)
