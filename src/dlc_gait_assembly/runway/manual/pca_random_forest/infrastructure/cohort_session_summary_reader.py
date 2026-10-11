"""Read source recording/session summaries for cohort table preparation."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_table_preparation import prepare_cohort_tables


def load_session_summaries(paths, pd):
    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        frame["source_file"] = str(Path(path).expanduser().resolve())
        frames.append(frame)
    return prepare_cohort_tables(frames, pd)
