"""Apply knee direction and confidence rules while preserving coordinate-table structure."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import (
    KneeCorrectionSettings,
    KneeMarkerReport,
)
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_marker_matching import (
    coordinate_columns as _coordinate_columns,
)
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_marker_matching import knee_targets as _knee_targets
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_marker_matching import (
    new_knee_columns as _new_knee_columns,
)
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_marker_matching import (
    normalised_knee_direction as _normalised_knee_direction,
)
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_marker_matching import (
    selected_or_matching_bodypart as _selected_or_matching_bodypart,
)
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_triangulation import (
    triangulated_knees as _triangulated_knees,
)
from dlc_gait_assembly.shared.business.coordinate_table_contracts import validate_dlc_dataframe
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS

COORDINATE_EXTENSIONS = {".csv", ".h5"}
PAIR_EXTENSIONS = COORDINATE_EXTENSIONS | VIDEO_EXTENSIONS


def correct_knee_dataframe(
    dataframe: pd.DataFrame, settings: KneeCorrectionSettings
) -> tuple[pd.DataFrame, tuple[KneeMarkerReport, ...]]:
    validate_dlc_dataframe(dataframe, Path("coordinates"))
    columns = _coordinate_columns(dataframe)
    corrected = dataframe.copy()
    reports: list[KneeMarkerReport] = []
    knee_targets = _knee_targets(columns, settings)
    if not knee_targets:
        raise ValueError(
            'No knee label could be corrected. Select hip and ankle labels, or add labels containing "hip" and "ankle".'
        )
    direction = _normalised_knee_direction(settings.knee_direction)
    if not np.isfinite(settings.pixels_per_cm) or settings.pixels_per_cm <= 0:
        raise ValueError("Calibration pixels per centimeter must be greater than zero.")
    hip_knee_length = float(settings.hip_knee_length_cm * settings.pixels_per_cm)
    knee_ankle_length = float(settings.knee_ankle_length_cm * settings.pixels_per_cm)
    if not np.isfinite([hip_knee_length, knee_ankle_length]).all() or min(hip_knee_length, knee_ankle_length) <= 0:
        raise ValueError("Femur and tibia/fibula lengths must be greater than zero.")
    if not np.isfinite(settings.fallback_femur_tibia_ratio) or settings.fallback_femur_tibia_ratio <= 0:
        raise ValueError("Fallback femur/tibia ratio must be finite and greater than zero.")
    if not np.isfinite(settings.adjusted_confidence_cap) or not 0 <= settings.adjusted_confidence_cap <= 1:
        raise ValueError("Adjusted-frame confidence cap must be between zero and one.")
    if not np.isfinite(settings.likelihood_threshold) or not 0 <= settings.likelihood_threshold <= 1:
        raise ValueError("Hip/ankle likelihood threshold must be between zero and one.")
    for prefix, bodypart in knee_targets:
        knee_columns = columns.get((prefix, bodypart))
        if knee_columns is None or not {"x", "y"}.issubset(knee_columns):
            knee_columns = _new_knee_columns(dataframe, prefix, bodypart)
            raw_knee = np.full((len(dataframe), 2), np.nan, dtype=float)
        else:
            raw_knee = xy_values(dataframe, knee_columns)
            ensure_float_columns(corrected, knee_columns)
        hip = _selected_or_matching_bodypart(bodypart, "hip", settings.hip_bodypart, prefix, columns)
        ankle = _selected_or_matching_bodypart(bodypart, "ankle", settings.ankle_bodypart, prefix, columns)
        hip_columns = columns[prefix, hip]
        ankle_columns = columns[prefix, ankle]
        hip_values = xy_values(dataframe, hip_columns)
        ankle_values = xy_values(dataframe, ankle_columns)
        hip_coordinates_valid = np.isfinite(hip_values).all(axis=1)
        ankle_coordinates_valid = np.isfinite(ankle_values).all(axis=1)
        hip_likelihood_valid = likelihood_mask(dataframe, hip_columns, settings.likelihood_threshold)
        ankle_likelihood_valid = likelihood_mask(dataframe, ankle_columns, settings.likelihood_threshold)
        diagnostics = {}
        (new_knee, corrected_mask, frame_statuses) = _triangulated_knees(
            hip_values,
            ankle_values,
            raw_knee,
            hip_coordinates_valid,
            ankle_coordinates_valid,
            hip_likelihood_valid,
            ankle_likelihood_valid,
            hip_knee_length,
            knee_ankle_length,
            direction,
            adapt_infeasible_lengths=settings.adapt_infeasible_lengths,
            fallback_femur_tibia_ratio=settings.fallback_femur_tibia_ratio,
            fill_missing_coordinates=settings.fill_missing_coordinates,
            diagnostics=diagnostics,
        )
        corrected.loc[:, knee_columns["x"]] = new_knee[:, 0]
        corrected.loc[:, knee_columns["y"]] = new_knee[:, 1]
        if "likelihood" in knee_columns:
            output_likelihood = dataframe.loc[:, knee_columns["likelihood"]].to_numpy(dtype=float, copy=True)
        else:
            knee_columns["likelihood"] = (*prefix, bodypart, "likelihood")
            output_likelihood = np.full(len(dataframe), np.nan, dtype=float)
        # Reconstructed points inherit the weaker endpoint; reconstruction is
        # never evidence for replacing a low source likelihood with 1.0.
        source_confidence = np.minimum(
            confidence_values(dataframe, hip_columns), confidence_values(dataframe, ankle_columns)
        )
        source_confidence[~hip_coordinates_valid | ~ankle_coordinates_valid] = 0.0
        output_likelihood = np.minimum(
            np.nan_to_num(output_likelihood, nan=0.0, posinf=0.0, neginf=0.0).clip(0.0, 1.0),
            source_confidence,
        )
        methods = diagnostics["methods"]
        configured = methods == "configured_geometry"
        adjusted = methods == "adjusted_geometry"
        output_likelihood[configured] = source_confidence[configured]
        output_likelihood[adjusted] = np.minimum(
            source_confidence[adjusted] * diagnostics["length_penalties"][adjusted],
            settings.adjusted_confidence_cap,
        )
        output_likelihood[np.isin(methods, ("temporal_display", "unavailable"))] = 0.0
        corrected.loc[:, knee_columns["likelihood"]] = output_likelihood
        reports.append(
            KneeMarkerReport(
                knee=bodypart,
                hip=hip,
                ankle=ankle,
                hip_knee_length=hip_knee_length,
                knee_ankle_length=knee_ankle_length,
                corrected_frames=int(corrected_mask.sum()),
                retained_frames=int((~corrected_mask).sum()),
                frame_statuses=frame_statuses,
                frame_methods=tuple(str(method) for method in methods),
                frame_confidences=tuple(float(value) for value in output_likelihood),
                frame_lengths=tuple(
                    tuple(float(value) if np.isfinite(value) else None for value in lengths)
                    for lengths in diagnostics["frame_lengths"]
                ),
                fallback_femur_tibia_ratio=settings.fallback_femur_tibia_ratio,
                source_likelihood_threshold=settings.likelihood_threshold,
                adjusted_confidence_cap=settings.adjusted_confidence_cap,
            )
        )
    corrected.columns = pd.MultiIndex.from_tuples(
        [tuple(column) for column in corrected.columns], names=dataframe.columns.names
    )
    return (corrected, tuple(reports))


def xy_values(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> np.ndarray:
    return dataframe.loc[:, [columns["x"], columns["y"]]].to_numpy(dtype=float, copy=True)


def ensure_float_columns(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> None:
    for coordinate in ("x", "y", "likelihood"):
        column = columns.get(coordinate)
        if column is not None and column in dataframe.columns:
            dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce").astype(float)


def likelihood_values(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> np.ndarray:
    if "likelihood" not in columns:
        return np.ones(len(dataframe), dtype=float)
    return dataframe.loc[:, columns["likelihood"]].to_numpy(dtype=float, copy=True)


def likelihood_mask(dataframe: pd.DataFrame, columns: dict[str, tuple], threshold: float) -> np.ndarray:
    values = likelihood_values(dataframe, columns)
    return np.isfinite(values) & (values >= threshold)


def confidence_values(dataframe: pd.DataFrame, columns: dict[str, tuple]) -> np.ndarray:
    if "likelihood" not in columns:
        return np.zeros(len(dataframe), dtype=float)
    return np.nan_to_num(likelihood_values(dataframe, columns), nan=0.0, posinf=0.0, neginf=0.0).clip(0.0, 1.0)
