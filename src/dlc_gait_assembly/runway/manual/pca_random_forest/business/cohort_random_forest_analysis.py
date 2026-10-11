"""Calculate classification results using animal-grouped training and validation splits."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_contracts import (
    CohortCalculationResult,
    CohortTable,
)


def run_grouped_random_forest(data, features, pd, np):
    tables = []
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.impute import SimpleImputer
        from sklearn.inspection import permutation_importance
        from sklearn.metrics import accuracy_score
        from sklearn.model_selection import StratifiedGroupKFold
        from sklearn.pipeline import make_pipeline
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Random Forest requires matplotlib and scikit-learn. Install the analysis dependencies."
        ) from exc
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
                n_estimators=500, random_state=42 + fold, class_weight="balanced", min_samples_leaf=2
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
            features, importance.importances_mean, importance.importances_std, strict=True
        ):
            importance_rows.append(
                {"fold": fold, "feature": feature, "importance": mean, "importance_sd": standard_deviation}
            )
    prediction_frame = analysis.loc[:, ["animal_id", "group", "timepoint", "session_id"]].copy()
    prediction_frame["predicted_group"] = predictions
    prediction_frame["fold"] = fold_assignments
    tables.append(CohortTable("random_forest_grouped_predictions.csv", prediction_frame, False))
    accuracy = float(accuracy_score(y, predictions))
    raw_importance = pd.DataFrame(importance_rows)
    importance_summary = (
        raw_importance.groupby("feature", as_index=False)
        .agg(permutation_importance_mean=("importance", "mean"), permutation_importance_sd=("importance", "std"))
        .sort_values("permutation_importance_mean", ascending=False)
    )
    tables.append(CohortTable("random_forest_permutation_importance.csv", importance_summary, False))
    return CohortCalculationResult(
        tuple(tables),
        {"random_forest": {"y": y, "predictions": predictions, "accuracy": accuracy}},
        f"Grouped Random Forest accuracy {accuracy:.3f}; no animal appears in both train and test within a fold.",
    )
