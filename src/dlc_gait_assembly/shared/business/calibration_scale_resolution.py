"""Resolve per-view, per-axis, and overall spatial scales from an already-loaded conversion map."""

from __future__ import annotations

from dlc_gait_assembly.shared.business.calibration_map_contracts import CalibrationConversionMap


def pixels_per_cm_from_conversion_node(node: dict | None) -> float | None:
    if not node:
        return None
    for key in ("mean_pixels_per_centimeter", "pixels_per_centimeter"):
        value = node.get(key)
        if value:
            return float(value)
    centimeters_per_pixel = node.get("centimeters_per_pixel")
    if centimeters_per_pixel:
        return 1.0 / float(centimeters_per_pixel)
    axis_values = [node.get("recommended_x_centimeters_per_pixel"), node.get("recommended_y_centimeters_per_pixel")]
    axis_values = [float(value) for value in axis_values if value]
    if axis_values:
        return 1.0 / (sum(axis_values) / len(axis_values))
    return None


def resolve_calibration_scale(payload: CalibrationConversionMap, view_index: int | None = None) -> tuple[float, str]:
    conversion_map = payload.get("conversion_factor_map", payload)
    if view_index is not None:
        view = conversion_map.get("views", {}).get(str(view_index))
        value = pixels_per_cm_from_conversion_node(view)
        if value is not None:
            return (value, f"view {view_index}")
    overall_value = pixels_per_cm_from_conversion_node(conversion_map.get("overall"))
    if overall_value is not None:
        return (overall_value, "overall")
    for key, view in sorted(conversion_map.get("views", {}).items(), key=lambda item: int(item[0])):
        value = pixels_per_cm_from_conversion_node(view)
        if value is not None:
            return (value, f"view {key}")
    raise ValueError("Could not find a usable pixels-per-centimeter value in calibration map")
