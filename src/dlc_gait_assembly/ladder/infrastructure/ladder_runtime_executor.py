"""Select Ladder scientific execution and exchange serialized requests with an installed external runtime."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderEvent, LadderRunResult, LadderSettings
from dlc_gait_assembly.shared.infrastructure.scientific_runtime_adapter import (
    find_alma_python,
    temporary_directory_root,
)


def run_ladder_analysis(
    csv_file: Path, output_folder: Path, settings: LadderSettings, bodyparts: list[str] | None = None
) -> LadderRunResult:
    """Run the ported ALMA detector and write its standard event CSV."""
    external_python = find_alma_python()
    if external_python is not None:
        return run_external(csv_file, output_folder, settings, bodyparts, external_python)
    return run_in_process(csv_file, output_folder, settings, bodyparts)


def run_in_process(
    csv_file: Path, output_folder: Path, settings: LadderSettings, bodyparts: list[str] | None
) -> LadderRunResult:
    from dlc_gait_assembly.ladder.business.ladder_analysis_use_cases import LadderAnalysisUseCases
    from dlc_gait_assembly.ladder.infrastructure.ladder_coordinate_reader import LadderCoordinateReader
    from dlc_gait_assembly.ladder.infrastructure.ladder_event_exporter import LadderEventExporter

    return LadderAnalysisUseCases(LadderCoordinateReader(), LadderEventExporter()).run(
        csv_file, output_folder, settings, bodyparts
    )


def run_external(csv_file, output_folder, settings, bodyparts, python_executable):
    with tempfile.TemporaryDirectory(prefix="alma-ladder-", dir=temporary_directory_root()) as temp_dir:
        request_path = Path(temp_dir) / "request.json"
        result_path = Path(temp_dir) / "result.json"
        request_path.write_text(
            json.dumps(
                {
                    "csv_file": str(Path(csv_file).expanduser().resolve()),
                    "output_folder": str(Path(output_folder).expanduser().resolve()),
                    "settings": asdict(settings),
                    "bodyparts": bodyparts,
                    "result_path": str(result_path),
                }
            ),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["DLC_GAIT_ALMA_PIPELINE_CHILD"] = "1"
        completed = subprocess.run(
            [
                str(python_executable),
                "-m",
                "dlc_gait_assembly.ladder.infrastructure.ladder_scientific_worker_entry",
                "--run-request",
                str(request_path),
            ],
            env=env,
            cwd=temporary_directory_root(),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"ALMA ladder analysis failed.\nPython: {python_executable}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return LadderRunResult(
            input_file=Path(payload["input_file"]),
            output_file=Path(payload["output_file"]),
            events=tuple(LadderEvent(**event) for event in payload["events"]),
        )
