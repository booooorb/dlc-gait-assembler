"""Infer recording groups and camera roles from filenames and sibling view folders without list-order pairing."""

from __future__ import annotations

import re
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet

VIEW_ALIASES = {
    "left": {"left", "lhs", "lview", "leftview", "leftside"},
    "right": {"right", "rhs", "rview", "rightview", "rightside"},
    "bottom": {"bottom", "down", "ventral", "below", "bview", "dview", "bottomview", "downview", "underside", "underneath"},
}
VIEW_TOKENS = set().union(*VIEW_ALIASES.values())


def suggest_view_set(paths: list[Path]) -> AlmaViewCsvSet:
    sets, _ = build_view_csv_sets(paths)
    if not sets:
        raise ValueError("No unambiguous left/right/bottom recording was found. Assign its views manually.")
    return sets[0]


def build_view_csv_sets(paths: list[Path], bodyparts_by_path=None) -> tuple[list[AlmaViewCsvSet], list[str]]:
    sets, errors = [], []
    for row in build_view_pair_rows(paths, bodyparts_by_path):
        if row["status"] != "Ready":
            errors.append(f"{row['name']}: {row['status']}.")
        else:
            sets.append(AlmaViewCsvSet(row["name"], row["left"], row["right"], row["bottom"]))
    return sets, errors


def build_view_pair_rows(paths: list[Path], bodyparts_by_path=None) -> list[dict[str, object]]:
    grouped = {}
    rows = []
    for path in sorted(set(Path(p).expanduser().resolve() for p in paths)):
        view, issue = csv_view_evidence(path, (bodyparts_by_path or {}).get(path, ()))
        if view is None:
            rows.append(
                {
                    "name": path.stem,
                    "left": None,
                    "right": None,
                    "bottom": None,
                    "status": issue or "Unclassified view",
                    "unassigned": (path,),
                }
            )
            continue
        parent = recording_folder(path)
        group = grouped.setdefault((parent, csv_view_group_key(path)), {})
        group.setdefault(view, []).append(path)
    for group_key, group in sorted(grouped.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        missing = [view for view in VIEW_ALIASES if view not in group]
        duplicates = [view for view in VIEW_ALIASES if len(group.get(view, [])) > 1]
        status = [f"Duplicate {view}" for view in duplicates]
        if missing:
            status.append("Missing " + ", ".join(missing))
        rows.append(
            {
                "name": view_group_label(group_key),
                **{view: group[view][0] if len(group.get(view, [])) == 1 else None for view in VIEW_ALIASES},
                "status": "; ".join(status) or "Ready",
                "unassigned": tuple(path for view in duplicates for path in group[view]),
            }
        )
    # Distinct directories may contain identically named recordings. Avoid output collisions.
    counts = {name: sum(row["name"] == name for row in rows) for name in {row["name"] for row in rows}}
    used = set()
    for row in rows:
        base = row["name"]
        if counts[base] > 1:
            path = next((row[v] for v in VIEW_ALIASES if row[v] is not None), None)
            path = path or next(iter(row.get("unassigned", ())), None)
            folder = recording_folder(path).name if path else "set"
            base = f"{folder}_{base}"
        name, suffix = base, 2
        while name in used:
            name, suffix = f"{base}_{suffix}", suffix + 1
        row["name"] = name
        used.add(name)
    return rows


def path_name(path) -> str:
    return Path(path).name if path is not None else "—"


def _view_in_tokens(tokens) -> str | None:
    matches = [view for view, aliases in VIEW_ALIASES.items() if set(tokens) & aliases]
    return matches[0] if len(matches) == 1 else None


def _directory_view(directory: Path) -> str | None:
    tokens = re.split("[^a-z0-9]+", directory.name.lower())
    if all(token in VIEW_TOKENS | {"camera", "view", "side", ""} for token in tokens):
        return _view_in_tokens(tokens)
    return None


def recording_folder(path):
    directory = path.parent
    camera_folder = re.fullmatch(r"cam(?:era)?[_ -]?[a-z0-9]+", directory.name.lower())
    return directory.parent if _directory_view(directory) or camera_folder else directory


def csv_view_from_name(path: Path) -> str | None:
    tokens = filename_token_list(path)
    matches = [view for view, aliases in VIEW_ALIASES.items() if set(tokens) & aliases]
    if len(matches) > 1:
        return None
    folder = _directory_view(path.parent)
    if matches and folder and matches[0] != folder:
        return None
    return matches[0] if matches else folder


def csv_view_from_bodyparts(bodyparts) -> str | None:
    """Only infer laterality from explicit labels; generic toe/ankle labels are insufficient."""
    labels = {re.sub("[^a-z0-9]", "", str(label).lower()) for label in bodyparts}
    left_paws = {"lhpaw", "dbackleft", "lefthindpaw", "hindpawleft"}
    right_paws = {"rhpaw", "dbackright", "righthindpaw", "hindpawright"}
    matches = ["bottom"] if labels & left_paws and labels & right_paws else []
    for side, prefix in (("left", "l"), ("right", "r")):
        count = sum(any(label in labels for label in (
            f"{prefix}back{marker}", f"{side}{marker}", f"{marker}{prefix}", f"{side}hind{marker}",
        )) for marker in ("toe", "ankle", "knee", "mtp", "hip"))
        if count >= 2:
            matches.append(side)
    return matches[0] if len(matches) == 1 else None


def csv_view_evidence(path, bodyparts=()):
    filename_views = {view for view, aliases in VIEW_ALIASES.items() if set(filename_token_list(path)) & aliases}
    folder_view = _directory_view(path.parent)
    if len(filename_views) > 1:
        return None, "Conflicting camera names"
    named = next(iter(filename_views), None)
    if named and folder_view and named != folder_view:
        return None, "Filename and folder disagree"
    marker_view = csv_view_from_bodyparts(bodyparts)
    named = named or folder_view
    if named and marker_view and named != marker_view:
        return None, f"Camera name says {named}; labels say {marker_view}"
    return named or marker_view, ""


def csv_view_group_key(path: Path) -> str:
    tokens = [token for token in filename_token_list(path) if token not in VIEW_TOKENS | {"view", "camera", "side"}]
    return "_".join(tokens) or "recording"


def normalized_bodypart_label(label: str) -> str:
    return " ".join(label.strip().lower().replace("_", " ").replace("-", " ").split())


def view_group_label(group_key: tuple[Path, str]) -> str:
    return group_key[1] or "view_set"


def filename_token_list(path: Path) -> list[str]:
    # DLC scorer/model names may differ between cameras; they are not recording identity.
    stem = re.split(r"DLC", path.stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stem = re.sub(r"(?i)(?:[_ -](?:filtered|knee[_ -]corrected))+$", "", stem)
    stem = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem)
    return [token for token in re.split("[^a-z0-9]+", stem.lower()) if token]
