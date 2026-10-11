"""Detect standalone stance onsets and accepted reference-paw stride intervals."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaPreprocessedCoordinates
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    validate_rustlab1_settings as _validate_rustlab1_settings,
)


def rustlab1_stance_mask(x, settings, np):
    """The shared RustLab1 horizontal-speed rule, in source pixels per frame."""
    x = np.asarray(x, dtype=float)
    speed = np.abs(np.diff(x, prepend=x[0])) if len(x) else np.array([])
    stance = np.isfinite(speed) & (speed <= float(settings.stance_speed_threshold_px_frame))
    if len(stance) > 1:
        stance[0] = stance[1]
    stance = enforce_minimum_phase_runs(stance, max(1, int(settings.minimum_stance_frames)), True, np)
    stance = enforce_minimum_phase_runs(stance, max(1, int(settings.minimum_swing_frames)), False, np)
    return stance, speed


def detect_rustlab1_strides(
    preprocessed: AlmaPreprocessedCoordinates,
    settings: RustLab1StandaloneSettings,
    pd,
    np,
    *,
    trusted=None,
    allow_empty=False,
):
    """Detect stance-onset strides using RustLab1's bottom-paw speed rule."""
    _validate_rustlab1_settings(settings)
    marker = settings.reference_paw
    x = preprocessed.series.get(marker, {}).get("x")
    if x is None:
        raise ValueError(
            f"RustLab1 stride detection requires bottom-view marker {marker}. Check the three-view label mapping."
        )
    x = np.asarray(x, dtype=float)
    if len(x) < 2 or np.count_nonzero(np.isfinite(x)) < 2:
        raise ValueError(f"RustLab1 stride marker {marker} has insufficient valid coordinates.")
    stance, speed = rustlab1_stance_mask(x, settings, np)
    if trusted is not None:
        stance &= np.asarray(trusted, dtype=bool)
    onsets = np.flatnonzero(stance & ~np.r_[False, stance[:-1]])
    if len(onsets) < 2 and not allow_empty:
        raise ValueError(
            "RustLab1 did not detect two stance onsets. Check the reference paw, likelihood cutoff, or stance speed threshold."
        )
    rows = []
    rejected_tracking_jumps = 0
    pixels_per_cm = bottom_pixels_per_cm(settings)
    for start, next_start in zip(onsets[:-1], onsets[1:], strict=True):
        start = int(start)
        next_start = int(next_start)
        if trusted is not None and not np.asarray(trusted[start : next_start + 1], dtype=bool).all():
            continue
        maximum_speed = float(np.nanmax(speed[start:next_start]))
        if maximum_speed >= float(settings.maximum_tracking_speed_px_frame):
            rejected_tracking_jumps += 1
            continue
        end = next_start - 1
        stance_end = phase_end(stance, start, end, expected=True)
        swing_start = stance_end + 1 if stance_end < end else None
        stance_frames = stance_end - start + 1
        swing_frames = max(0, next_start - (swing_start or next_start))
        stride_length_px = float(np.nanmax(x[start:next_start]) - np.nanmin(x[start:next_start]))
        rows.append(
            {
                "gait_cycle": len(rows) + 1,
                "limb (hind left / right)": limb_label(marker),
                "reference_paw": marker,
                "stride_start (frame)": start,
                "stride_end (frame)": end,
                "stance_start (frame)": start,
                "stance_end (frame)": stance_end,
                "swing_start (frame)": swing_start,
                "swing_end (frame)": end if swing_start is not None else None,
                "cycle duration (no. frames)": next_start - start,
                "cycle duration (s)": (next_start - start) / float(settings.frame_rate),
                "stance duration (s)": stance_frames / float(settings.frame_rate),
                "swing duration (s)": swing_frames / float(settings.frame_rate),
                "stride length (px)": stride_length_px,
                "stride length (cm)": stride_length_px / pixels_per_cm
                if pixels_per_cm is not None and pixels_per_cm > 0
                else np.nan,
                "maximum paw speed (px/frame)": maximum_speed,
                "stance speed threshold (px/frame)": float(settings.stance_speed_threshold_px_frame),
                "maximum tracking speed (px/frame)": float(settings.maximum_tracking_speed_px_frame),
            }
        )
    if len(rows) < int(settings.minimum_complete_strides) and not allow_empty:
        rejection = (
            f" {rejected_tracking_jumps} candidate stride(s) met or exceeded the {settings.maximum_tracking_speed_px_frame:g} px/frame tracking-speed limit."
            if rejected_tracking_jumps
            else ""
        )
        raise ValueError(
            f"RustLab1 accepted {len(rows)} complete stride(s), but {settings.minimum_complete_strides} are required.{rejection} Check tracking, the reference paw, phase durations, or stride QC settings."
        )
    dataframe = pd.DataFrame(rows)
    dataframe.attrs["rejected_tracking_jump_strides"] = rejected_tracking_jumps
    return dataframe


def enforce_minimum_phase_runs(mask, minimum_run: int, expected: bool, np):
    result = np.asarray(mask, dtype=bool).copy()
    start = 0
    while start < len(result):
        end = start + 1
        while end < len(result) and result[end] == result[start]:
            end += 1
        if bool(result[start]) == expected and end - start < minimum_run:
            result[start:end] = not expected
        start = end
    return result


def phase_end(mask, start: int, end: int, *, expected: bool) -> int:
    index = start
    while index <= end and bool(mask[index]) == expected:
        index += 1
    return index - 1


def limb_label(marker: str) -> str:
    return "right" if marker.endswith("right") else "left"


def bottom_pixels_per_cm(settings: RustLab1StandaloneSettings) -> float | None:
    configured = (settings.view_calibration or {}).get("bottom")
    if isinstance(configured, (int, float)) and float(configured) > 0:
        return float(configured)
    if isinstance(configured, dict):
        value = configured.get("x_pixels_per_cm", configured.get("pixels_per_cm"))
        if value and float(value) > 0:
            return float(value)
    if settings.pixels_per_cm and settings.pixels_per_cm > 0:
        return float(settings.pixels_per_cm)
    return None
