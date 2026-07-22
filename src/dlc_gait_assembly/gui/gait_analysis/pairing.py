"""Pure filename-based pairing for multiview gait-analysis CSV files."""

from __future__ import annotations

import re
from pathlib import Path

from dlc_gait_assembly.services.pipeline.alma import AlmaViewCsvSet


def suggest_view_set(paths: list[Path]) -> AlmaViewCsvSet:
    by_view: dict[str, Path] = {}
    for path in paths:
        view = csv_view_from_name(path)
        if view is not None and view not in by_view:
            by_view[view] = path
    remaining = [path for path in paths if path not in by_view.values()]
    for view in ("left", "right", "bottom"):
        if view not in by_view and remaining:
            by_view[view] = remaining.pop(0)
    return AlmaViewCsvSet(
        name=csv_view_group_key(by_view.get("left", paths[0])) if paths else "set_1",
        left_csv=by_view.get("left", paths[0]),
        right_csv=by_view.get("right", paths[min(1, len(paths) - 1)]),
        bottom_csv=by_view.get("bottom", paths[min(2, len(paths) - 1)]),
    )


def build_view_csv_sets(paths: list[Path]) -> tuple[list[AlmaViewCsvSet], list[str]]:
    rows = build_view_pair_rows(paths)
    view_sets: list[AlmaViewCsvSet] = []
    errors: list[str] = []
    for row in rows:
        if row["status"] != "Ready":
            errors.append(f"{row['name']}: {row['status']}.")
            continue
        view_sets.append(
            AlmaViewCsvSet(
                name=row["name"],
                left_csv=row["left"],
                right_csv=row["right"],
                bottom_csv=row["bottom"],
            )
        )
    return view_sets, errors


def build_view_pair_rows(paths: list[Path]) -> list[dict[str, object]]:
    grouped: dict[tuple[Path, str], dict[str, Path]] = {}
    rows: list[dict[str, object]] = []
    for path in paths:
        view = csv_view_from_name(path)
        if view is None:
            rows.append(
                {
                    "name": path.stem,
                    "left": None,
                    "right": None,
                    "bottom": None,
                    "status": "Unclassified view",
                }
            )
            continue
        group_key = (path.parent, csv_view_group_key(path))
        group = grouped.setdefault(group_key, {})
        if view in group:
            rows.append(
                {
                    "name": _view_group_label(group_key),
                    "left": path if view == "left" else None,
                    "right": path if view == "right" else None,
                    "bottom": path if view == "bottom" else None,
                    "status": f"Duplicate {view}",
                }
            )
            continue
        group[view] = path

    for group_key, group in sorted(
        grouped.items(),
        key=lambda item: (str(item[0][0]), item[0][1]),
    ):
        missing = [view for view in ("left", "right", "bottom") if view not in group]
        rows.append(
            {
                "name": _view_group_label(group_key),
                "left": group.get("left"),
                "right": group.get("right"),
                "bottom": group.get("bottom"),
                "status": "Ready" if not missing else "Missing " + ", ".join(missing),
            }
        )
    return rows


def path_name(path) -> str:
    return Path(path).name if path is not None else "-"


def csv_view_from_name(path: Path) -> str | None:
    tokens = set(_filename_token_list(path))
    stem = path.stem.lower()
    if tokens & {"left", "lhs", "lview"} or "leftview" in stem:
        return "left"
    if tokens & {"right", "rhs", "rview"} or "rightview" in stem:
        return "right"
    if (
        tokens & {"bottom", "down", "ventral", "below", "bview", "dview"}
        or "bottomview" in stem
        or "downview" in stem
    ):
        return "bottom"
    return None


def csv_view_group_key(path: Path) -> str:
    view_tokens = {
        "left", "lhs", "lview", "right", "rhs", "rview",
        "bottom", "down", "ventral", "below", "bview", "dview",
    }
    tokens = [token for token in _filename_token_list(path) if token not in view_tokens]
    return "_".join(tokens) or path.stem.lower()


def normalized_bodypart_label(label: str) -> str:
    return " ".join(label.strip().lower().replace("_", " ").replace("-", " ").split())


def _view_group_label(group_key: tuple[Path, str]) -> str:
    _parent, key = group_key
    return key or "view_set"


def _filename_token_list(path: Path) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", path.stem.lower()) if token]
