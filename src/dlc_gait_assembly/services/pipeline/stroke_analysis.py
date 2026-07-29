"""Animal-grouped cohort analysis for synchronized stroke gait summaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dlc_gait_assembly.services.pipeline.stroke import PRIMARY_STROKE_PARAMETER_NAMES

_NON_FEATURE_COLUMNS = {
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

_DETERMINISTIC_REDUNDANCY_SUFFIXES = (
    "cycle duration (no. frames)",
    "swing percentage (%)",
    "cycle velocity (cm/s)",
    "mtp joint amplitude (deg)",
    "ankle joint amplitude (deg)",
    "hip joint amplitude (deg)",
)


@dataclass(frozen=True)
class CohortAnalysisResult:
    output_files: tuple[Path, ...]
    messages: tuple[str, ...]


def load_session_summaries(paths, pd):
    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        frame["source_file"] = str(Path(path).expanduser().resolve())
        frames.append(frame)
    if not frames:
        raise ValueError("Select at least one session-summary CSV.")
    data = pd.concat(frames, ignore_index=True, sort=False)
    required = {"animal_id", "group", "timepoint", "session_id"}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValueError("Session summaries are missing required columns: " + ", ".join(missing))
    data["animal_id"] = data["animal_id"].astype(str)
    data["group"] = data["group"].astype(str)
    data["timepoint"] = data["timepoint"].astype(str)
    return add_baseline_phase_deviation(data, pd)


def add_baseline_phase_deviation(data, pd):
    result = data.copy()
    source = "left_right_hindlimb_phase_offset"
    target = "hindlimb_phase_offset_deviation_from_baseline"
    if source not in result:
        return result
    result[target] = float("nan")
    for _animal_id, indices in result.groupby("animal_id").groups.items():
        animal = result.loc[indices]
        baseline_mask = animal["timepoint"].map(_is_baseline)
        if baseline_mask.any():
            baseline = pd.to_numeric(animal.loc[baseline_mask, source], errors="coerce").median()
        else:
            order = animal["timepoint"].map(_timepoint_order)
            earliest = order.min()
            baseline = pd.to_numeric(animal.loc[order == earliest, source], errors="coerce").median()
        result.loc[indices, target] = pd.to_numeric(animal[source], errors="coerce") - baseline
    return result


def audit_and_select_features(data, pd, np, correlation_threshold: float = 0.90):
    candidates = []
    deterministic_drops = []
    for column in data.columns:
        if column in _NON_FEATURE_COLUMNS or column == "source_file" or column.endswith("__iqr"):
            continue
        if any(column.endswith(suffix) for suffix in _DETERMINISTIC_REDUNDANCY_SUFFIXES):
            deterministic_drops.append(column)
            continue
        values = pd.to_numeric(data[column], errors="coerce")
        if values.notna().sum() < 2 or values.nunique(dropna=True) < 2:
            continue
        candidates.append(column)

    numeric = data.loc[:, candidates].apply(pd.to_numeric, errors="coerce")
    missing_fraction = numeric.isna().mean()
    candidates = [column for column in candidates if missing_fraction[column] <= 0.20]
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
            preferred = _preferred_feature(column, conflict)
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
    return retained, pd.DataFrame(report_rows)


def run_stroke_cohort_analysis(
    session_summary_paths,
    output_folder: Path,
    *,
    run_pca: bool = True,
    run_random_forest: bool = True,
    run_mixed_effects: bool = True,
) -> CohortAnalysisResult:
    """Run leakage-safe cohort analyses and write portable CSV/SVG results."""

    import numpy as np
    import pandas as pd

    output_folder = Path(output_folder).expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)
    data = load_session_summaries(session_summary_paths, pd)
    combined_path = output_folder / "stroke_session_summaries.csv"
    data.to_csv(combined_path, index=False)
    output_files = [combined_path]
    messages = [f"Loaded {len(data)} animal-session row(s) from {len(session_summary_paths)} file(s)."]
    if "session_usable" in data:
        usable = data["session_usable"].map(_coerce_bool)
        unusable_fraction = float((~usable).mean()) if len(usable) else float("nan")
        acceptance = pd.DataFrame(
            [
                {
                    "criterion": "unusable animal-sessions",
                    "target": "< 20%",
                    "observed": unusable_fraction,
                    "passed": bool(unusable_fraction < 0.20),
                    "notes": "Other pilot criteria require manual-event and test-retest annotation inputs.",
                }
            ]
        )
        acceptance_path = output_folder / "pilot_acceptance_summary.csv"
        acceptance.to_csv(acceptance_path, index=False)
        output_files.append(acceptance_path)
        messages.append(
            f"Pilot usability: {unusable_fraction:.1%} unusable animal-session(s) "
            f"({'pass' if unusable_fraction < 0.20 else 'review required'}; target <20%)."
        )

    features, redundancy = audit_and_select_features(data, pd, np)
    redundancy_path = output_folder / "feature_redundancy_report.csv"
    redundancy.to_csv(redundancy_path, index=False)
    output_files.append(redundancy_path)
    messages.append(f"Retained {len(features)} model-ready features after non-outcome-based redundancy control.")

    if run_pca:
        paths, detail = _run_pca(data, features, output_folder, pd, np)
        output_files.extend(paths)
        messages.append(detail)
    if run_random_forest:
        paths, detail = _run_grouped_random_forest(data, features, output_folder, pd, np)
        output_files.extend(paths)
        messages.append(detail)
    if run_mixed_effects:
        paths, detail = _run_mixed_effects(data, output_folder, pd, np)
        output_files.extend(paths)
        messages.append(detail)

    return CohortAnalysisResult(tuple(output_files), tuple(messages))


def _run_pca(data, features, output_folder, pd, np):
    try:
        import matplotlib
        from sklearn.decomposition import PCA
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PCA requires matplotlib and scikit-learn. Install the analysis dependencies."
        ) from exc
    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    if len(data) < 2 or not features:
        raise ValueError("PCA requires at least two animal-session rows and one usable feature.")
    matrix = data.loc[:, features].apply(pd.to_numeric, errors="coerce")
    transformed = StandardScaler().fit_transform(SimpleImputer(strategy="median").fit_transform(matrix))
    component_count = min(5, transformed.shape[0], transformed.shape[1])
    model = PCA(n_components=component_count, random_state=42)
    scores = model.fit_transform(transformed)
    score_columns = [f"PC{index}" for index in range(1, component_count + 1)]
    score_frame = data.loc[:, ["animal_id", "group", "timepoint", "session_id"]].reset_index(drop=True)
    for index, column in enumerate(score_columns):
        score_frame[column] = scores[:, index]
    scores_path = output_folder / "PCA_scores.csv"
    score_frame.to_csv(scores_path, index=False)

    loadings = pd.DataFrame(model.components_.T, index=features, columns=score_columns)
    loadings.index.name = "feature"
    loadings_path = output_folder / "PCA_loadings.csv"
    loadings.to_csv(loadings_path)
    variance = pd.DataFrame(
        {
            "component": score_columns,
            "explained_variance_ratio": model.explained_variance_ratio_,
            "cumulative_variance_ratio": np.cumsum(model.explained_variance_ratio_),
        }
    )
    variance_path = output_folder / "PCA_explained_variance.csv"
    variance.to_csv(variance_path, index=False)

    figure, axis = plt.subplots(figsize=(7.5, 5.5))
    if component_count >= 2:
        for group, group_frame in score_frame.groupby("group"):
            axis.scatter(group_frame["PC1"], group_frame["PC2"], label=str(group), alpha=0.82)
        axis.set_ylabel(f"PC2 ({model.explained_variance_ratio_[1] * 100:.1f}%)")
    else:
        axis.scatter(score_frame["PC1"], np.zeros(len(score_frame)), alpha=0.82)
        axis.set_ylabel("")
    axis.set_xlabel(f"PC1 ({model.explained_variance_ratio_[0] * 100:.1f}%)")
    axis.set_title("Animal-session PCA")
    if data["group"].nunique() > 1:
        axis.legend(frameon=False)
    figure.tight_layout()
    cluster_path = output_folder / "PCA_clusters.svg"
    figure.savefig(cluster_path, format="svg")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(7.5, 4.5))
    axis.plot(range(1, component_count + 1), np.cumsum(model.explained_variance_ratio_), marker="o")
    axis.set_ylim(0, 1.05)
    axis.set_xlabel("Number of components")
    axis.set_ylabel("Cumulative explained variance")
    axis.set_title("PCA scree summary")
    figure.tight_layout()
    scree_path = output_folder / "PCA_scree_plot.svg"
    figure.savefig(scree_path, format="svg")
    plt.close(figure)
    return (
        (scores_path, loadings_path, variance_path, cluster_path, scree_path),
        f"PCA used {len(features)} features across {len(data)} animal-session rows.",
    )


def _run_grouped_random_forest(data, features, output_folder, pd, np):
    try:
        import matplotlib
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.inspection import permutation_importance
        from sklearn.metrics import ConfusionMatrixDisplay, accuracy_score
        from sklearn.model_selection import StratifiedGroupKFold
        from sklearn.pipeline import make_pipeline
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Random Forest requires matplotlib and scikit-learn. Install the analysis dependencies."
        ) from exc
    matplotlib.use("Agg", force=True)
    from matplotlib import pyplot as plt

    usable = data["group"].notna() & data["animal_id"].notna()
    analysis = data.loc[usable].reset_index(drop=True)
    if not features:
        raise ValueError("Grouped Random Forest requires at least one usable feature.")
    class_animals = analysis.groupby("group")["animal_id"].nunique()
    if len(class_animals) < 2 or class_animals.min() < 2:
        raise ValueError("Grouped Random Forest requires at least two groups and two animals per group.")
    split_count = int(min(5, class_animals.min(), analysis["animal_id"].nunique()))
    splitter = StratifiedGroupKFold(n_splits=split_count, shuffle=True, random_state=42)
    x = analysis.loc[:, features].apply(pd.to_numeric, errors="coerce")
    y = analysis["group"].astype(str)
    groups = analysis["animal_id"].astype(str)
    predictions = pd.Series(index=analysis.index, dtype=object)
    importance_rows = []
    fold_assignments = pd.Series(index=analysis.index, dtype="Int64")

    for fold, (train_index, test_index) in enumerate(splitter.split(x, y, groups), start=1):
        pipeline = make_pipeline(
            SimpleImputer(strategy="median"),
            RandomForestClassifier(
                n_estimators=500,
                random_state=42 + fold,
                class_weight="balanced",
                min_samples_leaf=2,
            ),
        )
        pipeline.fit(x.iloc[train_index], y.iloc[train_index])
        predictions.iloc[test_index] = pipeline.predict(x.iloc[test_index])
        fold_assignments.iloc[test_index] = fold
        importance = permutation_importance(
            pipeline,
            x.iloc[test_index],
            y.iloc[test_index],
            n_repeats=25,
            random_state=142 + fold,
            scoring="balanced_accuracy",
        )
        for feature, mean, standard_deviation in zip(
            features,
            importance.importances_mean,
            importance.importances_std,
            strict=True,
        ):
            importance_rows.append(
                {
                    "fold": fold,
                    "feature": feature,
                    "importance": mean,
                    "importance_sd": standard_deviation,
                }
            )

    prediction_frame = analysis.loc[:, ["animal_id", "group", "timepoint", "session_id"]].copy()
    prediction_frame["predicted_group"] = predictions
    prediction_frame["fold"] = fold_assignments
    predictions_path = output_folder / "random_forest_grouped_predictions.csv"
    prediction_frame.to_csv(predictions_path, index=False)
    accuracy = float(accuracy_score(y, predictions))

    raw_importance = pd.DataFrame(importance_rows)
    importance_summary = (
        raw_importance.groupby("feature", as_index=False)
        .agg(
            permutation_importance_mean=("importance", "mean"),
            permutation_importance_sd=("importance", "std"),
        )
        .sort_values("permutation_importance_mean", ascending=False)
    )
    importance_path = output_folder / "random_forest_permutation_importance.csv"
    importance_summary.to_csv(importance_path, index=False)

    figure, axis = plt.subplots(figsize=(6.5, 5.5))
    ConfusionMatrixDisplay.from_predictions(y, predictions, ax=axis, cmap="Blues")
    axis.set_title(f"Animal-grouped Random Forest (accuracy {accuracy:.3f})")
    figure.tight_layout()
    confusion_path = output_folder / f"random_forest_confusion_acc_{accuracy:.3f}.svg"
    figure.savefig(confusion_path, format="svg")
    plt.close(figure)
    return (
        (predictions_path, importance_path, confusion_path),
        f"Grouped Random Forest accuracy {accuracy:.3f}; no animal appears in both train and test within a fold.",
    )


def _run_mixed_effects(data, output_folder, pd, np):
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
        (speed - speed.mean()) / speed.std(ddof=0)
        if speed.notna().sum() > 1 and speed.std(ddof=0)
        else 0.0
    )
    for outcome in outcomes:
        subset = model_data.loc[
            :,
            ["animal_id", "group", "timepoint", "session_speed_z", outcome],
        ].copy()
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
            and subset["timepoint"].nunique() >= 3
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
                    (value for value in subset["timepoint"].unique() if value != baseline),
                    key=_timepoint_order,
                ):
                    comparison_rows = pd.DataFrame(
                        {
                            "timepoint": [baseline, post],
                            "group": [group, group],
                            "session_speed_z": [0.0, 0.0],
                        }
                    )
                    design = np.asarray(
                        build_design_matrices([design_info], comparison_rows)[0],
                        dtype=float,
                    )
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
        results.loc[tested, "holm_adjusted_p"] = _holm_adjust(results.loc[tested, "p_value"], pd, np)
    results_path = output_folder / "mixed_effects_primary_outcomes.csv"
    results.to_csv(results_path, index=False)
    contrasts = pd.DataFrame(contrast_rows)
    if not contrasts.empty:
        contrasts["holm_adjusted_p"] = _holm_adjust(contrasts["p_value"], pd, np)
    contrasts_path = output_folder / "mixed_effects_planned_contrasts.csv"
    contrasts.to_csv(contrasts_path, index=False)
    failures_path = output_folder / "mixed_effects_failures.csv"
    pd.DataFrame({"message": failures}).to_csv(failures_path, index=False)
    return (
        (results_path, contrasts_path, failures_path),
        f"Mixed-effects models completed for {results['outcome'].nunique() if not results.empty else 0} primary outcome(s).",
    )


def _preferred_feature(first: str, second: str) -> str:
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


def _holm_adjust(values, pd, np):
    values = pd.to_numeric(values, errors="coerce")
    valid = values.dropna().sort_values()
    adjusted = pd.Series(np.nan, index=values.index, dtype=float)
    count = len(valid)
    running = 0.0
    for rank, (index, value) in enumerate(valid.items()):
        running = max(running, min(1.0, (count - rank) * float(value)))
        adjusted.loc[index] = running
    return adjusted


def _is_baseline(value: str) -> bool:
    normalized = str(value).strip().casefold().replace(" ", "")
    return normalized in {"baseline", "base", "bl", "0", "0d", "day0", "0dpi"}


def _timepoint_order(value: str) -> float:
    text = str(value).strip().casefold()
    if _is_baseline(text):
        return 0.0
    number = "".join(character for character in text if character.isdigit() or character in ".-")
    try:
        return float(number)
    except ValueError:
        return float("inf")


def _coerce_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "1", "yes", "y"}
    return bool(value)


__all__ = [
    "CohortAnalysisResult",
    "add_baseline_phase_deviation",
    "audit_and_select_features",
    "load_session_summaries",
    "run_stroke_cohort_analysis",
]
