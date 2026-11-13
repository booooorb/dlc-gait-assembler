"""Summarize independently observed strides for bilateral asymmetry and variability."""

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.stroke_recovery_parameter_definitions import (
    recovery_outcomes,
)


def outcome_values(table, side, outcome):
    names = [name.format(side=side, prefix=side[0]) for name in outcome.columns]
    if any(name not in table for name in names):
        return pd.Series(np.nan, index=table.index, dtype=float)
    values = pd.to_numeric(table[names[0]], errors="coerce")
    if len(names) == 2:
        values = values - pd.to_numeric(table[names[1]], errors="coerce")
    return values * outcome.factor


def eligible_strides(table, start, stop):
    if table is None:
        return pd.DataFrame()
    begin = pd.to_numeric(table["stride_start (s)"], errors="coerce")
    end = pd.to_numeric(table["stride_stop (s)"], errors="coerce")
    accepted = table["passed_stride_filters"].fillna(False).astype(bool)
    return table.loc[accepted & begin.ge(start - 1e-9) & end.le(stop + 1e-9) & end.gt(begin)]


def recovery_summary(tables, settings, start, stop, lesion_hemisphere="unknown"):
    """Compare same-trial medians; never zip, pair, or truncate left/right rows."""
    required = max(1, int(settings.minimum_synchronized_cycles))
    eligible = {side: eligible_strides(tables.get(side), start, stop) for side in ("left", "right")}
    result = {
        "recovery_summary_method": "independent side medians; complete accepted strides in common camera interval",
        "recovery_minimum_strides_per_side": required,
        "recovery_interval_start (s)": start,
        "recovery_interval_stop (s)": stop,
        "contralesional_side": {"left": "right", "right": "left"}.get(lesion_hemisphere, "unknown"),
        "ipsilesional_side": lesion_hemisphere if lesion_hemisphere in {"left", "right"} else "unknown",
        "lesion_asymmetry_status": "available when outcome has sufficient strides"
        if lesion_hemisphere in {"left", "right"}
        else "unavailable: lesion hemisphere is unknown or none",
    }
    for side, frame in eligible.items():
        result[f"{side}__recovery_stride_count"] = len(frame)
        speed = pd.to_numeric(frame.get("cycle velocity (cm/s)", pd.Series(dtype=float)), errors="coerce")
        speed = speed[np.isfinite(speed)]
        result[f"{side}__median_cycle_velocity (cm/s)"] = float(speed.median()) if len(speed) else np.nan
    for outcome in recovery_outcomes(settings.limb_scope):
        medians, counts = {}, {}
        for side, frame in eligible.items():
            values = outcome_values(frame, side, outcome)
            values = values[np.isfinite(values) & values.ge(0)]
            counts[side] = len(values)
            medians[side] = float(values.median()) if len(values) else np.nan
            result[f"{side}__{outcome.key}_valid_strides"] = len(values)
            result[f"{side}__{outcome.key}_median ({outcome.unit})"] = medians[side]
            if outcome.variability:
                mean = float(values.mean()) if len(values) else np.nan
                result[f"{side}__{outcome.key}_cv (%)"] = (
                    float(100.0 * values.std(ddof=1) / abs(mean))
                    if len(values) >= max(3, required) and mean != 0
                    else np.nan
                )
        denominator = abs(medians["left"]) + abs(medians["right"])
        usable = min(counts.values()) >= required and np.isfinite(denominator) and denominator > 0
        result[f"{outcome.key}_symmetry_index (%)"] = (
            200.0 * abs(medians["left"] - medians["right"]) / denominator if usable else np.nan
        )
        contra, ipsi = result["contralesional_side"], result["ipsilesional_side"]
        result[f"{outcome.key}_lesion_asymmetry (%)"] = (
            200.0 * (medians[contra] - medians[ipsi]) / denominator if usable and contra in medians else np.nan
        )
        result[f"{outcome.key}_asymmetry_status"] = (
            "available"
            if usable
            else "insufficient valid strides"
            if min(counts.values()) < required
            else "undefined: zero denominator"
        )
    return result
