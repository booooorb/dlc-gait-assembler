"""Resolve body-part aliases, limb sides, segment endpoints, and target knee markers."""

from __future__ import annotations

import re

import pandas as pd

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings


def coordinate_columns(dataframe: pd.DataFrame) -> dict[tuple[tuple[str, ...], str], dict[str, tuple]]:
    result: dict[tuple[tuple[str, ...], str], dict[str, tuple]] = {}
    for raw_column in dataframe.columns:
        column = tuple(raw_column)
        prefix = tuple(str(value) for value in column[:-2])
        bodypart = str(column[-2])
        coordinate = str(column[-1]).casefold()
        result.setdefault((prefix, bodypart), {})[coordinate] = raw_column
    return result


def knee_targets(
    columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]], settings: KneeCorrectionSettings
) -> tuple[tuple[tuple[str, ...], str], ...]:
    if settings.knee_bodyparts:
        targets: list[tuple[tuple[str, ...], str]] = []
        for requested in settings.knee_bodyparts:
            requested_label = clean_output_knee_bodypart(requested)
            existing = [
                (prefix, bodypart)
                for ((prefix, bodypart), coordinates) in columns.items()
                if bodypart.casefold() == requested_label.casefold() and {"x", "y"}.issubset(coordinates)
            ]
            if existing:
                targets.extend(existing)
            else:
                targets.extend(
                    (prefix, requested_label)
                    for prefix in prefixes_with_endpoint_pair(requested_label, columns, settings)
                )
        return tuple(sorted(dict.fromkeys(targets), key=lambda item: (str(item[0]), item[1].casefold())))
    existing_knees = [
        (prefix, bodypart)
        for ((prefix, bodypart), coordinates) in columns.items()
        if "knee" in bodypart.casefold() and {"x", "y"}.issubset(coordinates)
    ]
    if existing_knees:
        return tuple(sorted(existing_knees, key=lambda item: (str(item[0]), item[1].casefold())))
    output_label = clean_output_knee_bodypart(settings.output_knee_bodypart)
    return tuple((prefix, output_label) for prefix in prefixes_with_endpoint_pair(output_label, columns, settings))


def prefixes_with_endpoint_pair(
    knee_bodypart: str, columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]], settings: KneeCorrectionSettings
) -> tuple[tuple[str, ...], ...]:
    prefixes = sorted({prefix for (prefix, _bodypart) in columns}, key=str)
    matches: list[tuple[str, ...]] = []
    for prefix in prefixes:
        try:
            selected_or_matching_bodypart(knee_bodypart, "hip", settings.hip_bodypart, prefix, columns)
            selected_or_matching_bodypart(knee_bodypart, "ankle", settings.ankle_bodypart, prefix, columns)
        except ValueError:
            continue
        matches.append(prefix)
    return tuple(matches)


def clean_output_knee_bodypart(bodypart: str | None) -> str:
    cleaned = str(bodypart or "").strip()
    if not cleaned:
        raise ValueError("Output knee label must not be blank.")
    return cleaned


def normalised_knee_direction(direction: str) -> str:
    normalised = str(direction or "auto").strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "auto": "auto",
        "automatic": "auto",
        "side_a": "positive",
        "a": "positive",
        "positive": "positive",
        "plus": "positive",
        "side_b": "negative",
        "b": "negative",
        "negative": "negative",
        "minus": "negative",
    }
    if normalised not in aliases:
        raise ValueError("Knee direction must be auto, side A, or side B.")
    return aliases[normalised]


def new_knee_columns(dataframe: pd.DataFrame, prefix: tuple[str, ...], bodypart: str) -> dict[str, tuple]:
    if len(prefix) != dataframe.columns.nlevels - 2:
        raise ValueError("Could not create a knee label for this DeepLabCut table.")
    return {"x": (*prefix, bodypart, "x"), "y": (*prefix, bodypart, "y")}


def matching_bodypart(
    knee: str, target: str, prefix: tuple[str, ...], columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]]
) -> str:
    candidates = [
        bodypart
        for (candidate_prefix, bodypart) in columns
        if candidate_prefix == prefix
        and target in bodypart.casefold()
        and {"x", "y"}.issubset(columns[candidate_prefix, bodypart])
    ]
    if not candidates:
        raise ValueError(f'No {target} marker matches knee marker "{knee}".')
    exact = re.sub("knee", target, knee, flags=re.IGNORECASE)
    for candidate in candidates:
        if candidate.casefold() == exact.casefold():
            return candidate
    knee_side = marker_side(knee)
    ranked = sorted(
        candidates,
        key=lambda candidate: (
            marker_side(candidate) != knee_side if knee_side else False,
            -len(marker_tokens(knee, "knee") & marker_tokens(candidate, target)),
            candidate.casefold(),
        ),
    )
    return ranked[0]


def selected_or_matching_bodypart(
    knee: str,
    target: str,
    selected: str | None,
    prefix: tuple[str, ...],
    columns: dict[tuple[tuple[str, ...], str], dict[str, tuple]],
) -> str:
    if selected is None:
        return matching_bodypart(knee, target, prefix, columns)
    for candidate_prefix, bodypart in columns:
        if (
            candidate_prefix == prefix
            and bodypart.casefold() == selected.casefold()
            and {"x", "y"}.issubset(columns[candidate_prefix, bodypart])
        ):
            return bodypart
    raise ValueError(f'Selected {target} label "{selected}" was not found for knee marker "{knee}".')


def marker_side(name: str) -> str | None:
    lowered = name.casefold()
    tokens = set(filter(None, re.split("[^a-z0-9]+", lowered)))
    if "left" in tokens or "l" in tokens or lowered.startswith("l-") or lowered.endswith("l"):
        return "left"
    if "right" in tokens or "r" in tokens or lowered.startswith("r-") or lowered.endswith("r"):
        return "right"
    return None


def marker_tokens(name: str, joint: str) -> set[str]:
    lowered = name.casefold().replace(joint, " ")
    return set(filter(None, re.split("[^a-z0-9]+", lowered)))
