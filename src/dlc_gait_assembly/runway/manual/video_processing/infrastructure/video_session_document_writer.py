"""Persist processing-session manifests, generated summaries, and export artifact references."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import NormalizedRect
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange
from dlc_gait_assembly.shared.infrastructure.json_document_writer import write_json as _write_json
from dlc_gait_assembly.shared.infrastructure.session_directory_allocator import make_session_output_dir


def write_video_processing_session_documents(
    session_dir: str | Path,
    video_paths: list[Path],
    outputs: list[tuple[str, str]],
    failures: list[tuple[str, str]],
    options: ProcessingOptions,
    trim_ranges_by_path: dict[str, tuple[TrimRange, ...]],
    generated_at: datetime | None = None,
) -> dict[str, Path]:
    session_dir = Path(session_dir).expanduser().resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now().astimezone()
    manifest = video_processing_manifest(video_paths, outputs, failures, options, trim_ranges_by_path, generated_at)
    manifest_path = session_dir / "processing_manifest.json"
    summary_path = session_dir / "processing_summary.md"
    _write_json(manifest_path, manifest)
    summary_path.write_text(video_processing_summary_markdown(manifest), encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}


def video_processing_manifest(
    video_paths: list[Path],
    outputs: list[tuple[str, str]],
    failures: list[tuple[str, str]],
    options: ProcessingOptions,
    trim_ranges_by_path: dict[str, tuple[TrimRange, ...]],
    generated_at: datetime,
) -> dict:
    outputs_by_input: dict[str, list[str]] = {}
    for input_path, output_path in outputs:
        key = str(Path(input_path).expanduser().resolve())
        outputs_by_input.setdefault(key, []).append(str(Path(output_path).expanduser().resolve()))
    failure_by_input = {str(Path(input_path).expanduser().resolve()): message for (input_path, message) in failures}
    trims_by_input = {
        str(Path(input_path).expanduser().resolve()): ranges for (input_path, ranges) in trim_ranges_by_path.items()
    }
    files = []
    for path in video_paths:
        input_path = str(Path(path).expanduser().resolve())
        output_paths = outputs_by_input.get(input_path, [])
        files.append(
            {
                "input": input_path,
                "output": output_paths[0] if output_paths else None,
                "outputs": output_paths,
                "status": "failed" if input_path in failure_by_input else "completed",
                "error": failure_by_input.get(input_path),
                "trim_ranges": [trim_to_dict(trim) for trim in trims_by_input.get(input_path, ())],
            }
        )
    return {
        "generated_at": generated_at.isoformat(),
        "format": {"container": "mp4", "video_codec": "H.264", "crf": options.crf, "preset": options.preset},
        "operations": {
            "crop": rect_to_dict(options.effective_crop_regions()[0].rect)
            if options.effective_crop_regions()
            else None,
            "crop_regions": [
                {
                    "name": region.name,
                    "rect": rect_to_dict(region.rect),
                    "flip_horizontal": region.flip_horizontal,
                    "flip_vertical": region.flip_vertical,
                    "flip_horizontal_video_paths": sorted(region.flip_horizontal_video_paths)
                    if region.flip_horizontal_video_paths is not None
                    else None,
                }
                for region in options.effective_crop_regions()
            ],
            "invert_regions": [rect_to_dict(rect) for rect in options.effective_invert_rects()]
            if options.invert_enabled
            else [],
            "enhancements": enhancements_to_dict(options.enhancements),
            "trim": "per-video",
        },
        "counts": {
            "requested": len(video_paths),
            "completed": len(video_paths) - len(failures),
            "outputs": len(outputs),
            "failed": len(failures),
        },
        "files": files,
    }


def video_processing_summary_markdown(manifest: dict) -> str:
    operations = manifest["operations"]
    lines = [
        "# Video Processing Summary",
        "",
        f"Generated: {manifest['generated_at']}",
        "",
        "## Export Format",
        "",
        f"- Container: {manifest['format']['container']}",
        f"- Video codec: {manifest['format']['video_codec']}",
        f"- Quality: CRF {manifest['format']['crf']}, preset {manifest['format']['preset']}",
        "",
        "## Operations",
        "",
        f"- Regions: {format_crop_operation(operations)}",
        f"- Region flips: {format_region_flips(operations)}",
        f"- Enhancements: {format_enhancements(operations['enhancements'])}",
        "- Trim: stored per video below",
        "",
        "## Files",
        "",
    ]
    for file_info in manifest["files"]:
        lines.append(f"### {Path(file_info['input']).name}")
        lines.append("")
        lines.append(f"- Input: `{file_info['input']}`")
        output_paths = file_info.get("outputs") or ([file_info["output"]] if file_info["output"] else [])
        if len(output_paths) == 1:
            lines.append(f"- Output: `{file_info['output']}`")
        elif output_paths:
            lines.append("- Outputs:")
            for output_path in output_paths:
                lines.append(f"  - `{output_path}`")
        lines.append(f"- Status: {file_info['status']}")
        if file_info["error"]:
            lines.append(f"- Error: {file_info['error']}")
        if file_info["trim_ranges"]:
            lines.append("- Trim ranges:")
            for trim in file_info["trim_ranges"]:
                lines.append(f"  - {trim['start_ms']} ms to {trim['end_ms']} ms")
        else:
            lines.append("- Trim ranges: full video")
        lines.append("")
    return "\n".join(lines)


def rect_to_dict(rect: NormalizedRect | None) -> dict | None:
    if rect is None:
        return None
    rect = rect.clamped()
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def trim_to_dict(trim: TrimRange) -> dict:
    return {"start_ms": trim.start_ms, "end_ms": trim.end_ms}


def enhancements_to_dict(settings: EnhancementSettings) -> dict:
    return {
        "enabled": settings.is_enabled(),
        "sharpening": settings.sharpening,
        "cas": settings.cas,
        "brightness": settings.brightness,
        "contrast": settings.contrast,
        "exposure": settings.exposure,
        "black_level": settings.black_level,
        "tone_scale": settings.tone_scale,
        "input_black": settings.input_black,
        "input_white": settings.input_white,
        "output_black": settings.output_black,
        "output_white": settings.output_white,
    }


def format_rect(rect: dict | None) -> str:
    if rect is None:
        return "none"
    return f"x={rect['x']:.4f}, y={rect['y']:.4f}, width={rect['width']:.4f}, height={rect['height']:.4f}"


def format_crop_operation(operations: dict) -> str:
    crop_regions = operations.get("crop_regions") or []
    if not crop_regions:
        return "none"
    if len(crop_regions) == 1:
        return format_rect(crop_regions[0]["rect"])
    return ", ".join(f"{region['name']} ({format_rect(region['rect'])})" for region in crop_regions)


def format_region_flips(operations: dict) -> str:
    crop_regions = operations.get("crop_regions") or []
    horizontal = [region["name"] for region in crop_regions if region.get("flip_horizontal")]
    vertical = [region["name"] for region in crop_regions if region.get("flip_vertical")]
    vertical_overlays = len(operations.get("invert_regions") or [])
    parts = []
    if horizontal:
        parts.append(f"horizontal on {', '.join(horizontal)}")
    if vertical:
        parts.append(f"vertical on {', '.join(vertical)}")
    if vertical_overlays:
        parts.append(f"vertical overlays: {vertical_overlays}")
    return "; ".join(parts) if parts else "none"


def format_enhancements(settings: dict) -> str:
    if not settings["enabled"]:
        return "none"
    changed = [
        f"{key}={value}"
        for (key, value) in settings.items()
        if key != "enabled" and abs(float(value) - float(getattr(EnhancementSettings(), key))) > 0.001
    ]
    return ", ".join(changed) if changed else "none"


class VideoSessionDocumentWriter:
    write = staticmethod(write_video_processing_session_documents)
    allocate = staticmethod(make_session_output_dir)
