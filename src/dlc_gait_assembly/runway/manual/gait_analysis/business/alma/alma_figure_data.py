"""Prepare ALMA trajectory, timing, and cycle data for infrastructure figure rendering."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    parameter_unit as _parameter_unit,
)

IDENTIFIER_COLUMNS = {"limb (hind left / right)", "stride_start (frame)", "stride_end (frame)"}


def numeric_parameter_frame(parameters, pd, np):
    output = pd.DataFrame(index=parameters.index)
    for column in parameters.columns:
        if column == "gait_cycle" or column in IDENTIFIER_COLUMNS:
            continue
        values = pd.to_numeric(parameters[column], errors="coerce")
        if np.isfinite(values.to_numpy(dtype=float)).any():
            output[column] = values
    return output


def long_parameter_table(parameters, numeric, pd):
    identifier_columns = ["gait_cycle"]
    for column in IDENTIFIER_COLUMNS:
        if column in parameters:
            identifier_columns.append(column)
    if numeric.empty:
        return pd.DataFrame(columns=[*identifier_columns, "parameter", "value", "unit"])
    tidy = pd.concat([parameters[identifier_columns], numeric], axis=1).melt(
        id_vars=identifier_columns, value_vars=list(numeric.columns), var_name="parameter", value_name="value"
    )
    tidy["unit"] = tidy["parameter"].map(_parameter_unit)
    return tidy


def parameter_summary(parameters, numeric, pd, np):
    columns = (
        "limb",
        "parameter",
        "unit",
        "count",
        "mean",
        "standard_deviation",
        "median",
        "q1",
        "q3",
        "minimum",
        "maximum",
        "coefficient_of_variation",
    )
    if numeric.empty:
        return pd.DataFrame(columns=columns)
    limb_column = "limb (hind left / right)"
    groups = [("all", parameters.index)]
    if limb_column in parameters:
        groups = [
            (str(limb), group.index) for (limb, group) in parameters.groupby(limb_column, dropna=False, sort=True)
        ]
    rows = []
    for limb, indices in groups:
        for parameter in numeric.columns:
            values = numeric.loc[indices, parameter].to_numpy(dtype=float)
            values = values[np.isfinite(values)]
            count = int(len(values))
            mean = float(np.mean(values)) if count else np.nan
            standard_deviation = float(np.std(values, ddof=1)) if count > 1 else np.nan
            rows.append(
                {
                    "limb": limb,
                    "parameter": parameter,
                    "unit": _parameter_unit(parameter),
                    "count": count,
                    "mean": mean,
                    "standard_deviation": standard_deviation,
                    "median": float(np.median(values)) if count else np.nan,
                    "q1": float(np.percentile(values, 25)) if count else np.nan,
                    "q3": float(np.percentile(values, 75)) if count else np.nan,
                    "minimum": float(np.min(values)) if count else np.nan,
                    "maximum": float(np.max(values)) if count else np.nan,
                    "coefficient_of_variation": standard_deviation / abs(mean)
                    if count > 1 and np.isfinite(mean) and (mean != 0)
                    else np.nan,
                }
            )
    return pd.DataFrame(rows, columns=columns)
