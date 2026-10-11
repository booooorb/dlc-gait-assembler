"""Calculate PCA coordinates, variance, and feature loadings."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_contracts import (
    CohortCalculationResult,
    CohortTable,
)


def run_pca(data, features, pd, np):
    tables = []
    try:
        from sklearn.decomposition import PCA
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PCA requires matplotlib and scikit-learn. Install the analysis dependencies."
        ) from exc
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
    tables.append(CohortTable("PCA_scores.csv", score_frame, False))
    loadings = pd.DataFrame(model.components_.T, index=features, columns=score_columns)
    loadings.index.name = "feature"
    tables.append(CohortTable("PCA_loadings.csv", loadings, True))
    variance = pd.DataFrame(
        {
            "component": score_columns,
            "explained_variance_ratio": model.explained_variance_ratio_,
            "cumulative_variance_ratio": np.cumsum(model.explained_variance_ratio_),
        }
    )
    tables.append(CohortTable("PCA_explained_variance.csv", variance, False))
    return CohortCalculationResult(
        tuple(tables),
        {
            "pca": {
                "data": data,
                "score_frame": score_frame,
                "component_count": component_count,
                "variance_ratio": model.explained_variance_ratio_,
            }
        },
        f"PCA used {len(features)} features across {len(data)} animal-session rows.",
    )
