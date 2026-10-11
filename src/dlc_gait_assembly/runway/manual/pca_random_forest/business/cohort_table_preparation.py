"""Combine recording summaries and normalize animal, group, phase, and study identifiers."""

from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_baseline_deviation import (
    add_baseline_phase_deviation,
)


def prepare_cohort_tables(frames, pd):
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
