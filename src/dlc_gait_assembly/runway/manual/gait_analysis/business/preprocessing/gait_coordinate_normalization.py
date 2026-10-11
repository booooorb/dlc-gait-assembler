"""Normalize coordinate columns and prepare canonical marker series for shared scientific calculations."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaPreprocessedCoordinates
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_signal_filtering import filtered_series


def prepare_alma_coordinates(
    raw_dataframe, settings, kinematics, markers: tuple[str, ...] | None = None
) -> AlmaPreprocessedCoordinates:
    """Confidence-filter, interpolate, and low-pass-filter marker coordinates.

    This is the shared preprocessing boundary for ALMA-adjacent RustLab1 and
    custom measures. It deliberately uses the same likelihood cutoff, frame
    rate, Butterworth implementation, and cutoff frequency configured for
    ALMA, and it computes every coordinate series only once.
    """
    columns = coordinate_columns(raw_dataframe)
    selected_markers = (
        tuple(dict.fromkeys(markers))
        if markers is not None
        else tuple(dict.fromkeys(marker for (marker, _coord) in columns))
    )
    series = {
        marker: {
            coord: filtered_series(raw_dataframe, columns, marker, coord, settings, kinematics) for coord in ("x", "y")
        }
        for marker in selected_markers
        if (marker, "x") in columns or (marker, "y") in columns
    }
    return AlmaPreprocessedCoordinates(
        columns=columns,
        series=series,
        frame_count=len(raw_dataframe),
        likelihood_threshold=float(getattr(settings, "likelihood_threshold", 0.0) or 0.0),
        frame_rate=float(settings.frame_rate),
        filter_cutoff=float(settings.filter_cutoff),
    )


def coordinate_columns(dataframe) -> dict[tuple[str, str], object]:
    columns: dict[tuple[str, str], object] = {}
    for column in dataframe.columns:
        if isinstance(column, tuple) and len(column) >= 2:
            marker = canonical_marker(column[0])
            coord = str(column[1]).strip().lower()
        else:
            parts = str(column).rsplit(" ", 1)
            if len(parts) != 2:
                continue
            (marker, coord) = (canonical_marker(parts[0]), parts[1].strip().lower())
        if coord in {"x", "y", "likelihood"}:
            columns[marker, coord] = column
    return columns


def canonical_marker(value) -> str:
    marker = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in marker:
        marker = marker.replace("--", "-")
    aliases = {
        "l-back-toe-tip": "l-back-toe",
        "r-back-toe-tip": "r-back-toe",
        "left-back-toe": "l-back-toe",
        "right-back-toe": "r-back-toe",
        "left-back-ankle": "l-back-ankle",
        "right-back-ankle": "r-back-ankle",
        "left-hip": "l-hip",
        "right-hip": "r-hip",
        "left-iliac-crest": "l-iliac-crest",
        "right-iliac-crest": "r-iliac-crest",
        "l-front-toe": "l-front-toe-tip",
        "r-front-toe": "r-front-toe-tip",
        "left-front-toe": "l-front-toe-tip",
        "right-front-toe": "r-front-toe-tip",
        "left-front-toe-tip": "l-front-toe-tip",
        "right-front-toe-tip": "r-front-toe-tip",
        "left-wrist": "l-wrist",
        "right-wrist": "r-wrist",
        "left-elbow": "l-elbow",
        "right-elbow": "r-elbow",
        "left-shoulder": "l-shoulder",
        "right-shoulder": "r-shoulder",
        "center-front": "d-center-front",
        "front-center": "d-center-front",
        "front-left": "d-front-left",
        "front-right": "d-front-right",
    }
    return aliases.get(marker, marker)
