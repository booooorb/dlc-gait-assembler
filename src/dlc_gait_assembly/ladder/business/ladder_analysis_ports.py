"""Define Ladder coordinate inspection, scientific execution, and event-export interfaces."""

from pathlib import Path
from typing import Protocol

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderRunResult, LadderSettings


class LadderCoordinateInputPort(Protocol):
    def read(self, path: Path) -> tuple: ...

    def bodyparts(self, path: Path) -> list[str]: ...


class LadderEventExportPort(Protocol):
    def write(self, events, destination: Path, combined: bool = False) -> Path: ...


class LadderScientificExecutionPort(Protocol):
    def __call__(
        self, csv_file: Path, output_folder: Path, settings: LadderSettings, bodyparts: list[str] | None = None
    ) -> LadderRunResult: ...
