"""Score recording-name similarity while protecting animal, trial, and session identities."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache

IDENTITY_PREFIXES = {
    "m": "mouse", "animal": "mouse", "subject": "mouse", "mouse": "mouse",
    "mouseid": "mouse", "animalid": "mouse", "subjectid": "mouse",
    "trial": "trial", "run": "trial", "segment": "segment", "seg": "segment",
    "session": "session", "day": "day", "dpi": "day", "timepoint": "day", "clip": "clip",
}
GENERIC_WORDS = {"recording", "video", "runway", "treadmill", "export", "csv", "coordinates", "data"}


@lru_cache(maxsize=8192)
def recording_identity_tokens(name: str) -> tuple[str, ...]:
    tokens = re.findall(r"[a-z]+|\d+", name.casefold())
    normalized = [str(int(token)) if token.isdigit() else IDENTITY_PREFIXES.get(token, token) for token in tokens]
    return tuple(token for index, token in enumerate(normalized)
                 if token != "id" or index == 0 or normalized[index - 1] not in IDENTITY_PREFIXES.values())


def recording_identity_fields(name: str) -> dict[str, str]:
    tokens = recording_identity_tokens(name)
    return {token: tokens[index + 1] for index, token in enumerate(tokens[:-1])
            if token in IDENTITY_PREFIXES.values() and tokens[index + 1] not in IDENTITY_PREFIXES.values()}


@lru_cache(maxsize=8192)
def recording_name_similarity(first: str, second: str) -> float:
    """Return 0–100; fuzzy text never overrides conflicting IDs or recording numbers."""
    left, right = recording_identity_tokens(first), recording_identity_tokens(second)
    if not left or not right:
        return 0.0
    left_fields, right_fields = recording_identity_fields(first), recording_identity_fields(second)
    if any(left_fields[field] != right_fields[field] for field in left_fields.keys() & right_fields.keys()):
        return 0.0
    left_numbers = Counter(token for token in left if token.isdigit())
    right_numbers = Counter(token for token in right if token.isdigit())
    if left_numbers and right_numbers and left_numbers != right_numbers:
        return 0.0
    # Unlabelled dates/timestamps must retain their order. Labelled mouse/trial
    # fields may move around the filename because their identities are checked above.
    left_unlabelled = tuple(token for index, token in enumerate(left)
                            if token.isdigit() and (index == 0 or left[index - 1] not in IDENTITY_PREFIXES.values()))
    right_unlabelled = tuple(token for index, token in enumerate(right)
                             if token.isdigit() and (index == 0 or right[index - 1] not in IDENTITY_PREFIXES.values()))
    if left_unlabelled and right_unlabelled and left_unlabelled != right_unlabelled:
        return 0.0
    if Counter(left) == Counter(right):
        return 100.0
    common = Counter(left) & Counter(right)
    if not any(token not in GENERIC_WORDS for token in common):
        return 0.0
    overlap = 2 * sum(common.values()) / (len(left) + len(right))
    text = SequenceMatcher(None, " ".join(sorted(left)), " ".join(sorted(right)), autojunk=False).ratio()
    return 100 * (0.75 * overlap + 0.25 * text)


def natural_recording_key(value: str) -> tuple:
    return tuple((0, int(token)) if token.isdigit() else (1, token.casefold())
                 for token in re.split(r"(\d+)", value))
