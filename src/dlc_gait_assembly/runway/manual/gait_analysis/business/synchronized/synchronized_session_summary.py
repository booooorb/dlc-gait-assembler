"""Aggregate accepted-cycle measurements with study identifiers and quality-control results."""

from __future__ import annotations

from dataclasses import asdict

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.bottom_paw_parameter_contract import (
    without_retired_bottom_parameters,
)


def summarize_session(stride_features, metadata, trajectory_qc, session_usable, pd, np):
    stride_features = without_retired_bottom_parameters(stride_features)
    if "cycle_valid" in stride_features:
        valid_strides = stride_features.loc[stride_features["cycle_valid"].fillna(False).astype(bool)]
    else:
        valid_strides = stride_features
    numeric = valid_strides.select_dtypes(include="number")
    medians = numeric.median(axis=0, skipna=True)
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    row = asdict(metadata)
    row["valid_cycle_count"] = int(len(valid_strides))
    row["session_usable"] = bool(session_usable)
    row["tracking_coverage"] = float(trajectory_qc["required_tracking_coverage"])
    for column in numeric:
        row[column] = medians[column]
        row[f"{column}__iqr"] = q3[column] - q1[column]
    return pd.DataFrame([row])


def resolved_metadata(view_set: AlmaViewCsvSet) -> tuple[StrokeStudyMetadata, tuple[str, ...]]:
    metadata = view_set.metadata or StrokeStudyMetadata()
    values = asdict(metadata)
    missing = [
        field
        for field in ("animal_id", "group", "sex", "timepoint", "trial", "session_id")
        if not str(values[field]).strip()
    ]
    if values["lesion_hemisphere"] not in {"left", "right"}:
        missing.append("lesion_hemisphere")
    if missing:
        raise ValueError(
            "Stroke analysis requires complete study metadata. Missing or unknown: "
            + ", ".join(missing)
            + ". Edit the CSV pairing metadata."
        )
    return (StrokeStudyMetadata(**values), ())


def metadata_frame(metadata, cycles, pd):
    values = asdict(metadata)
    values["animal_id"] = values["animal_id"] or "unknown"
    values["session_id"] = values["session_id"] or "unknown"
    frame = pd.DataFrame([values] * len(cycles))
    frame["cycle_id"] = cycles["cycle_id"].to_numpy() if len(cycles) else []
    return frame
