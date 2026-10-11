"""Apply per-view body-part mappings and preserve synchronized frame correspondence."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings


def align_multiview_coordinates(view_frames, pd, view_mappings: dict[str, dict[str, str]] | None = None):
    frames = []
    for view, frame in view_frames.items():
        columns = []
        for column in frame.columns:
            if isinstance(column, tuple) and len(column) >= 2:
                (marker, coord) = (column[0], column[1])
            else:
                parts = str(column).rsplit(" ", 1)
                (marker, coord) = (parts[0], parts[1]) if len(parts) == 2 else (column, "")
            columns.append((rustlab1_marker_for_view(marker, view, view_mappings), str(coord).strip().lower()))
        frame = frame.copy()
        frame.columns = pd.MultiIndex.from_tuples(columns)
        frames.append(frame)
    return pd.concat(frames, axis=1)


def view_mappings_for_set(settings: AlmaSettings, set_name: str) -> dict[str, dict[str, str]] | None:
    mappings = settings.view_bodypart_mapping
    if not mappings:
        return None
    if looks_like_view_mapping(mappings):
        return mappings
    candidate = mappings.get(set_name) if isinstance(mappings, dict) else None
    if isinstance(candidate, dict) and looks_like_view_mapping(candidate):
        return candidate
    return None


def view_mapping_for(view_mappings: dict[str, dict[str, str]] | None, view: str) -> dict[str, str] | None:
    if not view_mappings:
        return None
    mapping = view_mappings.get(view)
    return mapping if isinstance(mapping, dict) else None


def rustlab1_marker_for_view(marker, view: str, view_mappings) -> str:
    key = marker_key(marker)
    mapped = view_mapping_for_marker(view_mappings, view, marker)
    if mapped:
        key = marker_key(mapped)
    if key.startswith(("l-", "r-", "d-")):
        return key
    if view == "left":
        return side_view_marker(key, "l")
    if view == "right":
        return side_view_marker(key, "r")
    return bottom_view_marker(key)


def looks_like_view_mapping(mapping: dict) -> bool:
    return any(view in mapping for view in ("left", "right", "bottom"))


def view_mapping_for_marker(view_mappings, view: str, marker) -> str | None:
    if not view_mappings:
        return None
    mapping = view_mappings.get(view)
    if not mapping:
        return None
    marker_text = str(marker)
    if marker_text in mapping:
        return mapping[marker_text]
    normalized_marker = marker_key(marker_text)
    for raw, standard in mapping.items():
        if marker_key(raw) == normalized_marker:
            return standard
    return None


def side_view_marker(marker: str, prefix: str) -> str:
    marker = strip_view_prefix(marker)
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


def bottom_view_marker(marker: str) -> str:
    marker = strip_view_prefix(marker)
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
        "lhpaw": "back-left",
        "rhpaw": "back-right",
        "lfpaw": "front-left",
        "rfpaw": "front-right",
    }
    return f"d-{aliases.get(marker, aliases.get(marker.replace('-', ''), marker))}"


def strip_view_prefix(marker: str) -> str:
    for prefix in ("left-", "right-", "bottom-", "down-", "camera-left-", "camera-right-"):
        if marker.startswith(prefix):
            return marker[len(prefix) :]
    return marker


def marker_key(marker) -> str:
    key = str(marker).strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in key:
        key = key.replace("--", "-")
    return key
