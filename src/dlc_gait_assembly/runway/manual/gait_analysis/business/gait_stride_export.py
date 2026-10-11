"""Stride identity and quality fields, and checks against accidental row loss."""

from collections import Counter

import numpy as np
import pandas as pd

FRAME_COLUMNS = ("stride_start (frame)", "stride_end (frame)")
STRIDE_DETAIL_COLUMNS = ("stride_number", "passed_stride_filters", "timing_observed (%)", "timing_gap_frames")


def with_stride_details(result):
    parameters = result[0].copy()
    starts, ends = (pd.to_numeric(parameters[name], errors="coerce") for name in FRAME_COLUMNS)
    complete = starts.notna() & ends.notna() & (ends > starts)
    # Keep an independent chronological identity for each side, even when the
    # opposite side has missing or differently timed strides.
    parameters["stride_number"] = starts.where(complete).rank(method="first").astype("Int64")
    duration = pd.to_numeric(
        parameters.get("cycle duration (s)", pd.Series(index=parameters.index, dtype=float)), errors="coerce"
    )
    parameters["passed_stride_filters"] = (complete & duration.gt(0)).astype("boolean")
    parameters.loc[~complete, "passed_stride_filters"] = pd.NA
    observed = result[1].attrs.get("detection_diagnostics", {}).get("observed") if result[1] is not None else None
    coverage, gaps = [], []
    for start, end in zip(starts, ends, strict=True):
        if observed is None or not np.isfinite(start + end) or not 0 <= start < end < len(observed):
            coverage.append(np.nan)
            gaps.append(pd.NA)
            continue
        samples = np.asarray(observed[int(start) : int(end) + 1], dtype=bool)
        coverage.append(100.0 * samples.mean())
        gaps.append(int((~samples).sum()))
    parameters["timing_observed (%)"] = coverage
    parameters["timing_gap_frames"] = pd.array(gaps, dtype="Int64")
    return (parameters, *result[1:])


def validate_stride_rows(table, side_parameters):
    """Every real cycle must survive export exactly once; pairing cannot drop it."""

    def bounds(frame, prefix=""):
        values = frame.reindex(columns=[f"{prefix}{name}" for name in FRAME_COLUMNS]).apply(
            pd.to_numeric, errors="coerce"
        )
        return Counter(tuple(row) for row in values.to_numpy() if np.isfinite(row).all() and row[1] > row[0])

    for side, parameters in side_parameters.items():
        prefix = "" if side == "side" else f"{side}__"
        if bounds(parameters) != bounds(table, prefix):
            raise RuntimeError(
                f"The {side} stride rows do not match detection. Export stopped to prevent losing or duplicating strides."
            )
