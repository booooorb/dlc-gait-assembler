"""Calculate repeated-measures models and adjusted multiple comparisons."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    PRIMARY_STROKE_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_contracts import (
    CohortCalculationResult,
    CohortTable,
)
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_baseline_deviation import (
    is_baseline as _is_baseline,
)
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_baseline_deviation import (
    timepoint_order as _timepoint_order,
)


def run_mixed_effects(data, pd, np):
    tables = []
    try:
        import statsmodels.formula.api as smf
        from patsy import build_design_matrices
        from scipy.stats import norm
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Repeated-measures models require statsmodels. Install the analysis dependencies."
        ) from exc
    outcomes = [column for column in PRIMARY_STROKE_PARAMETER_NAMES if column in data]
    rows = []
    contrast_rows = []
    failures = []
    model_data = data.copy()
    if "session_speed_cm_s" in model_data:
        speed = pd.to_numeric(model_data["session_speed_cm_s"], errors="coerce")
    else:
        speed = pd.Series(np.nan, index=model_data.index, dtype=float)
    model_data["session_speed_z"] = (
        (speed - speed.mean()) / speed.std(ddof=0) if speed.notna().sum() > 1 and speed.std(ddof=0) else 0.0
    )
    for outcome in outcomes:
        subset = model_data.loc[:, ["animal_id", "group", "timepoint", "session_speed_z", outcome]].copy()
        subset[outcome] = pd.to_numeric(subset[outcome], errors="coerce")
        subset = subset.dropna()
        if len(subset) < 6 or subset["animal_id"].nunique() < 3:
            failures.append(f"{outcome}: insufficient animal-session observations")
            continue
        safe_name = "outcome_value"
        subset[safe_name] = subset[outcome]
        subset["time_order"] = subset["timepoint"].map(_timepoint_order)
        finite_time = subset["time_order"].replace([np.inf, -np.inf], np.nan)
        subset["time_order_z"] = (
            (finite_time - finite_time.mean()) / finite_time.std(ddof=0)
            if finite_time.notna().sum() > 1 and finite_time.std(ddof=0)
            else 0.0
        )
        use_random_time_slope = (
            subset["animal_id"].nunique() >= 8
            and subset.groupby("animal_id").size().min() >= 3
            and (subset["timepoint"].nunique() >= 3)
        )
        try:
            fitted = smf.mixedlm(
                f"{safe_name} ~ C(timepoint) * C(group) + session_speed_z",
                subset,
                groups=subset["animal_id"],
                re_formula="~time_order_z" if use_random_time_slope else "1",
            ).fit(reml=False, method="lbfgs", maxiter=500)
        except Exception as exc:
            failures.append(f"{outcome}: {exc}")
            continue
        confidence = fitted.conf_int()
        for term, estimate in fitted.params.items():
            rows.append(
                {
                    "outcome": outcome,
                    "term": term,
                    "estimate": estimate,
                    "standard_error": fitted.bse.get(term, np.nan),
                    "p_value": fitted.pvalues.get(term, np.nan),
                    "ci_95_low": confidence.loc[term, 0] if term in confidence.index else np.nan,
                    "ci_95_high": confidence.loc[term, 1] if term in confidence.index else np.nan,
                    "animal_count": subset["animal_id"].nunique(),
                    "session_count": len(subset),
                    "random_effects": "intercept + time slope" if use_random_time_slope else "intercept",
                }
            )
        baseline_values = [value for value in subset["timepoint"].unique() if _is_baseline(value)]
        if baseline_values:
            baseline = baseline_values[0]
            design_info = fitted.model.data.design_info
            fixed_names = list(fitted.fe_params.index)
            fixed_covariance = fitted.cov_params().loc[fixed_names, fixed_names].to_numpy(dtype=float)
            fixed_estimates = fitted.fe_params.to_numpy(dtype=float)
            for group in sorted(subset["group"].unique()):
                for post in sorted(
                    (value for value in subset["timepoint"].unique() if value != baseline), key=_timepoint_order
                ):
                    comparison_rows = pd.DataFrame(
                        {"timepoint": [baseline, post], "group": [group, group], "session_speed_z": [0.0, 0.0]}
                    )
                    design = np.asarray(build_design_matrices([design_info], comparison_rows)[0], dtype=float)
                    contrast = design[1] - design[0]
                    estimate = float(contrast @ fixed_estimates)
                    standard_error = float(np.sqrt(max(0.0, contrast @ fixed_covariance @ contrast)))
                    z_value = estimate / standard_error if standard_error > 0 else np.nan
                    p_value = 2.0 * norm.sf(abs(z_value)) if np.isfinite(z_value) else np.nan
                    contrast_rows.append(
                        {
                            "outcome": outcome,
                            "group": group,
                            "baseline_timepoint": baseline,
                            "post_timepoint": post,
                            "estimate": estimate,
                            "standard_error": standard_error,
                            "z_value": z_value,
                            "p_value": p_value,
                            "ci_95_low": estimate - 1.96 * standard_error,
                            "ci_95_high": estimate + 1.96 * standard_error,
                        }
                    )
    results = pd.DataFrame(rows)
    if not results.empty:
        tested = ~results["term"].isin(["Intercept", "Group Var"])
        results.loc[tested, "holm_adjusted_p"] = holm_adjust(results.loc[tested, "p_value"], pd, np)
    tables.append(CohortTable("mixed_effects_primary_outcomes.csv", results, False))
    contrasts = pd.DataFrame(contrast_rows)
    if not contrasts.empty:
        contrasts["holm_adjusted_p"] = holm_adjust(contrasts["p_value"], pd, np)
    tables.append(CohortTable("mixed_effects_planned_contrasts.csv", contrasts, False))
    tables.append(CohortTable("mixed_effects_failures.csv", pd.DataFrame({"message": failures}), False))
    return CohortCalculationResult(
        tuple(tables),
        {},
        f"Mixed-effects models completed for {(results['outcome'].nunique() if not results.empty else 0)} primary outcome(s).",
    )


def holm_adjust(values, pd, np):
    values = pd.to_numeric(values, errors="coerce")
    valid = values.dropna().sort_values()
    adjusted = pd.Series(np.nan, index=values.index, dtype=float)
    count = len(valid)
    running = 0.0
    for rank, (index, value) in enumerate(valid.items()):
        running = max(running, min(1.0, (count - rank) * float(value)))
        adjusted.loc[index] = running
    return adjusted
