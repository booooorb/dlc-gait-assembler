"""Standalone three-view RustLab1 stride detection and analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.services.pipeline.alma.models import AlmaViewCsvSet
from dlc_gait_assembly.services.pipeline.alma.multiview import (
    merge_multiview_rustlab1_dataframe,
    view_mappings_for_set,
)
from dlc_gait_assembly.services.pipeline.rustlab1.extraction import (
    AlmaPreprocessedCoordinates,
    extract_rustlab1_parameters,
    prepare_alma_coordinates,
)
from dlc_gait_assembly.services.pipeline.rustlab1.figures import generate_rustlab1_figures

RustLab1ReferencePaw = Literal[
    "d-back-left",
    "d-back-right",
    "d-front-left",
    "d-front-right",
]

RUSTLAB1_REFERENCE_PAWS: tuple[RustLab1ReferencePaw, ...] = (
    "d-back-left",
    "d-back-right",
    "d-front-left",
    "d-front-right",
)


@dataclass(frozen=True)
class RustLab1StandaloneSettings:
    """Settings used only by the standalone RustLab1 workflow."""

    frame_rate: float = 60.0
    filter_cutoff: float = 6.0
    likelihood_threshold: float = 0.95
    stance_speed_threshold_px_frame: float = 7.0
    maximum_tracking_speed_px_frame: float = 100.0
    minimum_stance_frames: int = 1
    minimum_swing_frames: int = 1
    minimum_complete_strides: int = 1
    reference_paw: RustLab1ReferencePaw = "d-back-left"
    limb_scope: str = "Hindlimb + Forelimb"
    calibration_method: str = "manual"
    reference_segment: str = "ankle_toe"
    reference_length_cm: float = 1.5
    pixels_per_cm: float | None = None
    view_calibration: dict[str, object] | None = None
    view_bodypart_mapping: dict[str, object] | None = None
    enabled_parameter_names: tuple[str, ...] | None = None
    generate_figures: bool = True


@dataclass(frozen=True)
class RustLab1RunResult:
    input_file: Path
    output_files: tuple[Path, ...]
    messages: tuple[str, ...] = ()


def detect_rustlab1_strides(
    preprocessed: AlmaPreprocessedCoordinates,
    settings: RustLab1StandaloneSettings,
    pd,
    np,
):
    """Detect stance-onset strides using RustLab1's bottom-paw speed rule."""
    _validate_rustlab1_settings(settings)
    marker = settings.reference_paw
    x = preprocessed.series.get(marker, {}).get("x")
    if x is None:
        raise ValueError(
            f"RustLab1 stride detection requires bottom-view marker {marker}. "
            "Check the three-view label mapping."
        )
    x = np.asarray(x, dtype=float)
    if len(x) < 2 or np.count_nonzero(np.isfinite(x)) < 2:
        raise ValueError(f"RustLab1 stride marker {marker} has insufficient valid coordinates.")

    speed = np.abs(np.diff(x, prepend=x[0]))
    stance = np.isfinite(speed) & (
        speed <= float(settings.stance_speed_threshold_px_frame)
    )
    # ``prepend`` gives frame zero an artificial speed of zero. Match the
    # original RustLab1 diff-based phase assignment by inheriting frame 1,
    # which avoids a false stance onset when a recording begins in swing.
    if len(stance) > 1:
        stance[0] = stance[1]
    stance = _enforce_minimum_phase_runs(
        stance,
        max(1, int(settings.minimum_stance_frames)),
        True,
        np,
    )
    stance = _enforce_minimum_phase_runs(
        stance,
        max(1, int(settings.minimum_swing_frames)),
        False,
        np,
    )
    onsets = np.flatnonzero(stance & ~np.r_[False, stance[:-1]])
    if len(onsets) < 2:
        raise ValueError(
            "RustLab1 did not detect two stance onsets. Check the reference paw, "
            "likelihood cutoff, or stance speed threshold."
        )

    rows = []
    rejected_tracking_jumps = 0
    pixels_per_cm = _bottom_pixels_per_cm(settings)
    for start, next_start in zip(onsets[:-1], onsets[1:], strict=True):
        start = int(start)
        next_start = int(next_start)
        maximum_speed = float(np.nanmax(speed[start:next_start]))
        if maximum_speed >= float(settings.maximum_tracking_speed_px_frame):
            rejected_tracking_jumps += 1
            continue
        end = next_start - 1
        stance_end = _phase_end(stance, start, end, expected=True)
        swing_start = stance_end + 1 if stance_end < end else None
        stance_frames = stance_end - start + 1
        swing_frames = max(0, next_start - (swing_start or next_start))
        stride_length_px = float(np.nanmax(x[start:next_start]) - np.nanmin(x[start:next_start]))
        rows.append(
            {
                "gait_cycle": len(rows) + 1,
                "limb (hind left / right)": _limb_label(marker),
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
                "stride length (cm)": (
                    stride_length_px / pixels_per_cm
                    if pixels_per_cm is not None and pixels_per_cm > 0
                    else np.nan
                ),
                "maximum paw speed (px/frame)": maximum_speed,
                "stance speed threshold (px/frame)": float(
                    settings.stance_speed_threshold_px_frame
                ),
                "maximum tracking speed (px/frame)": float(
                    settings.maximum_tracking_speed_px_frame
                ),
            }
        )
    if len(rows) < int(settings.minimum_complete_strides):
        rejection = (
            f" {rejected_tracking_jumps} candidate stride(s) met or exceeded the "
            f"{settings.maximum_tracking_speed_px_frame:g} px/frame tracking-speed limit."
            if rejected_tracking_jumps
            else ""
        )
        raise ValueError(
            f"RustLab1 accepted {len(rows)} complete stride(s), but "
            f"{settings.minimum_complete_strides} are required.{rejection} "
            "Check tracking, the reference paw, phase durations, or stride QC settings."
        )
    dataframe = pd.DataFrame(rows)
    dataframe.attrs["rejected_tracking_jump_strides"] = rejected_tracking_jumps
    return dataframe


