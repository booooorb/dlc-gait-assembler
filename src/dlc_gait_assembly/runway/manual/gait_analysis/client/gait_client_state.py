"""GaitClientState owns selections, editable state, and preview validity for this workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_validity import GaitPreviewValidity


@dataclass
class GaitClientState:
    profile_analysis_manifest_path: Path | None = None
    selected_files: list[Path] = field(default_factory=lambda: [])
    view_sets: list[AlmaViewCsvSet] = field(default_factory=lambda: [])
    view_set_errors: list[str] = field(default_factory=lambda: [])
    manual_view_sets: list[AlmaViewCsvSet] | None = None
    output_preview_paths: tuple[Path, ...] = ()
    preview_validity: GaitPreviewValidity = field(default_factory=GaitPreviewValidity)
    preview_svg_data: tuple[tuple[str, bytes], ...] | None = None
    preview_source_name: str = ""
    calibration_map_path: Path | None = None
    calibration_map_source: str = ""
    raw_bodyparts: list[str] = field(default_factory=lambda: [])
    view_label_mappings: dict[str, dict[str, dict[str, str]]] = field(default_factory=lambda: {})
