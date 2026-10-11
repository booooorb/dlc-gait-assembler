"""Define common DLC coordinate-table data and CSV/H5 codec interfaces."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def validate_dlc_dataframe(dataframe: pd.DataFrame, path: Path) -> None:
    if not isinstance(dataframe.columns, pd.MultiIndex) or dataframe.columns.nlevels < 2:
        raise ValueError(f"{path.name} is not a DeepLabCut coordinate table.")
    coordinate_names = {str(column[-1]).casefold() for column in dataframe.columns}
    if not {"x", "y"}.issubset(coordinate_names):
        raise ValueError(f"{path.name} does not contain x/y DeepLabCut coordinates.")
