"""Output contract for conversion maps and assessment reports."""

from pathlib import Path
from typing import Protocol

from dlc_gait_assembly.runway.manual.calibration.business.calibration_assessment_contracts import CalibrationReport
from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick


class CalibrationExportPort(Protocol):
    def __call__(
        self, output_dir: Path, sticks: list[CalibrationStick], report: CalibrationReport
    ) -> dict[str, Path]: ...