def run_rustlab1_analysis(
    view_sets: list[AlmaViewCsvSet],
    output_folder: Path,
    settings: RustLab1StandaloneSettings,
    alma_root: Path,
    progress_callback=None,
) -> list[RustLab1RunResult]:
    """Run RustLab1 only on paired left/right/bottom coordinate CSVs."""
    if not view_sets:
        raise ValueError("Standalone RustLab1 analysis requires at least one three-view CSV set.")
    _validate_rustlab1_settings(settings)

    import matplotlib
    import numpy as np
    import pandas as pd

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    from dlc_gait_assembly.services.pipeline.alma.runner import (
        load_kinematics_functions,
    )

    kinematics = load_kinematics_functions(Path(alma_root))
    output_folder = Path(output_folder).expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)
    results = []
    total = len(view_sets)
    for index, view_set in enumerate(view_sets, start=1):
        if progress_callback is not None:
            progress_callback(index, total, f"RustLab1: processing {view_set.name}")
        view_mappings = view_mappings_for_set(settings, view_set.name)
        merged = merge_multiview_rustlab1_dataframe(view_set, pd, view_mappings)
        preprocessed = prepare_alma_coordinates(merged, settings, kinematics)
        strides = detect_rustlab1_strides(preprocessed, settings, pd, np)
        extraction = extract_rustlab1_parameters(
            merged,
            strides,
            settings,
            kinematics,
            preprocessed,
        )
        if extraction.dataframe is None:
            raise ValueError(
                f"RustLab1 markers were not found for {view_set.name}. Check label mapping."
            )

        stem = view_set.name
        stride_path = output_folder / f"{stem}_rustlab1_strides.csv"
        parameters_path = output_folder / f"{stem}_rustlab1_parameters.csv"
        summary_path = output_folder / f"{stem}_rustlab1_summary.csv"
        preview_path = output_folder / f"{stem}_rustlab1_stride_preview.svg"
        strides.to_csv(stride_path, index=False)
        extraction.dataframe.to_csv(parameters_path, index=False)
        _summarize_rustlab1(extraction.dataframe, pd, np).to_csv(summary_path, index=False)
        generate_rustlab1_stride_preview(
            preprocessed,
            strides,
            preview_path,
            settings,
            plt,
            np,
        )
        output_files = [stride_path, parameters_path, summary_path, preview_path]
        if settings.generate_figures:
            output_files.extend(
                generate_rustlab1_figures(
                    merged,
                    strides,
                    extraction,
                    output_folder / f"{stem}_rustlab1_figures",
                    settings,
                    kinematics,
                    plt,
                    preprocessed,
                )
            )
        messages = [
            f"RustLab1: detected {len(strides)} stride(s) from {settings.reference_paw}.",
            f"RustLab1: calculated {len(extraction.available_parameters)} selected parameter(s).",
        ]
        rejected_tracking_jumps = int(
            strides.attrs.get("rejected_tracking_jump_strides", 0)
        )
        if rejected_tracking_jumps:
            messages.append(
                "RustLab1 stride QC: rejected "
                f"{rejected_tracking_jumps} candidate stride(s) at or above "
                f"{settings.maximum_tracking_speed_px_frame:g} px/frame."
            )
        if extraction.missing_markers:
            messages.append("RustLab1 missing markers: " + ", ".join(extraction.missing_markers))
        results.append(
            RustLab1RunResult(
                input_file=Path(view_set.bottom_csv),
                output_files=tuple(output_files),
                messages=tuple(messages),
            )
        )
    return results


