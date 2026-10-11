"""Summary loading and cohort result export required by numerical cohort use cases."""

from pathlib import Path
from typing import Protocol


class CohortSummaryReaderPort(Protocol):
    def read_summaries(self, paths, pandas): ...


class CohortResultExportPort(CohortSummaryReaderPort, Protocol):
    def prepare(self, destination: Path) -> None: ...
    def write_table(self, table, destination: Path, **options) -> None: ...
    def export_calculation(self, calculation, destination: Path): ...
