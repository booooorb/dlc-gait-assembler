"""Operations and storage required by the automatic run coordinator."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_use_cases import KneeCorrectionUseCases
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_use_cases import VideoProcessingUseCases


@dataclass(frozen=True)
class AutomaticStageOperations:
    video: VideoProcessingUseCases
    knee: KneeCorrectionUseCases
    gait: Callable
    deeplabcut_analysis: Callable
    labeled_videos: Callable
    stickplots: Callable


class AutomaticRunStoragePort(Protocol):
    def allocate(self, run, project_root, output_root, profile): ...

    def is_file(self, path): ...

    def video_settings(self, manifest): ...

    def knee_settings(self, manifest): ...

    def gait_settings(self, manifest, calibration): ...

    def persist_knee_replacements(self, run, pairs, settings, corrected, progress): ...

    def write_manifest(self, run, result): ...
