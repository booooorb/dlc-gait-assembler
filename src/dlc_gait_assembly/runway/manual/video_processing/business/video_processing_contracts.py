"""Define video regions, trims, enhancements, export options, processing jobs, and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import CropRegion, NormalizedRect
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange


@dataclass(frozen=True)
class ProcessingOptions:
    crop_enabled: bool = False
    crop_rect: NormalizedRect | None = None
    crop_regions: tuple[CropRegion, ...] = ()
    invert_enabled: bool = False
    invert_rect: NormalizedRect | None = None
    invert_rects: tuple[NormalizedRect, ...] = ()
    enhancements: EnhancementSettings = field(default_factory=EnhancementSettings)
    trim_ranges: tuple[TrimRange, ...] = ()
    crf: int = 18
    preset: str = "slow"

    def has_work(self) -> bool:
        has_crop = bool(self.effective_crop_regions())
        has_invert = self.invert_enabled and any(rect.is_usable() for rect in self.effective_invert_rects())
        return has_crop or has_invert or self.enhancements.is_enabled() or self.has_trim()

    def effective_crop_regions(self) -> tuple[CropRegion, ...]:
        if not self.crop_enabled:
            return ()
        if self.crop_regions:
            return tuple(region for region in self.crop_regions if region.rect.is_usable())
        if self.crop_rect is not None and self.crop_rect.is_usable():
            return (CropRegion("Region", self.crop_rect),)
        return ()

    def effective_invert_rects(self) -> tuple[NormalizedRect, ...]:
        if self.invert_rects:
            return self.invert_rects
        if self.invert_rect is not None:
            return (self.invert_rect,)
        return ()

    def has_trim(self) -> bool:
        return any(trim.is_usable() for trim in self.trim_ranges)


@dataclass(frozen=True)
class ProcessingResult:
    input_path: Path
    output_path: Path
    command: list[str]
    crop_region_name: str | None = None


@dataclass(frozen=True)
class VideoSettingsSnapshot:
    """Current processing controls and per-input trim selections."""

    options: ProcessingOptions
    trim_ranges_by_path: dict[str, tuple[TrimRange, ...]]
