"""Apply already-resolved spatial calibration to side and bottom coordinate measurements."""

from __future__ import annotations


def resolve_pixels_per_cm(dataframe, columns, settings) -> tuple[float | None, str]:
    import numpy as np
    import pandas as pd

    if settings.calibration_method == "manual" and settings.pixels_per_cm:
        return (float(settings.pixels_per_cm), "manual calibration")
    (first, second) = settings.reference_segment.split("_", 1)
    aliases = {"toe": "back-toe", "mtp": "back-mtp", "ankle": "back-ankle", "knee": "back-knee"}
    (first, second) = (aliases.get(first, first), aliases.get(second, second))
    for prefix in ("l", "r"):
        (marker_a, marker_b) = (f"{prefix}-{first}", f"{prefix}-{second}")
        required = [(marker_a, "x"), (marker_a, "y"), (marker_b, "x"), (marker_b, "y")]
        if not all(key in columns for key in required):
            continue
        arrays = [pd.to_numeric(dataframe[columns[key]], errors="coerce").to_numpy(float) for key in required]
        distance = np.sqrt((arrays[0] - arrays[2]) ** 2 + (arrays[1] - arrays[3]) ** 2)
        likelihoods = []
        for marker in (marker_a, marker_b):
            likelihood_column = columns.get((marker, "likelihood"))
            if likelihood_column is not None:
                likelihoods.append(pd.to_numeric(dataframe[likelihood_column], errors="coerce").to_numpy(float))
        valid = np.isfinite(distance)
        for likelihood in likelihoods:
            valid &= likelihood >= 0.9
        if np.count_nonzero(valid):
            value = float(np.nanmedian(distance[valid]) / settings.reference_length_cm)
            return (value, f"{prefix}-{settings.reference_segment} reference")
    if settings.pixels_per_cm:
        return (float(settings.pixels_per_cm), "configured pixel ratio fallback")
    return (49.143, "ALMA 49.143 px/cm fallback (reference markers unavailable)")
