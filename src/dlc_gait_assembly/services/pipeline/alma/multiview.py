"""Pure coordinate mapping and confidence filtering for ALMA inputs."""

from __future__ import annotations

from dlc_gait_assembly.services.pipeline.alma.models import (
    ALMA_BODYPARTS,
    AlmaSettings,
    AlmaViewCsvSet,
)


def merge_multiview_rustlab1_dataframe(
    view_set: AlmaViewCsvSet,
    pd,
    view_mappings: dict[str, dict[str, str]] | None = None,
):
    frames = []
    for view, path in (
        ("left", view_set.left_csv),
        ("right", view_set.right_csv),
        ("bottom", view_set.bottom_csv),
    ):
        frame = pd.read_csv(path, header=[1, 2])
        columns = []
        for column in frame.columns:
            if isinstance(column, tuple) and len(column) >= 2:
                marker, coord = column[0], column[1]
            else:
                parts = str(column).rsplit(" ", 1)
                marker, coord = (parts[0], parts[1]) if len(parts) == 2 else (column, "")
            columns.append(
                (
                    _rustlab1_marker_for_view(marker, view, view_mappings),
                    str(coord).strip().lower(),
                )
            )
        frame = frame.copy()
        frame.columns = pd.MultiIndex.from_tuples(columns)
        frames.append(frame)
    return pd.concat(frames, axis=1)


def view_mappings_for_set(
    settings: AlmaSettings,
    set_name: str,
) -> dict[str, dict[str, str]] | None:
    mappings = settings.view_bodypart_mapping
    if not mappings:
        return None
    if _looks_like_view_mapping(mappings):
        return mappings
    candidate = mappings.get(set_name) if isinstance(mappings, dict) else None
    if isinstance(candidate, dict) and _looks_like_view_mapping(candidate):
        return candidate
    return None


def view_mapping_for(
    view_mappings: dict[str, dict[str, str]] | None,
    view: str,
) -> dict[str, str] | None:
    if not view_mappings:
        return None
    mapping = view_mappings.get(view)
    return mapping if isinstance(mapping, dict) else None


def filter_low_confidence_coordinates(dataframe, threshold: float, pd):
    threshold = float(threshold or 0.0)
    if threshold <= 0:
        return dataframe, None, ()
    bodypart_masks = {}
    for bodypart in ALMA_BODYPARTS:
        likelihood_column = f"{bodypart} likelihood"
        if likelihood_column not in dataframe.columns:
            continue
        likelihood = pd.to_numeric(dataframe[likelihood_column], errors="coerce")
        valid = likelihood.ge(threshold).fillna(False)
        if not bool(valid.any()):
            raise ValueError(
                f"Tracking confidence filter removed every {bodypart} point at likelihood cutoff {threshold:.2f}. "
                "Lower the cutoff, set it to 0, or check body-part mapping."
            )
        bodypart_masks[bodypart] = valid
    if not bodypart_masks:
        return dataframe, None, (
            "Tracking confidence filter skipped: no ALMA likelihood columns were found.",
        )
    valid_mask = pd.DataFrame(bodypart_masks, index=dataframe.index)
    low_confidence_count = int((~valid_mask).sum().sum())
    total_count = int(valid_mask.shape[0] * valid_mask.shape[1])
    if low_confidence_count == 0:
        return dataframe, valid_mask, (
            f"Tracking confidence filter: all frames met the {threshold:.2f} likelihood cutoff.",
        )
    filtered = dataframe.copy()
    filtered_any_coordinates = False
    for bodypart, valid in bodypart_masks.items():
        coordinate_columns = [
            column
            for column in (f"{bodypart} x", f"{bodypart} y")
            if column in filtered.columns
        ]
        if not coordinate_columns:
            continue
        filtered_any_coordinates = True
        filtered.loc[~valid, coordinate_columns] = float("nan")
        interpolated = (
            filtered.loc[:, coordinate_columns]
            .apply(pd.to_numeric, errors="coerce")
            .interpolate(method="linear", limit_direction="both")
        )
        if interpolated.isna().any().any():
            raise ValueError(
                f"Tracking confidence filter could not interpolate {bodypart} at cutoff {threshold:.2f}."
            )
        filtered.loc[:, coordinate_columns] = interpolated
    if not filtered_any_coordinates:
        return dataframe, valid_mask, (
            "Tracking confidence filter skipped: no ALMA x/y coordinate columns were found.",
        )
    message = (
        f"Tracking confidence filter: interpolated {low_confidence_count}/{total_count} "
        f"low-confidence marker sample(s) below {threshold:.2f} for parameter extraction "
        "and hid those marker positions from stickplots."
    )
    return filtered, valid_mask, (message,)


