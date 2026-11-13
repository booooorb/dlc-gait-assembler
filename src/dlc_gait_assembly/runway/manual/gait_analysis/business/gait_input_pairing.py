"""Infer recording groups and camera roles from filenames and sibling view folders without list-order pairing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_recording_similarity import (
    natural_recording_key,
    recording_identity_fields,
    recording_identity_tokens,
    recording_name_similarity,
)

VIEW_ALIASES = {
    "left": {"left", "l", "lhs", "lview", "leftview", "leftside", "leftcam", "leftcamera", "camleft"},
    "right": {"right", "r", "rhs", "rview", "rightview", "rightside", "rightcam", "rightcamera", "camright"},
    "bottom": {"bottom", "b", "bot", "down", "downward", "ventral", "below", "bview", "dview", "bottomview",
               "downview", "underside", "underneath", "bottomcam", "bottomcamera", "cambottom"},
}
VIEW_TOKENS = set().union(*VIEW_ALIASES.values())
CAMERA_WORDS = {"view", "camera", "cam", "side"}
EXPORT_WORDS = {"csv", "csvs", "coordinates", "exports", "export", "filtered", "processed", "corrected"}


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
    bodyparts_by_path = normalized_bodyparts_by_path(bodyparts_by_path)
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
    grouped = merge_similar_recordings(grouped)
    for group_key, group in sorted(grouped.items(), key=lambda item: (str(item[0][0]), natural_recording_key(item[0][1]))):
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
    return sorted(rows, key=lambda row: (row["status"] != "Ready", natural_recording_key(row["name"])))


def normalized_bodyparts_by_path(bodyparts_by_path=None):
    return {Path(key).expanduser().resolve(): tuple(value) for key, value in (bodyparts_by_path or {}).items()}


def merge_similar_recordings(grouped):
    """Merge only mutual best matches, with a clear margin and agreement across every view."""
    grouped = dict(grouped)
    while True:
        keys = list(grouped)
        best = {}
        for key in keys:
            group = grouped[key]
            if any(len(paths) > 1 for paths in group.values()):
                continue
            candidates = []
            for other in keys:
                other_group = grouped[other]
                if key == other or key[0] != other[0] or group.keys() & other_group.keys():
                    continue
                if any(len(paths) > 1 for paths in other_group.values()):
                    continue
                score = min(recording_name_similarity(csv_view_group_key(left), csv_view_group_key(right))
                            for paths in group.values() for left in paths
                            for other_paths in other_group.values() for right in other_paths)
                if score >= 74:
                    candidates.append((score, other))
            # Equally good right and bottom files complement each other. Two equally good
            # right files compete, so neither should be assigned automatically.
            best[key] = [other for score, other in candidates if score >= 82 and not any(
                rival != other and grouped[other].keys() & grouped[rival].keys() and score - rival_score < 8
                for rival_score, rival in candidates
            )]
        merged = set()
        for key, choices in best.items():
            if key in merged:
                continue
            other = next((other for other in choices if other not in merged and key in best.get(other, ())), None)
            if other is not None:
                grouped[key].update(grouped.pop(other))
                merged.update((key, other))
        if not merged:
            return grouped


def path_name(path) -> str:
    return Path(path).name if path is not None else "—"


def _view_in_tokens(tokens) -> str | None:
    matches = [view for view, aliases in VIEW_ALIASES.items() if set(tokens) & aliases]
    return matches[0] if len(matches) == 1 else None


@lru_cache(maxsize=8192)
def _directory_view(directory: Path) -> str | None:
    if re.fullmatch(r"cam(?:era)?[_ -]?[a-z0-9]", directory.name.casefold()):
        return None  # Camera A/B/C are identifiers, not bottom/left/right abbreviations.
    tokens = filename_token_list(Path(directory.name + ".csv"))
    if all(token in VIEW_TOKENS | CAMERA_WORDS | EXPORT_WORDS for token in tokens):
        return _view_in_tokens(tokens)
    return None


@lru_cache(maxsize=8192)
def recording_folder(path):
    directory = path.parent
    while directory != directory.parent:
        camera_folder = re.fullmatch(r"cam(?:era)?[_ -]?[a-z0-9]+", directory.name.lower())
        if not (_directory_view(directory) or camera_folder or directory.name.casefold() in EXPORT_WORDS):
            break
        directory = directory.parent
    return directory


def csv_folder_view(path: Path) -> str | None:
    directory = path.parent
    while directory != directory.parent:
        view = _directory_view(directory)
        if view or directory.name.casefold() not in EXPORT_WORDS:
            return view
        directory = directory.parent
    return None


def csv_view_from_name(path: Path) -> str | None:
    return csv_view_evidence(path)[0]


def csv_view_from_bodyparts(bodyparts) -> str | None:
    """Only infer laterality from explicit labels; generic toe/ankle labels are insufficient."""
    return _bodypart_view(tuple(str(label) for label in bodyparts))


@lru_cache(maxsize=8192)
def _bodypart_view(bodyparts: tuple[str, ...]) -> str | None:
    labels = {re.sub("[^a-z0-9]", "", str(label).lower()) for label in bodyparts}
    left_paws = {"lhpaw", "lfpaw", "hlpaw", "flpaw", "dbackleft", "dfrontleft", "backleft", "frontleft", "leftback", "leftfront",
                 "lefthindpaw", "hindpawleft", "leftforepaw", "forepawleft", "hl", "fl", "lh", "lf"}
    right_paws = {"rhpaw", "rfpaw", "hrpaw", "frpaw", "dbackright", "dfrontright", "backright", "frontright", "rightback", "rightfront",
                  "righthindpaw", "hindpawright", "rightforepaw", "forepawright", "hr", "fr", "rh", "rf"}
    matches = ["bottom"] if labels & left_paws and labels & right_paws else []
    for side, prefix in (("left", "l"), ("right", "r")):
        count = sum(any(label in labels for alias in (prefix, side)
                        for location in ("", "back", "hind", "hindlimb", "front", "fore", "forelimb")
                        for suffix in (("", "tip") if marker == "toe" else ("",))
                        for label in (f"{alias}{location}{marker}{suffix}", f"{location}{alias}{marker}{suffix}",
                                      f"{location}{marker}{suffix}{alias}"))
                    for marker in ("toe", "ankle", "knee", "mtp", "hip", "iliaccrest", "crest", "wrist", "elbow", "shoulder"))
        if count >= 2:
            matches.append(side)
    return matches[0] if len(matches) == 1 else None


def csv_view_evidence(path, bodyparts=()):
    return _csv_view_evidence(path, tuple(str(label) for label in bodyparts))


@lru_cache(maxsize=8192)
def _csv_view_evidence(path: Path, bodyparts: tuple[str, ...]):
    filename_views = {view for view, aliases in VIEW_ALIASES.items() if set(filename_token_list(path)) & aliases}
    folder_view = csv_folder_view(path)
    if len(filename_views) > 1:
        return None, "Conflicting camera names"
    named = next(iter(filename_views), None)
    if named and folder_view and named != folder_view:
        return None, "Filename and folder disagree"
    # The scorer may be called LEFT or BOTTOM even when the source video has no
    # camera suffix. Use that as a fallback; never include the scorer in recording identity.
    if not named and not folder_view:
        model = re.split(r"DLC", path.stem, maxsplit=1, flags=re.IGNORECASE)
        model_tokens = set(name_token_list(model[1])) if len(model) > 1 else set()
        model_views = {view for view, aliases in VIEW_ALIASES.items() if model_tokens & (aliases - {"l", "r", "b"})}
        if len(model_views) > 1:
            return None, "Conflicting camera names in model"
        named = next(iter(model_views), None)
    marker_view = csv_view_from_bodyparts(bodyparts)
    named = named or folder_view
    if named and marker_view and named != marker_view:
        return None, f"Camera name says {named}; labels say {marker_view}"
    return named or marker_view, ""


@lru_cache(maxsize=8192)
def csv_view_group_key(path: Path) -> str:
    tokens = [token for token in filename_token_list(path)
              if token not in VIEW_TOKENS | CAMERA_WORDS | EXPORT_WORDS and not re.fullmatch(r"cam(?:era)?\d+", token)]
    return "_".join(tokens) or "recording"


def normalized_bodypart_label(label: str) -> str:
    return " ".join(label.strip().lower().replace("_", " ").replace("-", " ").split())


def view_group_label(group_key: tuple[Path, str]) -> str:
    return group_key[1] or "view_set"


def filename_token_list(path: Path) -> list[str]:
    # DLC scorer/model names may differ between cameras; they are not recording identity.
    stem = re.split(r"DLC", path.stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stem = re.sub(r"(?i)(?:[_ -](?:filtered|knee[_ -]corrected))+$", "", stem)
    tokens = name_token_list(stem)
    # Camera A/B/C and Camera 1/2/3 identify capture devices, not animal/trial IDs.
    skip = {index + 1 for index, token in enumerate(tokens[:-1])
            if token in {"cam", "camera"} and (tokens[index + 1].isdigit() or len(tokens[index + 1]) == 1)}
    return [token for index, token in enumerate(tokens) if index not in skip]


def name_token_list(stem: str) -> list[str]:
    stem = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", stem)
    stem = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", stem)
    stem = re.sub(r"(?i)(\d)(left|right|bottom|ventral|underside|down)(?=$|[^a-z])", r"\1_\2", stem)
    return [token for token in re.split("[^a-z0-9]+", stem.lower()) if token]


@dataclass(frozen=True)
class RankedCsvCandidate:
    path: Path
    score: float
    reasons: tuple[str, ...]


def rank_view_candidates(paths, view, *, recording="", reference_paths=(), bodyparts_by_path=None,
                         used_paths=(), animal_id="") -> list[RankedCsvCandidate]:
    """Rank manual choices using labels, camera names, recording identity and current assignments."""
    bodyparts = bodyparts_by_path or {}
    references = tuple(reference_paths)
    used = set(used_paths)
    ranked = []
    for candidate in paths:
        labels = csv_view_from_bodyparts(bodyparts.get(candidate, ()))
        inferred, issue = csv_view_evidence(candidate, bodyparts.get(candidate, ()))
        inferred = labels or inferred
        score, reasons = 0.0, []
        if inferred == view:
            score += 45 if labels else 40
            reasons.append(f"{view.title()} body-part labels" if labels else f"{view.title()} camera name")
        elif inferred:
            score -= 80
            reasons.append(f"Appears to be {inferred} view")
        else:
            reasons.append(issue or "View needs review")
        identity = csv_view_group_key(candidate)
        similarities = [recording_name_similarity(identity, csv_view_group_key(reference)) for reference in references]
        if not references and recording and not re.fullmatch(r"recording_\d+", recording):
            similarities = [recording_name_similarity(identity, recording)]
        if similarities:
            similarity = min(similarities)
            score += 0.55 * similarity if similarity else -35
            if similarity:
                reasons.append(f"Recording name similarity {similarity:.0f}%")
            else:
                reasons.append("Different recording identity")
        if references and all(recording_folder(candidate) == recording_folder(reference) for reference in references):
            score += 5
            reasons.append("Same recording folder")
        if animal_id.strip():
            animal = recording_identity_fields(identity).get("mouse")
            expected = recording_identity_fields(f"mouse_{animal_id}").get("mouse")
            # An Animal ID may already include its own mouse/M prefix.
            expected = recording_identity_fields(animal_id).get("mouse", expected)
            if animal and expected:
                score += 15 if animal == expected else -50
                reasons.append("Same mouse ID" if animal == expected else "Different mouse ID")
            elif set(recording_identity_tokens(animal_id)) <= set(recording_identity_tokens(identity)):
                score += 15
                reasons.append("Same mouse name")
        if issue:
            reasons.append(issue)
        if candidate in used:
            score -= 120
            reasons.append("Already assigned to another recording")
        ranked.append(RankedCsvCandidate(candidate, score, tuple(dict.fromkeys(reasons))))
    return sorted(ranked, key=lambda item: (-item.score, natural_recording_key(item.path.name), str(item.path)))
