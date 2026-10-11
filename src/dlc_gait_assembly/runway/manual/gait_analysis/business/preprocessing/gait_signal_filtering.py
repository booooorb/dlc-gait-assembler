"""Interpolate and Butterworth-filter marker series using the established preprocessing contract."""

from __future__ import annotations


def filtered_series(dataframe, columns, marker, coord, settings, kinematics):
    import numpy as np
    import pandas as pd

    column = columns.get((marker, coord))
    if column is None:
        return None
    values = pd.to_numeric(dataframe[column], errors="coerce").astype(float)
    likelihood_column = columns.get((marker, "likelihood"))
    likelihood_threshold = float(getattr(settings, "likelihood_threshold", 0.0) or 0.0)
    if likelihood_column is not None and likelihood_threshold > 0:
        likelihood = pd.to_numeric(dataframe[likelihood_column], errors="coerce")
        valid = likelihood.ge(likelihood_threshold).fillna(False)
        values = values.mask(~valid)
    values = values.interpolate(limit_direction="both")
    array = values.to_numpy(dtype=float)
    if np.count_nonzero(np.isfinite(array)) < 2:
        return array
    try:
        return np.asarray(
            kinematics.butterworth_filter(array, settings.frame_rate, settings.filter_cutoff), dtype=float
        )
    except (ValueError, TypeError):
        return array


def validate_preprocessed_coordinates(preprocessed, raw_dataframe, settings) -> None:
    expected = (
        len(raw_dataframe),
        float(getattr(settings, "likelihood_threshold", 0.0) or 0.0),
        float(settings.frame_rate),
        float(settings.filter_cutoff),
    )
    actual = (
        preprocessed.frame_count,
        preprocessed.likelihood_threshold,
        preprocessed.frame_rate,
        preprocessed.filter_cutoff,
    )
    if actual != expected:
        raise ValueError("Preprocessed coordinates do not match the current ALMA frame count or filtering settings.")
