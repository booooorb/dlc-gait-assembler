"""Define paired coordinate inputs, knee settings, reconstruction reports, and corrected results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CoordinateFilePair:
    directory: Path
    stem: str
    csv_paths: tuple[Path, ...] = ()
    h5_paths: tuple[Path, ...] = ()
    video_paths: tuple[Path, ...] = ()

    @property
    def is_paired(self) -> bool:
        return len(self.csv_paths) == 1 and len(self.h5_paths) == 1 and (len(self.video_paths) == 1)

    @property
    def csv_path(self) -> Path | None:
        return self.csv_paths[0] if len(self.csv_paths) == 1 else None

    @property
    def h5_path(self) -> Path | None:
        return self.h5_paths[0] if len(self.h5_paths) == 1 else None

    @property
    def video_path(self) -> Path | None:
        return self.video_paths[0] if len(self.video_paths) == 1 else None

    @property
    def status(self) -> str:
        if self.is_paired:
            return "Paired"
        problems = []
        for label, paths in (("CSV", self.csv_paths), ("H5", self.h5_paths), ("Video", self.video_paths)):
            if not paths:
                problems.append(f"Missing {label}")
            elif len(paths) > 1:
                problems.append(f"Duplicate {label}")
        return " + ".join(problems) if problems else "Incomplete"


@dataclass(frozen=True)
class KneeCorrectionSettings:
    hip_knee_length_cm: float
    knee_ankle_length_cm: float
    pixels_per_cm: float
    likelihood_threshold: float = 0.0
    knee_bodyparts: tuple[str, ...] | None = None
    hip_bodypart: str | None = None
    ankle_bodypart: str | None = None
    output_knee_bodypart: str = "knee"
    knee_direction: str = "auto"


@dataclass(frozen=True)
class KneeMarkerReport:
    knee: str
    hip: str
    ankle: str
    hip_knee_length: float
    knee_ankle_length: float
    corrected_frames: int
    retained_frames: int
    frame_statuses: tuple[str, ...]


@dataclass(frozen=True)
class KneeCorrectionResult:
    source_csv: Path
    source_h5: Path
    source_video: Path
    output_csv: Path
    output_h5: Path
    markers: tuple[KneeMarkerReport, ...]
