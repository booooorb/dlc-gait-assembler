"""Calculate deviations from baseline phases within each animal."""

from __future__ import annotations


def add_baseline_phase_deviation(data, pd):
    result = data.copy()
    source = "left_right_hindlimb_phase_offset"
    target = "hindlimb_phase_offset_deviation_from_baseline"
    if source not in result:
        return result
    result[target] = float("nan")
    for _animal_id, indices in result.groupby("animal_id").groups.items():
        animal = result.loc[indices]
        baseline_mask = animal["timepoint"].map(is_baseline)
        if baseline_mask.any():
            baseline = pd.to_numeric(animal.loc[baseline_mask, source], errors="coerce").median()
        else:
            order = animal["timepoint"].map(timepoint_order)
            earliest = order.min()
            baseline = pd.to_numeric(animal.loc[order == earliest, source], errors="coerce").median()
        result.loc[indices, target] = pd.to_numeric(animal[source], errors="coerce") - baseline
    return result


def is_baseline(value: str) -> bool:
    normalized = str(value).strip().casefold().replace(" ", "")
    return normalized in {"baseline", "base", "bl", "0", "0d", "day0", "0dpi"}


def timepoint_order(value: str) -> float:
    text = str(value).strip().casefold()
    if is_baseline(text):
        return 0.0
    number = "".join(character for character in text if character.isdigit() or character in ".-")
    try:
        return float(number)
    except ValueError:
        return float("inf")
