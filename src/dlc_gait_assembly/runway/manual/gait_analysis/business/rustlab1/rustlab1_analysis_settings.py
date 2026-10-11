"""Define standalone RustLab1 detection, reference-paw, calibration, and stride-QC settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RustLab1ReferencePaw = Literal["d-back-left", "d-back-right", "d-front-left", "d-front-right"]
RUSTLAB1_REFERENCE_PAWS: tuple[RustLab1ReferencePaw, ...] = (
    "d-back-left",
    "d-back-right",
    "d-front-left",
    "d-front-right",
)


@dataclass(frozen=True)
class RustLab1StandaloneSettings:
    """Settings used only by the standalone RustLab1 workflow."""

    n_continuous_strides: int = 10
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


def validate_rustlab1_settings(settings: RustLab1StandaloneSettings) -> None:
    if settings.frame_rate <= 0:
        raise ValueError("RustLab1 frame rate must be greater than zero.")
    if settings.filter_cutoff <= 0 or settings.filter_cutoff >= settings.frame_rate / 2.0:
        raise ValueError(
            "RustLab1 filter cutoff must be greater than zero and below the Nyquist frequency (half the frame rate)."
        )
    if not 0.0 <= settings.likelihood_threshold <= 1.0:
        raise ValueError("RustLab1 likelihood threshold must be between 0 and 1.")
    if settings.stance_speed_threshold_px_frame < 0:
        raise ValueError("RustLab1 stance speed threshold cannot be negative.")
    if settings.maximum_tracking_speed_px_frame <= settings.stance_speed_threshold_px_frame:
        raise ValueError("RustLab1 maximum tracking speed must be greater than the stance speed threshold.")
    if settings.minimum_stance_frames < 1 or settings.minimum_swing_frames < 1:
        raise ValueError("RustLab1 minimum stance and swing durations must be at least one frame.")
    if settings.minimum_complete_strides < 1:
        raise ValueError("RustLab1 minimum complete strides must be at least one.")
    if settings.reference_paw not in RUSTLAB1_REFERENCE_PAWS:
        raise ValueError(f"Unsupported RustLab1 reference paw: {settings.reference_paw}")
