"""Save conversion-map JSON and the accompanying calibration report in a collision-safe session."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.runway.manual.calibration.business.calibration_conversion_map import build_conversion_factor_map
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick
from dlc_gait_assembly.runway.manual.calibration.infrastructure.calibration_report_formatter import (
    calibration_report_markdown as _calibration_report_markdown,
)
from dlc_gait_assembly.runway.manual.calibration.infrastructure.calibration_report_formatter import (
    stick_to_dict as _stick_to_dict,
)
from dlc_gait_assembly.shared.infrastructure.json_document_writer import write_json as _write_json
from dlc_gait_assembly.shared.infrastructure.session_directory_allocator import make_session_output_dir


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
    report_path.write_text(_calibration_report_markdown(report, conversion_map, sticks, generated_at), encoding="utf-8")
    return {"map": map_path, "report": report_path}


class CalibrationExportWriter:
    write = staticmethod(write_calibration_conversion_export)
    allocate_session = staticmethod(make_session_output_dir)
