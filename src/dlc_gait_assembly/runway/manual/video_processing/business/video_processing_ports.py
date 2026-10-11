"""Required video exporter and manifest persistence capabilities."""

from pathlib import Path
from typing import Protocol

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import (
    ProcessingOptions,
    ProcessingResult,
)


class VideoExporterPort(Protocol):
    def export(
        self,
        source: Path,
        destination: Path,
        options: ProcessingOptions,
        region_name: str | None,
        region_folder: bool,
        *,
        feedback=None,
    ) -> ProcessingResult: ...


class VideoSettingsStorePort(Protocol):
    def read(self, path: Path) -> tuple: ...

    def write(self, path: Path, options: ProcessingOptions, trims: dict) -> Path: ...


class VideoSessionDocumentPort(Protocol):
    def __call__(
        self,
        session_dir: Path,
        video_paths: list,
        outputs: list,
        failures: list,
        options: ProcessingOptions,
        trim_ranges_by_path: dict,
    ) -> dict: ...