def generate_rustlab1_stride_preview(
    preprocessed,
    strides,
    output_path: Path,
    settings,
    plt,
    np,
) -> Path:
    """Render the reference-paw speed trace and detected RustLab1 strides."""
    x = np.asarray(preprocessed.series[settings.reference_paw]["x"], dtype=float)
    speed = np.abs(np.diff(x, prepend=x[0]))
    figure, axis = plt.subplots(figsize=(10, 3.8))
    frames = np.arange(len(speed))
    axis.plot(frames, speed, color="#315c8b", linewidth=1.25, label="Paw speed")
    axis.axhline(
        float(settings.stance_speed_threshold_px_frame),
        color="#d97706",
        linestyle="--",
        linewidth=1.2,
        label="Stance threshold",
    )
    for row_index, row in strides.iterrows():
        start = int(row["stride_start (frame)"])
        end = int(row["stride_end (frame)"])
        axis.axvspan(start, end, color="#22c55e", alpha=0.08 if row_index % 2 else 0.14)
        axis.axvline(start, color="#15803d", alpha=0.55, linewidth=0.8)
    axis.set_title(f"RustLab1 stride detection — {settings.reference_paw}")
    axis.set_xlabel("Frame")
    axis.set_ylabel("Absolute x speed (px/frame)")
    axis.set_xlim(0, max(1, len(speed) - 1))
    axis.legend(loc="upper right", frameon=False)
    axis.grid(axis="y", alpha=0.2)
    figure.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, format="svg", bbox_inches="tight")
    plt.close(figure)
    return output_path


def _summarize_rustlab1(dataframe, pd, np):
    numeric = dataframe.select_dtypes(include="number")
    row = {"stride_count": int(len(dataframe))}
    for column in numeric.columns:
        if column in {"gait_cycle", "stride_start (frame)", "stride_end (frame)"}:
            continue
        values = pd.to_numeric(numeric[column], errors="coerce").to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        row[column] = float(np.nanmedian(finite)) if len(finite) else np.nan
    return pd.DataFrame([row])


def _enforce_minimum_phase_runs(mask, minimum_run: int, expected: bool, np):
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


def _phase_end(mask, start: int, end: int, *, expected: bool) -> int:
    index = start
    while index <= end and bool(mask[index]) == expected:
        index += 1
    return index - 1


def _limb_label(marker: str) -> str:
    return "right" if marker.endswith("right") else "left"


def _bottom_pixels_per_cm(settings: RustLab1StandaloneSettings) -> float | None:
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


def _validate_rustlab1_settings(settings: RustLab1StandaloneSettings) -> None:
    if settings.frame_rate <= 0:
        raise ValueError("RustLab1 frame rate must be greater than zero.")
    if settings.filter_cutoff <= 0 or settings.filter_cutoff >= settings.frame_rate / 2.0:
        raise ValueError(
            "RustLab1 filter cutoff must be greater than zero and below the "
            "Nyquist frequency (half the frame rate)."
        )
    if not 0.0 <= settings.likelihood_threshold <= 1.0:
        raise ValueError("RustLab1 likelihood threshold must be between 0 and 1.")
    if settings.stance_speed_threshold_px_frame < 0:
        raise ValueError("RustLab1 stance speed threshold cannot be negative.")
    if settings.maximum_tracking_speed_px_frame <= settings.stance_speed_threshold_px_frame:
        raise ValueError(
            "RustLab1 maximum tracking speed must be greater than the stance speed threshold."
        )
    if settings.minimum_stance_frames < 1 or settings.minimum_swing_frames < 1:
        raise ValueError("RustLab1 minimum stance and swing durations must be at least one frame.")
    if settings.minimum_complete_strides < 1:
        raise ValueError("RustLab1 minimum complete strides must be at least one.")
    if settings.reference_paw not in RUSTLAB1_REFERENCE_PAWS:
        raise ValueError(f"Unsupported RustLab1 reference paw: {settings.reference_paw}")


__all__ = [
    "RUSTLAB1_REFERENCE_PAWS",
    "RustLab1RunResult",
    "RustLab1StandaloneSettings",
    "detect_rustlab1_strides",
    "generate_rustlab1_stride_preview",
    "run_rustlab1_analysis",
]
