"""Resolve shared or independently estimated camera scales for post-ALMA measurements."""

from __future__ import annotations

from dataclasses import replace

from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import (
    positive_scale,
    side_recording_scale,
)


def resolve_pixels_per_cm(dataframe, columns, settings) -> tuple[float | None, str]:
    if settings.calibration_method in {"manual", "map"}:
        return positive_scale(settings.pixels_per_cm), f"{settings.calibration_method} calibration"
    return None, f"{settings.calibration_method} calibration by view"


def resolve_reference_scales(dataframe, columns, settings):
    """Use this camera's reference markers; unavailable cameras remain uncalibrated."""
    if settings.calibration_method != "reference":
        return settings
    import pandas as pd

    views = dict(settings.view_calibration or {})
    aliases = {"toe": "back-toe", "mtp": "back-mtp", "ankle": "back-ankle", "knee": "back-knee"}
    parts = settings.reference_segment.split("_", 1)
    for side, prefix in (("left", "l"), ("right", "r")):
        node = views.get(side, {})
        if isinstance(node, dict) and positive_scale(node.get("pixels_per_cm")):
            continue
        normalized = {}
        for part in parts:
            marker = f"{prefix}-{aliases.get(part, part)}"
            for axis in ("x", "y", "likelihood"):
                column = columns.get((marker, axis))
                if column is not None:
                    normalized[f"{part} {axis}"] = dataframe[column]
        try:
            scale = side_recording_scale(settings, pd.DataFrame(normalized))
        except (KeyError, ValueError):
            continue
        views[side] = {"pixels_per_cm": scale, "source": f"{side} {settings.reference_segment} reference"}
    return replace(settings, view_calibration=views or None)
