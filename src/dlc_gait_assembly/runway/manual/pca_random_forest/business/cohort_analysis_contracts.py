"""Define cohort inputs, feature selection, numerical analyses, and returned artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CohortAnalysisResult:
    output_files: tuple[Path, ...]
    messages: tuple[str, ...]


@dataclass(frozen=True)
class CohortTable:
    name: str
    dataframe: object
    include_index: bool = False


@dataclass(frozen=True)
class CohortCalculationResult:
    tables: tuple[CohortTable, ...]
    figures: dict[str, object]
    message: str
