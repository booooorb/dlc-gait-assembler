"""Represent frame corrections and rank predictions for manual review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_coordinate_correction import xy_values
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_marker_matching import (
    coordinate_columns,
    knee_targets,
    selected_or_matching_bodypart,
)

Marker = tuple[str, ...]
Point = tuple[float, float]


@dataclass(frozen=True)
class LabelReviewSource:
    region: str
    video: Path
    csv: Path
    h5: Path
    model: Path


@dataclass(frozen=True)
class LabelEdit:
    region: str
    video: Path
    frame: int
    marker: Marker
    point: Point | None

    @property
    def key(self):
        return self.region, self.video, self.frame, self.marker

    @classmethod
    def from_record(cls, record):
        point = record["point"]
        return cls(
            record["region"],
            Path(record["video"]),
            record["frame"],
            tuple(record["marker"]),
            tuple(point) if point is not None else None,
        )


@dataclass(frozen=True)
class LabelCorrection:
    edits: tuple[LabelEdit, ...]
    fine_tune: bool


def marker_columns(table):
    return {
        (*prefix[1:], bodypart): cols
        for (prefix, bodypart), cols in coordinate_columns(table).items()
        if {"x", "y"} <= cols.keys()
    }


def frame_positions(table, columns, frame):
    row = table.iloc[frame]
    points = {}
    for marker, cols in columns.items():
        point = float(row[cols["x"]]), float(row[cols["y"]])
        if np.isfinite(point).all():
            points[marker] = point
    return points


def confidence_scores(table):
    """Use the weakest keypoint, counting missing predictions as zero confidence."""
    scores = np.ones(len(table))
    for cols in marker_columns(table).values():
        likelihood = cols.get("likelihood")
        if likelihood is not None:
            values = table[likelihood].to_numpy(dtype=float)
            missing = ~np.isfinite(xy_values(table, cols)).all(axis=1) | ~np.isfinite(values)
            scores = np.minimum(scores, np.where(missing, 0, values))
    return scores


def knee_distance_errors(table, settings: KneeCorrectionSettings | None):
    """Return the worst relative femur/tibia error per frame across tracked limbs."""
    errors = np.full(len(table), np.nan)
    if settings is None:
        settings = KneeCorrectionSettings(1, 1, 1)
        expected = None
    else:
        expected = (
            settings.hip_knee_length_cm * settings.pixels_per_cm,
            settings.knee_ankle_length_cm * settings.pixels_per_cm,
        )
    columns = coordinate_columns(table)
    for prefix, knee in knee_targets(columns, settings):
        if (prefix, knee) not in columns:
            continue
        try:
            hip = selected_or_matching_bodypart(knee, "hip", settings.hip_bodypart, prefix, columns)
            ankle = selected_or_matching_bodypart(knee, "ankle", settings.ankle_bodypart, prefix, columns)
        except ValueError:
            continue
        knee_xy = xy_values(table, columns[prefix, knee])
        for index, endpoint in enumerate((hip, ankle)):
            distances = np.linalg.norm(xy_values(table, columns[prefix, endpoint]) - knee_xy, axis=1)
            observed = distances[np.isfinite(distances)]
            if not len(observed):
                continue
            reference = expected[index] if expected is not None else np.median(observed)
            if np.isfinite(reference) and reference > 0:
                errors = np.fmax(errors, abs(distances - reference) / reference)
    return errors
