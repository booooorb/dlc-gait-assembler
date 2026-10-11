"""Evaluate feature availability, missingness, redundancy, and analysis eligibility."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    PRIMARY_STROKE_PARAMETER_NAMES,
)

NON_FEATURE_COLUMNS = {
    "animal_id",
    "group",
    "sex",
    "lesion_hemisphere",
    "timepoint",
    "trial",
    "session_id",
    "valid_cycle_count",
    "session_usable",
    "tracking_coverage",
    "session_speed_cm_s",
    "session_speed_cv",
    "frame_rate_hz",
    "bottom_x_pixels_per_cm",
    "bottom_y_pixels_per_cm",
    "stride_start (frame)",
    "stride_end (frame)",
    "left_stance_start_frame",
    "left_stance_end_frame",
    "right_stance_start_frame",
    "right_stance_end_frame",
    "cycle_duration_frames",
    "cycle_valid",
}
DETERMINISTIC_REDUNDANCY_SUFFIXES = (
    "cycle duration (no. frames)",
    "swing percentage (%)",
    "cycle velocity (cm/s)",
    "mtp joint amplitude (deg)",
    "ankle joint amplitude (deg)",
    "hip joint amplitude (deg)",
)


def audit_and_select_features(data, pd, np, correlation_threshold: float = 0.9):
    candidates = []
    deterministic_drops = []
    for column in data.columns:
        if column in NON_FEATURE_COLUMNS or column == "source_file" or column.endswith("__iqr"):
            continue
        if any(column.endswith(suffix) for suffix in DETERMINISTIC_REDUNDANCY_SUFFIXES):
            deterministic_drops.append(column)
            continue
        values = pd.to_numeric(data[column], errors="coerce")
        if values.notna().sum() < 2 or values.nunique(dropna=True) < 2:
            continue
        candidates.append(column)
    numeric = data.loc[:, candidates].apply(pd.to_numeric, errors="coerce")
    missing_fraction = numeric.isna().mean()
    candidates = [column for column in candidates if missing_fraction[column] <= 0.2]
    numeric = numeric.loc[:, candidates]
    correlation = numeric.corr(method="spearman").abs()
    retained = []
    correlation_drops = []
    for column in candidates:
        conflict = next(
            (
                existing
                for existing in retained
                if pd.notna(correlation.loc[column, existing])
                and correlation.loc[column, existing] >= correlation_threshold
            ),
            None,
        )
        if conflict is None:
            retained.append(column)
        else:
            preferred = preferred_feature(column, conflict)
            dropped = conflict if preferred == column else column
            kept = column if preferred == column else conflict
            if dropped == conflict:
                retained.remove(conflict)
                retained.append(column)
            correlation_drops.append(
                {
                    "dropped_feature": dropped,
                    "retained_feature": kept,
                    "reason": f"|Spearman rho| >= {correlation_threshold:.2f}",
                    "absolute_spearman": float(correlation.loc[column, conflict]),
                }
            )
    report_rows = [
        {
            "dropped_feature": column,
            "retained_feature": "",
            "reason": "deterministic/derived redundancy",
            "absolute_spearman": np.nan,
        }
        for column in deterministic_drops
    ]
    report_rows.extend(correlation_drops)
    return (retained, pd.DataFrame(report_rows))


def preferred_feature(first: str, second: str) -> str:
    primary = set(PRIMARY_STROKE_PARAMETER_NAMES)
    if first in primary and second not in primary:
        return first
    if second in primary and first not in primary:
        return second
    first_missing_penalty = first.count("Variability") + first.count("__")
    second_missing_penalty = second.count("Variability") + second.count("__")
    if first_missing_penalty != second_missing_penalty:
        return first if first_missing_penalty < second_missing_penalty else second
    return min(first, second)


def coerce_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes", "y"}
    return bool(value)
