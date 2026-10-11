"""Preserve fallback canonical-cycle detection for synchronized analysis."""

from __future__ import annotations

from dataclasses import asdict

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    CANONICAL_CYCLE_COLUMNS,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_feature_calculations import (
    interval_overlap as _interval_overlap,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    debounce_boolean as _debounce_boolean,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    onsets as _onsets,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_signal_operations import (
    stance_end as _stance_end,
)


def detect_canonical_cycles(trajectories, settings: AlmaSettings, metadata, pd, np):
    """Detect left-onset cycles and pair the right stance onset by source frame."""
    left_stance = _debounce_boolean(
        trajectories["left_stance"].fillna(False).to_numpy(dtype=bool), minimum_run=2, np=np
    )
    right_stance = _debounce_boolean(
        trajectories["right_stance"].fillna(False).to_numpy(dtype=bool), minimum_run=2, np=np
    )
    left_onsets = _onsets(left_stance, np)
    right_onsets = _onsets(right_stance, np)
    rows = []
    session_id = metadata.session_id or metadata.animal_id or "session"
    metadata_values = asdict(metadata)
    if metadata.lesion_hemisphere == "right":
        (contralesional_side, ipsilesional_side) = ("left", "right")
    elif metadata.lesion_hemisphere == "left":
        (contralesional_side, ipsilesional_side) = ("right", "left")
    else:
        contralesional_side = ipsilesional_side = "unknown"
    for index, (start, next_start) in enumerate(zip(left_onsets[:-1], left_onsets[1:], strict=True), start=1):
        end = int(next_start) - 1
        right_candidates = right_onsets[(right_onsets >= start) & (right_onsets < next_start)]
        right_start = int(right_candidates[0]) if len(right_candidates) else None
        left_stance_end = _stance_end(left_stance, int(start), end)
        right_stance_end = _stance_end(right_stance, right_start, end) if right_start is not None else None
        coverage = float(trajectories.loc[start:end, "required_tracking_valid"].astype(float).mean())
        overlap_frames = _interval_overlap(int(start), left_stance_end, right_start, right_stance_end)
        duration_frames = max(1, int(next_start) - int(start))
        row_valid = right_start is not None and coverage >= 1.0
        rejection_reasons = []
        if right_start is None:
            rejection_reasons.append("missing_right_stance_onset")
        if coverage < 1.0:
            rejection_reasons.append("required_marker_gap")
        rows.append(
            {
                **metadata_values,
                "session_id": session_id,
                "cycle_id": f"{session_id}:cycle-{index:04d}",
                "contralesional_side": contralesional_side,
                "ipsilesional_side": ipsilesional_side,
                "stride_start (frame)": int(start),
                "stride_end (frame)": end,
                "left_stance_start_frame": int(start),
                "left_stance_end_frame": left_stance_end,
                "right_stance_start_frame": right_start,
                "right_stance_end_frame": right_stance_end,
                "cycle_duration_frames": duration_frames,
                "left_right_hindlimb_phase_offset": 100.0 * (right_start - int(start)) / duration_frames
                if right_start is not None
                else np.nan,
                "hindlimb_stance_overlap_fraction": 100.0 * overlap_frames / duration_frames,
                "tracking_coverage": coverage,
                "cycle_valid": bool(row_valid),
                "rejection_reason": ";".join(rejection_reasons),
            }
        )
    return pd.DataFrame(rows, columns=CANONICAL_CYCLE_COLUMNS)
