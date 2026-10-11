"""Select candidate paw markers and translate Ladder detection defaults."""

from __future__ import annotations

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderSettings


def ladder_settings_from_alma_config(config: dict) -> LadderSettings:
    """Translate ALMA's ladder keys from ``config.yaml`` into typed settings."""
    threshold = config.get("threshold")
    if threshold in (None, ""):
        threshold = None
    return LadderSettings(
        frame_rate=float(config.get("frame_rate", 120.0)),
        likelihood_threshold=float(config.get("likelihood_threshold", 0.1)),
        depth_threshold=float(config.get("depth_threshold", 0.8)),
        threshold=None if threshold is None else float(threshold),
    )


def suggested_ladder_bodyparts(bodyparts: list[str]) -> list[str]:
    """Prefer distal paw/toe markers, matching ALMA's ladder workflow."""
    distal = [bodypart for bodypart in bodyparts if any(token in bodypart.lower() for token in ("toe", "paw", "foot"))]
    return distal or list(bodyparts)
