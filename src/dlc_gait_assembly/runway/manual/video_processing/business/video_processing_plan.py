"""Resolve each source video into separate crop, inversion, flip, trim, and enhancement jobs."""

from __future__ import annotations

from dataclasses import dataclass, replace

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange


def trim_sort_key(trim: TrimRange) -> tuple[int, int]:
    return (trim.start_ms, trim.end_ms)


def normalized_trim_ranges(trim_ranges: tuple[TrimRange, ...]) -> tuple[TrimRange, ...]:
    sorted_ranges = sorted((trim for trim in trim_ranges if trim.is_usable()), key=trim_sort_key)
    merged: list[TrimRange] = []
    for trim in sorted_ranges:
        if not merged or trim.start_ms > merged[-1].end_ms:
            merged.append(trim)
            continue
        previous = merged[-1]
        merged[-1] = TrimRange(previous.start_ms, max(previous.end_ms, trim.end_ms))
    return tuple(merged)


@dataclass(frozen=True)
class VideoProcessingJob:
    options: ProcessingOptions
    region_name: str | None
    region_folder: bool


def plan_video_outputs(input_path, options):
    """Resolve this video's flip assignments and the independently exported crop jobs."""
    if options.crop_regions:
        options = replace(
            options, crop_regions=tuple(region.resolved_for_input(input_path) for region in options.crop_regions)
        )
    regions = options.effective_crop_regions()
    if not regions:
        return (VideoProcessingJob(options, None, False),)
    return tuple(
        VideoProcessingJob(
            replace(options, crop_enabled=True, crop_rect=region.rect, crop_regions=(region,)),
            region.name,
            len(regions) > 1,
        )
        for region in regions
    )
