"""Aggregate RustLab1 stride features into recording-level statistics and quality summaries."""

from __future__ import annotations


def summarize_rustlab1(dataframe, pd, np):
    numeric = dataframe.select_dtypes(include="number")
    row = {"stride_count": int(len(dataframe))}
    for column in numeric.columns:
        if column in {"gait_cycle", "stride_start (frame)", "stride_end (frame)"}:
            continue
        values = pd.to_numeric(numeric[column], errors="coerce").to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        row[column] = float(np.nanmedian(finite)) if len(finite) else np.nan
    return pd.DataFrame([row])
