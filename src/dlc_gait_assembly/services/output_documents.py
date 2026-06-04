from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from dlc_gait_assembly.domain.calibration import CalibrationReport, CalibrationStick, build_conversion_factor_map
from dlc_gait_assembly.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.domain.regions import NormalizedRect
from dlc_gait_assembly.domain.trimming import TrimRange
from dlc_gait_assembly.services.ffmpeg import ProcessingOptions


def write_calibration_conversion_export(
    output_dir: str | Path,
    sticks: list[CalibrationStick],
    report: CalibrationReport,
    generated_at: datetime | None = None,
) -> dict[str, Path]:
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now().astimezone()
    conversion_map = build_conversion_factor_map(report)

    map_path = output_dir / "conversion_factor_map.json"
    report_path = output_dir / "calibration_report.md"

    _write_json(
        map_path,
        {
            "generated_at": generated_at.isoformat(),
            "conversion_factor_map": conversion_map,
            "sticks": [_stick_to_dict(stick) for stick in sticks],
        },
    )
    report_path.write_text(
        _calibration_report_markdown(report, conversion_map, sticks, generated_at),
        encoding="utf-8",
    )

    return {"map": map_path, "report": report_path}


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

    manifest = _video_processing_manifest(
        video_paths,
        outputs,
        failures,
        options,
        trim_ranges_by_path,
        generated_at,
    )
    manifest_path = session_dir / "processing_manifest.json"
    summary_path = session_dir / "processing_summary.md"

    _write_json(manifest_path, manifest)
    summary_path.write_text(_video_processing_summary_markdown(manifest), encoding="utf-8")
    return {"manifest": manifest_path, "summary": summary_path}


def _video_processing_manifest(
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
    failure_by_input = {str(Path(input_path).expanduser().resolve()): message for input_path, message in failures}
    trims_by_input = {
        str(Path(input_path).expanduser().resolve()): ranges for input_path, ranges in trim_ranges_by_path.items()
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
                "trim_ranges": [_trim_to_dict(trim) for trim in trims_by_input.get(input_path, ())],
            }
        )

    return {
        "generated_at": generated_at.isoformat(),
        "format": {
            "container": "mp4",
            "video_codec": "H.264",
            "crf": options.crf,
            "preset": options.preset,
        },
        "operations": {
            "crop": _rect_to_dict(options.effective_crop_regions()[0].rect) if options.effective_crop_regions() else None,
            "crop_regions": [
                {"name": region.name, "rect": _rect_to_dict(region.rect)}
                for region in options.effective_crop_regions()
            ],
            "invert_regions": [_rect_to_dict(rect) for rect in options.effective_invert_rects()]
            if options.invert_enabled
            else [],
            "enhancements": _enhancements_to_dict(options.enhancements),
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


def _video_processing_summary_markdown(manifest: dict) -> str:
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
        f"- Crop: {_format_crop_operation(operations)}",
        f"- Upside-down regions: {len(operations['invert_regions'])}",
        f"- Enhancements: {_format_enhancements(operations['enhancements'])}",
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


def _calibration_report_markdown(
    report: CalibrationReport,
    conversion_map: dict,
    sticks: list[CalibrationStick],
    generated_at: datetime,
) -> str:
    lines = [
        "# Calibration Conversion Factor Map",
        "",
        f"Generated: {generated_at.isoformat()}",
        "",
        "## How To Apply",
        "",
        "Use `conversion_factor_map.json` to convert pixel coordinates into centimeters.",
        "For a coordinate in a view, use the matching view entry:",
        "",
        "```text",
        "x_cm = x_px * recommended_x_centimeters_per_pixel",
        "y_cm = y_px * recommended_y_centimeters_per_pixel",
        "```",
        "",
        f"Recommended scope: `{conversion_map['recommended_scope']}`",
        f"Recommendation: {report.recommendation}",
        "",
        "## Overall",
        "",
        f"- Overall cm/px: {_format_optional(report.overall_mean)}",
        f"- Overall px/cm: {_format_optional(_safe_inverse(report.overall_mean))}",
        f"- Overall status: {_status(report.overall_passed)}",
        f"- Tau: {report.tau_percent:.2f}%",
        "",
        "## View Factors",
        "",
        "| View | X cm/px | Y cm/px | Mean cm/px | Axis check | View check |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]

    for view in report.views:
        lines.append(
            "| "
            f"{view.view_index} | "
            f"{_format_optional(view.x_mean)} | "
            f"{_format_optional(view.y_mean)} | "
            f"{_format_optional(view.view_mean)} | "
            f"{_status(view.axis_passed)} | "
            f"{_status(view.view_passed)} |"
        )

    lines.extend(["", "## Calibration Sticks", ""])
    for stick in sticks:
        lines.append(
            f"- {stick.name}: {len(stick.centimeter_pixel_lengths())} measured 1 cm segment(s), "
            f"markers at {', '.join(f'{position:.4f}' for position in stick.ordered_marker_positions())}"
        )

    return "\n".join(lines) + "\n"


def _stick_to_dict(stick: CalibrationStick) -> dict:
    return {
        "name": stick.name,
        "axis": stick.axis,
        "view_index": stick.view_index,
        "start": {"x": stick.start.x, "y": stick.start.y},
        "end": {"x": stick.end.x, "y": stick.end.y},
        "marker_positions": list(stick.marker_positions),
        "centimeter_pixel_lengths": list(stick.centimeter_pixel_lengths()),
    }


def _rect_to_dict(rect: NormalizedRect | None) -> dict | None:
    if rect is None:
        return None
    rect = rect.clamped()
    return {"x": rect.x, "y": rect.y, "width": rect.width, "height": rect.height}


def _trim_to_dict(trim: TrimRange) -> dict:
    return {"start_ms": trim.start_ms, "end_ms": trim.end_ms}


def _enhancements_to_dict(settings: EnhancementSettings) -> dict:
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


def _format_rect(rect: dict | None) -> str:
    if rect is None:
        return "none"
    return f"x={rect['x']:.4f}, y={rect['y']:.4f}, width={rect['width']:.4f}, height={rect['height']:.4f}"


def _format_crop_operation(operations: dict) -> str:
    crop_regions = operations.get("crop_regions") or []
    if not crop_regions:
        return "none"
    if len(crop_regions) == 1:
        return _format_rect(crop_regions[0]["rect"])
    return ", ".join(f"{region['name']} ({_format_rect(region['rect'])})" for region in crop_regions)


def _format_enhancements(settings: dict) -> str:
    if not settings["enabled"]:
        return "none"
    changed = [
        f"{key}={value}"
        for key, value in settings.items()
        if key != "enabled" and abs(float(value) - float(getattr(EnhancementSettings(), key))) > 0.001
    ]
    return ", ".join(changed) if changed else "none"


def _format_optional(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.8f}"


def _status(value: bool | None) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return "NEEDS DATA"


def _safe_inverse(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return 1.0 / value


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
