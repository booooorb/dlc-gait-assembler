"""Choose representative frames and prepare original and reconstructed joint coordinates."""

from __future__ import annotations

from math import isfinite


def bodypart_point(dataframe, bodypart: str, position: int) -> tuple[float, float] | None:
    x_column = next(
        (column for column in dataframe.columns if str(column[-2]) == bodypart and str(column[-1]).casefold() == "x"),
        None,
    )
    y_column = next(
        (column for column in dataframe.columns if str(column[-2]) == bodypart and str(column[-1]).casefold() == "y"),
        None,
    )
    if x_column is None or y_column is None:
        return None
    x = float(dataframe.iloc[position][x_column])
    y = float(dataframe.iloc[position][y_column])
    if not (isfinite(x) and isfinite(y)):
        return None
    return (x, y)


def previewable_frame_positions(frame_statuses: tuple[str, ...]) -> tuple[int, ...]:
    # Weak estimates must remain inspectable and must not disappear from review.
    return tuple(range(len(frame_statuses)))
