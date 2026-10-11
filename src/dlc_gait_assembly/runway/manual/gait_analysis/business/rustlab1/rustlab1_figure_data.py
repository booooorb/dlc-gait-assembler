"""Prepare RustLab1 tracking, trajectory, and cycle data for figure renderers."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    coordinate_columns,
    prepare_alma_coordinates,
)


def rustlab1_figure_context(
    raw_dataframe, alma_parameters, extraction, settings, kinematics, np, pd, preprocessed=None
):
    columns = coordinate_columns(raw_dataframe)
    from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import view_scale

    preprocessed = preprocessed or prepare_alma_coordinates(raw_dataframe, settings, kinematics)
    markers = sorted({marker for (marker, _coord) in columns})
    raw: dict[str, dict[str, object]] = {}
    filtered: dict[str, dict[str, object]] = {}
    for marker in markers:
        raw[marker] = {}
        filtered[marker] = {}
        for coord in ("x", "y", "likelihood"):
            column = columns.get((marker, coord))
            raw[marker][coord] = (
                None if column is None else pd.to_numeric(raw_dataframe[column], errors="coerce").to_numpy(dtype=float)
            )
        for coord in ("x", "y"):
            filtered[marker][coord] = preprocessed.series.get(marker, {}).get(coord)
    scales = {side: view_scale(settings, side, "x", extraction.pixels_per_cm) for side in ("left", "right")}
    return {
        "np": np,
        "pd": pd,
        "markers": markers,
        "raw": raw,
        "filtered": filtered,
        "parameters": alma_parameters.reset_index(drop=True),
        "rustlab": extraction.dataframe.reset_index(drop=True),
        "pixels_per_cm": extraction.pixels_per_cm,
        "side_x_scales": scales,
        "bottom_pixels_per_cm": bottom_x_pixels_per_cm(settings, extraction.pixels_per_cm),
        "frame_rate": float(settings.frame_rate),
        "likelihood_threshold": float(getattr(settings, "likelihood_threshold", 0.0) or 0.0),
        "stance_speed_threshold_px_frame": float(getattr(settings, "stance_speed_threshold_px_frame", 7.0)),
        "maximum_tracking_speed_px_frame": float(getattr(settings, "maximum_tracking_speed_px_frame", 100.0)),
        "include_forelimb": getattr(settings, "limb_scope", "Hindlimb") == "Hindlimb + Forelimb",
    }


def bottom_x_pixels_per_cm(settings, fallback):
    configured = (getattr(settings, "view_calibration", None) or {}).get("bottom")
    if isinstance(configured, (int, float)) and float(configured) > 0:
        return float(configured)
    if isinstance(configured, dict):
        value = configured.get("x_pixels_per_cm", configured.get("pixels_per_cm"))
        if value and float(value) > 0:
            return float(value)
    return fallback


def marker_reliability(context, marker: str) -> float:
    np = context["np"]
    values = context["raw"][marker]
    likelihood = values.get("likelihood")
    if likelihood is not None and len(likelihood):
        finite = np.isfinite(likelihood)
        threshold = context["likelihood_threshold"]
        return float(np.mean(likelihood[finite] >= threshold) * 100.0) if finite.any() else 0.0
    available = [values.get(coord) for coord in ("x", "y") if values.get(coord) is not None]
    if not available:
        return 0.0
    n = min(len(array) for array in available)
    valid = np.ones(n, dtype=bool)
    for array in available:
        valid &= np.isfinite(array[:n])
    return float(np.mean(valid) * 100.0) if n else 0.0


def marker_view(marker: str) -> str:
    if marker.startswith("l-"):
        return "left"
    if marker.startswith("r-"):
        return "right"
    if marker.startswith("d-"):
        return "down"
    return "other"


def coordinate_mask(context, marker, x, y, *, filtered: bool):
    np = context["np"]
    n = min(len(x), len(y))
    mask = np.isfinite(x[:n]) & np.isfinite(y[:n])
    if filtered:
        likelihood = context["raw"].get(marker, {}).get("likelihood")
        if likelihood is not None:
            n = min(n, len(likelihood))
            threshold = context["likelihood_threshold"]
            mask = mask[:n] & np.isfinite(likelihood[:n]) & (likelihood[:n] >= threshold)
    return mask


def sample_indices(indices, maximum: int, np):
    if len(indices) <= maximum:
        return indices
    positions = np.linspace(0, len(indices) - 1, maximum, dtype=int)
    return indices[positions]


def numeric_column(context, dataframe, column: str):
    if column not in dataframe:
        return context["np"].array([], dtype=float)
    return context["pd"].to_numeric(dataframe[column], errors="coerce").to_numpy(dtype=float)


def gait_cycles(context):
    values = numeric_column(context, context["rustlab"], "gait_cycle")
    if len(values):
        return values
    return context["np"].arange(1, len(context["rustlab"]) + 1, dtype=float)


def down_paw_angles(context):
    """Bottom-center angles are retired from the four-paw workflow."""
    return {}


def forelimb_joint_angles(context, prefix: str):
    np = context["np"]
    points = {
        name: (
            context["filtered"].get(f"{prefix}-{name}", {}).get("x"),
            context["filtered"].get(f"{prefix}-{name}", {}).get("y"),
        )
        for name in ("shoulder", "elbow", "wrist", "front-toe-tip")
    }
    result = {}
    for label, center_name, first_name, second_name in (
        ("Elbow", "elbow", "wrist", "shoulder"),
        ("Wrist", "wrist", "front-toe-tip", "elbow"),
    ):
        arrays = (*points[center_name], *points[first_name], *points[second_name])
        if any(value is None for value in arrays):
            continue
        length = min(len(value) for value in arrays)
        (center_x, center_y) = (value[:length] for value in points[center_name])
        (first_x, first_y) = (value[:length] for value in points[first_name])
        (second_x, second_y) = (value[:length] for value in points[second_name])
        if prefix == "l":
            (center_y, first_y, second_y) = (-center_y, -first_y, -second_y)
        angle = np.abs(
            np.degrees(
                np.arctan2(first_y - center_y, first_x - center_x)
                - np.arctan2(second_y - center_y, second_x - center_x)
            )
        )
        result[label] = np.where(angle < 180.0, angle, np.nan)
    return result
