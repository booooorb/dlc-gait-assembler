"""Define matched camera inputs, study identifiers, and preprocessed coordinate snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import LesionHemisphere


@dataclass(frozen=True)
class StrokeStudyMetadata:
    """Animal/session identifiers carried into every scientific output row."""

    animal_id: str = ""
    group: str = ""
    sex: str = ""
    lesion_hemisphere: LesionHemisphere = "unknown"
    timepoint: str = ""
    trial: str = ""
    session_id: str = ""


@dataclass(frozen=True)
class AlmaViewCsvSet:
    name: str
    left_csv: Path
    right_csv: Path
    bottom_csv: Path
    metadata: StrokeStudyMetadata | None = None

    @property
    def alma_csv(self) -> Path:
        return self.left_csv


@dataclass(frozen=True)
class AlmaPreprocessedCoordinates:
    """Coordinate series prepared with ALMA's configured filtering contract."""

    columns: dict[tuple[str, str], object]
    series: dict[str, dict[str, object | None]]
    frame_count: int
    likelihood_threshold: float
    frame_rate: float
    filter_cutoff: float
