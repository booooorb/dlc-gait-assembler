"""Define synchronized stride, general-parameter, and session-summary output schemas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StrokeOutputBundle:
    canonical_cycles: Path
    stride_features: Path
    session_summary: Path
    primary_stroke_panel: Path
    feature_dictionary: Path
    qc_report: Path
    messages: tuple[str, ...] = ()

    @property
    def output_files(self) -> tuple[Path, ...]:
        return (
            self.canonical_cycles,
            self.stride_features,
            self.session_summary,
            self.primary_stroke_panel,
            self.feature_dictionary,
            self.qc_report,
        )
