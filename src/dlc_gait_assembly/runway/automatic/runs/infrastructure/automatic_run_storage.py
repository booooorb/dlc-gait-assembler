"""Provide the run coordinator with concrete manifest and output storage adapters."""

from pathlib import Path

from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_manifest_store import (
    persist_knee_replacements,
    persist_run_manifest,
)
from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_output_layout import allocate_run_output
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
    alma_settings_from_manifest,
)
from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
    knee_settings_from_manifest,
)
from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
    video_settings_from_manifest,
)


class AutomaticRunStorage:
    allocate = staticmethod(allocate_run_output)
    video_settings = staticmethod(video_settings_from_manifest)
    knee_settings = staticmethod(knee_settings_from_manifest)
    gait_settings = staticmethod(alma_settings_from_manifest)
    persist_knee_replacements = staticmethod(persist_knee_replacements)
    write_manifest = staticmethod(persist_run_manifest)

    def is_file(self, path):
        return Path(path).is_file()