def hide_low_confidence_stickplot_frames(coords, valid_mask):
    if len(coords) != len(valid_mask):
        return coords
    masked = coords.copy()
    for bodypart in valid_mask.columns:
        coordinate_columns = [
            column
            for column in (f"{bodypart} x", f"{bodypart} y")
            if column in masked.columns
        ]
        if coordinate_columns:
            masked.loc[~valid_mask[bodypart].to_numpy(), coordinate_columns] = float("nan")
    return masked


def _rustlab1_marker_for_view(marker, view: str, view_mappings) -> str:
    key = _marker_key(marker)
    mapped = _view_mapping_for_marker(view_mappings, view, marker)
    if mapped:
        key = _marker_key(mapped)
    if key.startswith(("l-", "r-", "d-")):
        return key
    if view == "left":
        return _side_view_marker(key, "l")
    if view == "right":
        return _side_view_marker(key, "r")
    return _bottom_view_marker(key)


def _looks_like_view_mapping(mapping: dict) -> bool:
    return any(view in mapping for view in ("left", "right", "bottom"))


def _view_mapping_for_marker(view_mappings, view: str, marker) -> str | None:
    if not view_mappings:
        return None
    mapping = view_mappings.get(view)
    if not mapping:
        return None
    marker_text = str(marker)
    if marker_text in mapping:
        return mapping[marker_text]
    normalized_marker = _marker_key(marker_text)
    for raw, standard in mapping.items():
        if _marker_key(raw) == normalized_marker:
            return standard
    return None


def _side_view_marker(marker: str, prefix: str) -> str:
    marker = _strip_view_prefix(marker)
    aliases = {
        "toe": "back-toe",
        "toe-tip": "back-toe",
        "back-toe-tip": "back-toe",
        "ankle": "back-ankle",
        "back-ankle": "back-ankle",
        "hip": "hip",
        "back-hip": "hip",
        "iliac-crest": "iliac-crest",
        "crest": "iliac-crest",
        "back-iliac-crest": "iliac-crest",
        "mtp": "back-mtp",
        "knee": "back-knee",
        "front-toe": "front-toe-tip",
        "front-toe-tip": "front-toe-tip",
        "wrist": "wrist",
        "elbow": "elbow",
        "ellbow": "elbow",
        "shoulder": "shoulder",
    }
    return f"{prefix}-{aliases.get(marker, marker)}"


def _bottom_view_marker(marker: str) -> str:
    marker = _strip_view_prefix(marker)
    aliases = {
        "center": "center-back",
        "centre": "center-back",
        "center-back": "center-back",
        "centre-back": "center-back",
        "back-center": "center-back",
        "back-centre": "center-back",
        "left": "back-left",
        "left-back": "back-left",
        "back-left": "back-left",
        "right": "back-right",
        "right-back": "back-right",
        "back-right": "back-right",
        "center-front": "center-front",
        "centre-front": "center-front",
        "front-center": "center-front",
        "front-centre": "center-front",
        "left-front": "front-left",
        "front-left": "front-left",
        "right-front": "front-right",
        "front-right": "front-right",
    }
    return f"d-{aliases.get(marker, marker)}"


def _strip_view_prefix(marker: str) -> str:
    for prefix in ("left-", "right-", "bottom-", "down-", "camera-left-", "camera-right-"):
        if marker.startswith(prefix):
            return marker[len(prefix) :]
    return marker


def _marker_key(marker) -> str:
    key = str(marker).strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in key:
        key = key.replace("--", "-")
    return key
