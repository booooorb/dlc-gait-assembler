"""Translate processing settings into FFmpeg filter expressions without deciding which jobs to run."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.video_processing.business.video_crop_geometry import clamp_float as _clamp_float
from dlc_gait_assembly.runway.manual.video_processing.business.video_crop_geometry import normalized_to_pixel_rect
from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_plan import (
    normalized_trim_ranges as _normalized_trim_ranges,
)
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange


def build_filter_graph(
    source_width: int,
    source_height: int,
    options: ProcessingOptions,
    include_audio: bool = False,
    source_fps: float | None = None,
) -> str:
    parts: list[str] = []
    current = "[0:v]"
    if options.invert_enabled:
        for index, invert_norm in enumerate(rect for rect in options.effective_invert_rects() if rect.is_usable()):
            invert = normalized_to_pixel_rect(invert_norm, source_width, source_height)
            base = f"[base_{index}]"
            region = f"[region_{index}]"
            flipped = f"[flipped_{index}]"
            inverted = f"[v_inverted_{index}]"
            parts.append(f"{current}split=2{base}{region}")
            parts.append(f"{region}crop={invert.width}:{invert.height}:{invert.x}:{invert.y},vflip{flipped}")
            parts.append(f"{base}{flipped}overlay={invert.x}:{invert.y}{inverted}")
            current = inverted
    enhancement_filters = build_enhancement_filters(options.enhancements)
    if enhancement_filters:
        enhanced = "[v_enhanced]"
        parts.append(f"{current}{','.join(enhancement_filters)}{enhanced}")
        current = enhanced
    trim_ranges = _normalized_trim_ranges(options.trim_ranges)
    crop_regions = options.effective_crop_regions()
    crop_region = crop_regions[0] if len(crop_regions) == 1 else None
    crop_rect = options.crop_rect
    if crop_rect is None and len(crop_regions) == 1:
        crop_rect = crop_regions[0].rect
    if options.crop_enabled and crop_rect is not None and crop_rect.is_usable():
        crop = normalized_to_pixel_rect(crop_rect, source_width, source_height)
        crop_filters = [f"crop={crop.width}:{crop.height}:{crop.x}:{crop.y}"]
        if crop_region is not None and crop_region.flip_horizontal:
            crop_filters.append("hflip")
        if crop_region is not None and crop_region.flip_vertical:
            crop_filters.append("vflip")
        if trim_ranges:
            cropped = "[v_cropped]"
            parts.append(f"{current}{','.join(crop_filters)}{cropped}")
            current = cropped
        else:
            parts.append(f"{current}{','.join(crop_filters)},format=yuv420p[vout]")
            return ";".join(parts)
    if trim_ranges:
        parts.extend(build_trim_filters(current, trim_ranges, include_audio))
    elif current != "[0:v]":
        parts.append(f"{current}format=yuv420p[vout]")
    else:
        parts.append("[0:v]format=yuv420p[vout]")
    return ";".join(parts)


def build_trim_filters(current: str, trim_ranges: tuple[TrimRange, ...], include_audio: bool) -> list[str]:
    parts: list[str] = []
    if len(trim_ranges) == 1:
        trim = trim_ranges[0]
        parts.append(f"{current}{video_trim_filter(trim)},format=yuv420p[vout]")
        if include_audio:
            parts.append(
                f"[0:a]atrim=start={fmt_float(trim.start_seconds())}:end={fmt_float(trim.end_seconds())},asetpts=PTS-STARTPTS[aout]"
            )
        return parts
    video_sources = "".join(f"[trim_src_{index}]" for index in range(len(trim_ranges)))
    parts.append(f"{current}split={len(trim_ranges)}{video_sources}")
    if include_audio:
        audio_sources = "".join(f"[atrim_src_{index}]" for index in range(len(trim_ranges)))
        parts.append(f"[0:a]asplit={len(trim_ranges)}{audio_sources}")
    concat_inputs = []
    for index, trim in enumerate(trim_ranges):
        parts.append(f"[trim_src_{index}]{video_trim_filter(trim)}[vtrim_{index}]")
        concat_inputs.append(f"[vtrim_{index}]")
        if include_audio:
            parts.append(
                f"[atrim_src_{index}]atrim=start={fmt_float(trim.start_seconds())}:end={fmt_float(trim.end_seconds())},asetpts=PTS-STARTPTS[atrim_{index}]"
            )
            concat_inputs.append(f"[atrim_{index}]")
    if include_audio:
        parts.append(f"{''.join(concat_inputs)}concat=n={len(trim_ranges)}:v=1:a=1[vconcat][aout]")
        parts.append("[vconcat]format=yuv420p[vout]")
    else:
        parts.append(f"{''.join(concat_inputs)}concat=n={len(trim_ranges)}:v=1:a=0,format=yuv420p[vout]")
    return parts


def video_trim_filter(trim: TrimRange) -> str:
    return f"trim=start={fmt_float(trim.start_seconds())}:end={fmt_float(trim.end_seconds())},setpts=PTS-STARTPTS"


def build_enhancement_filters(settings: EnhancementSettings) -> list[str]:
    filters: list[str] = []
    if not settings.is_enabled():
        return filters
    if abs(settings.exposure) > 0.001 or abs(settings.black_level) > 0.001:
        filters.append(f"exposure=exposure={fmt_float(settings.exposure)}:black={fmt_float(settings.black_level)}")
    if levels_enabled(settings):
        input_black = _clamp_float(settings.input_black, 0.0, 0.99)
        input_white = _clamp_float(settings.input_white, input_black + 0.01, 1.0)
        output_black = _clamp_float(settings.output_black, 0.0, 0.99)
        output_white = _clamp_float(settings.output_white, output_black + 0.01, 1.0)
        filters.append(
            f"colorlevels=rimin={fmt_float(input_black)}:gimin={fmt_float(input_black)}:bimin={fmt_float(input_black)}:rimax={fmt_float(input_white)}:gimax={fmt_float(input_white)}:bimax={fmt_float(input_white)}:romin={fmt_float(output_black)}:gomin={fmt_float(output_black)}:bomin={fmt_float(output_black)}:romax={fmt_float(output_white)}:gomax={fmt_float(output_white)}:bomax={fmt_float(output_white)}"
        )
    effective_gamma = 1.0 / settings.tone_scale
    if abs(settings.brightness) > 0.001 or abs(settings.contrast - 1.0) > 0.001 or abs(effective_gamma - 1.0) > 0.001:
        filters.append(
            f"eq=brightness={fmt_float(settings.brightness)}:contrast={fmt_float(settings.contrast)}:gamma={fmt_float(effective_gamma)}"
        )
    if settings.sharpening > 0.001:
        filters.append(f"unsharp=5:5:{fmt_float(settings.sharpening)}:5:5:0")
    if settings.cas > 0.001:
        filters.append(f"cas=strength={fmt_float(settings.cas)}")
    return filters


def levels_enabled(settings: EnhancementSettings) -> bool:
    return any(
        (
            abs(settings.input_black) > 0.001,
            abs(settings.input_white - 1.0) > 0.001,
            abs(settings.output_black) > 0.001,
            abs(settings.output_white - 1.0) > 0.001,
        )
    )


def fmt_float(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")
