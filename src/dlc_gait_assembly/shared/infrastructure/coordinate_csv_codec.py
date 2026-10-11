"""Read and write DeepLabCut CSV coordinate columns without changing table structure."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dlc_gait_assembly.shared.business.coordinate_table_contracts import (
    validate_dlc_dataframe as _validate_dlc_dataframe,
)


def read_dlc_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path).expanduser().resolve()
    try:
        dataframe = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0)
    except Exception as exc:
        raise ValueError(f"Could not read DeepLabCut CSV: {csv_path.name}") from exc
    _validate_dlc_dataframe(dataframe, csv_path)
    return dataframe


def read_dlc_bodyparts(path: str | Path) -> tuple[str, ...]:
    csv_path = Path(path).expanduser().resolve()
    try:
        dataframe = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0, nrows=0)
    except Exception as exc:
        raise ValueError(f"Could not read DeepLabCut labels from: {csv_path.name}") from exc
    _validate_dlc_dataframe(dataframe, csv_path)
    bodyparts = []
    for column in dataframe.columns:
        bodypart = str(column[-2])
        if bodypart not in bodyparts:
            bodyparts.append(bodypart)
    return tuple(bodyparts)


def read_analysis_csv(path):
    """Read the established two-level scientific header, retaining the frame column."""
    return pd.read_csv(path, header=[1, 2])


def write_dlc_csv(dataframe, path):
    """Write a DLC table without flattening its scorer/bodypart/coordinate columns."""
    dataframe.to_csv(path)
