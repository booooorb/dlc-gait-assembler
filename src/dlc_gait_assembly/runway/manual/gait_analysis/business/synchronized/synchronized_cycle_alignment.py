"""Align feature rows to authoritative canonical cycle boundaries without changing stride identity."""

from __future__ import annotations

from dataclasses import asdict

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


def canonical_cycles_from_alma(alma_parameters, trajectories, metadata, pd, np):
    """Build synchronized-cycle metadata without re-detecting ALMA strides.

    ALMA's stride start/end columns are authoritative. Bottom-view stance
    states are used only for synchronized phase, overlap, and QC measures
    inside those already-detected windows.
    """
    left_stance = _debounce_boolean(
        trajectories["left_stance"].fillna(False).to_numpy(dtype=bool), minimum_run=2, np=np
    )
    right_stance = _debounce_boolean(
        trajectories["right_stance"].fillna(False).to_numpy(dtype=bool), minimum_run=2, np=np
    )
    right_onsets = _onsets(right_stance, np)
    session_id = metadata.session_id or metadata.animal_id or "session"
    metadata_values = asdict(metadata)
    if metadata.lesion_hemisphere == "right":
        (contralesional_side, ipsilesional_side) = ("left", "right")
    elif metadata.lesion_hemisphere == "left":
        (contralesional_side, ipsilesional_side) = ("right", "left")
    else:
        contralesional_side = ipsilesional_side = "unknown"
    rows = []
    for index, parameter_row in alma_parameters.reset_index(drop=True).iterrows():
        try:
            start = int(float(parameter_row["stride_start (frame)"]))
            end = int(float(parameter_row["stride_end (frame)"]))
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError(f"ALMA stride row {index + 1} has invalid frame boundaries.") from exc
        if start < 0 or end < start:
            raise ValueError(f"ALMA stride row {index + 1} has invalid frame boundaries: {start}-{end}.")
        in_range = end < len(trajectories)
        right_candidates = right_onsets[(right_onsets >= start) & (right_onsets <= end)]
        right_start = int(right_candidates[0]) if len(right_candidates) else None
        left_stance_end = _stance_end(left_stance, start, end) if in_range else None
        right_stance_end = _stance_end(right_stance, right_start, end) if in_range and right_start is not None else None
        cycle_trajectory = trajectories.loc[start:end]
        coverage = (
            float(cycle_trajectory["required_tracking_valid"].astype(float).mean()) if len(cycle_trajectory) else 0.0
        )
        duration_frames = end - start + 1
        overlap_frames = _interval_overlap(start, left_stance_end, right_start, right_stance_end)
        row_valid = in_range and right_start is not None and (coverage >= 1.0)
        rejection_reasons = []
        if not in_range:
            rejection_reasons.append("alma_stride_out_of_range")
        if right_start is None:
            rejection_reasons.append("missing_right_stance_onset")
        if coverage < 1.0:
            rejection_reasons.append("required_marker_gap")
        rows.append(
            {
                **metadata_values,
                "session_id": session_id,
                "cycle_id": f"{session_id}:cycle-{index + 1:04d}",
                "contralesional_side": contralesional_side,
                "ipsilesional_side": ipsilesional_side,
                "stride_start (frame)": start,
                "stride_end (frame)": end,
                "left_stance_start_frame": start,
                "left_stance_end_frame": left_stance_end,
                "right_stance_start_frame": right_start,
                "right_stance_end_frame": right_stance_end,
                "cycle_duration_frames": duration_frames,
                "left_right_hindlimb_phase_offset": 100.0 * (right_start - start) / duration_frames
                if right_start is not None
                else np.nan,
                "hindlimb_stance_overlap_fraction": 100.0 * overlap_frames / duration_frames,
                "tracking_coverage": coverage,
                "cycle_valid": bool(row_valid),
                "rejection_reason": ";".join(rejection_reasons),
            }
        )
    return pd.DataFrame(rows, columns=CANONICAL_CYCLE_COLUMNS)


def align_feature_rows_to_cycles(cycles, feature_rows, feature_names, pd, np):
    """Select feature columns only after verifying exact ALMA stride identity."""
    source = feature_rows.reset_index(drop=True)
    canonical = cycles.reset_index(drop=True)
    if len(source) != len(canonical):
        raise ValueError("Post-ALMA feature rows do not match the number of authoritative ALMA strides.")
    for column in ("stride_start (frame)", "stride_end (frame)"):
        source_bounds = pd.to_numeric(source[column], errors="coerce").to_numpy(dtype=float)
        canonical_bounds = pd.to_numeric(canonical[column], errors="coerce").to_numpy(dtype=float)
        if not np.array_equal(source_bounds, canonical_bounds, equal_nan=True):
            raise ValueError(f"Post-ALMA feature rows changed authoritative ALMA {column} values.")
    return source.reindex(columns=list(feature_names)).reset_index(drop=True)


def align_parameters_to_cycles(cycles, parameters, side: str, pd, np):
    """One-to-one overlap alignment of an ALMA table to canonical source frames."""
    output = []
    used_rows: set[int] = set()
    parameters = parameters.reset_index(drop=True)
    for _, cycle in cycles.iterrows():
        try:
            start = int(float(cycle["stride_start (frame)"]))
            end = int(float(cycle["stride_end (frame)"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            # ALMA can retain a stationary-recording row without a stride window.
            # Preserve its measurements without inventing an opposite-side match.
            values = {f"{side}__{column}": np.nan for column in parameters.columns}
            values[f"{side}__cycle_match_iou"] = 0.0
            values[f"{side}__cycle_match_valid"] = False
            output.append(values)
            continue
        best_index = None
        best_iou = 0.0
        for row_index, row in parameters.iterrows():
            if row_index in used_rows:
                continue
            try:
                candidate_start = int(float(row["stride_start (frame)"]))
                candidate_end = int(float(row["stride_end (frame)"]))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            intersection = max(0, min(end, candidate_end) - max(start, candidate_start) + 1)
            union = max(end, candidate_end) - min(start, candidate_start) + 1
            iou = intersection / union if union else 0.0
            if iou > best_iou:
                best_iou = iou
                best_index = int(row_index)
        if best_index is None or best_iou < 0.5:
            values = {f"{side}__{column}": np.nan for column in parameters.columns}
            values[f"{side}__cycle_match_iou"] = best_iou
            values[f"{side}__cycle_match_valid"] = False
        else:
            used_rows.add(best_index)
            values = {f"{side}__{column}": value for (column, value) in parameters.loc[best_index].items()}
            values[f"{side}__cycle_match_iou"] = best_iou
            values[f"{side}__cycle_match_valid"] = True
        output.append(values)
    return pd.DataFrame(output)
