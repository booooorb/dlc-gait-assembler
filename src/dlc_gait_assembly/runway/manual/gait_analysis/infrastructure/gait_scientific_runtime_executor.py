"""Select scientific execution, serialize gait requests, and invoke the configured installed runtime."""

import json
import os
import tempfile
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionProgress
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession
from dlc_gait_assembly.shared.infrastructure.scientific_runtime_adapter import (
    find_alma_python,
    temporary_directory_root,
)


def run_alma_gait_analysis(
    csv_files: list[Path | AlmaViewCsvSet], output_folder: Path, settings: AlmaSettings, progress_callback=None
) -> list[AlmaRunResult]:
    external_python = find_alma_python()
    if external_python is not None:
        return run_alma_gait_analysis_external(csv_files, output_folder, settings, external_python, progress_callback)
    return run_alma_gait_analysis_in_process(csv_files, output_folder, settings, progress_callback)


def run_alma_gait_analysis_in_process(
    csv_files: list[Path | AlmaViewCsvSet], output_folder: Path, settings: AlmaSettings, progress_callback=None
) -> list[AlmaRunResult]:
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import GaitAnalysisUseCases

    return GaitAnalysisUseCases(GaitResultWriter()).run(csv_files, output_folder, settings, progress_callback)


def run_alma_gait_analysis_external(
    csv_files: list[Path | AlmaViewCsvSet],
    output_folder: Path,
    settings: AlmaSettings,
    python_executable: Path,
    progress_callback=None,
) -> list[AlmaRunResult]:
    output_folder = Path(output_folder).expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="alma-pipeline-", dir=temporary_directory_root()) as temp_dir:
        temp_path = Path(temp_dir)
        request_path = temp_path / "request.json"
        result_path = temp_path / "result.json"
        request = {
            "inputs": [alma_input_to_json(item) for item in csv_files],
            "output_folder": str(output_folder),
            "settings": settings_to_json(settings),
            "result_path": str(result_path),
        }
        request_path.write_text(json.dumps(request), encoding="utf-8")
        env = os.environ.copy()
        env["DLC_GAIT_ALMA_PIPELINE_CHILD"] = "1"
        env.setdefault("MPLCONFIGDIR", str(temporary_directory_root() / "matplotlib"))
        if progress_callback is not None:
            progress_callback(1, max(1, len(csv_files)), "Running ALMA-compatible pipeline")
        env.pop("PYTHONPATH", None)
        completed = ExternalProcessSession().run(
            ExternalCommand(
                (
                    str(python_executable),
                    "-m",
                    "dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_worker_entry",
                    "--run-request",
                    str(request_path),
                ),
                environment=env,
            ),
            checkpoint=progress_callback.checkpoint if isinstance(progress_callback, ExecutionProgress) else None,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"ALMA-compatible pipeline failed.\nPython: {python_executable}\nprocess output:\n{completed.output}"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        results = [
            AlmaRunResult(
                input_file=Path(item["input_file"]),
                output_files=tuple(Path(path) for path in item["output_files"]),
                messages=tuple(item.get("messages", ())),
            )
            for item in payload["results"]
        ]
        if progress_callback is not None:
            for index, result in enumerate(results, start=1):
                progress_callback(index, len(results), f"Processed {result.input_file.name}")
        return results


def alma_input_to_json(item: Path | AlmaViewCsvSet) -> dict:
    if isinstance(item, AlmaViewCsvSet):
        payload = {
            "kind": "multiview",
            "name": item.name,
            "left_csv": str(Path(item.left_csv).expanduser().resolve()),
            "right_csv": str(Path(item.right_csv).expanduser().resolve()),
            "bottom_csv": str(Path(item.bottom_csv).expanduser().resolve()),
        }
        if item.metadata is not None:
            payload["metadata"] = dict(item.metadata.__dict__)
        return payload
    return {"kind": "single", "csv_file": str(Path(item).expanduser().resolve())}


def alma_input_from_json(payload) -> Path | AlmaViewCsvSet:
    if isinstance(payload, str):
        return Path(payload)
    if payload.get("kind") == "multiview":
        metadata = payload.get("metadata")
        return AlmaViewCsvSet(
            name=str(payload["name"]),
            left_csv=Path(payload["left_csv"]),
            right_csv=Path(payload["right_csv"]),
            bottom_csv=Path(payload["bottom_csv"]),
            metadata=StrokeStudyMetadata(**metadata) if isinstance(metadata, dict) else None,
        )
    return Path(payload["csv_file"])


def settings_to_json(settings: AlmaSettings) -> dict:
    payload = dict(settings.__dict__)
    if settings.calibration_map_path is not None:
        payload["calibration_map_path"] = str(settings.calibration_map_path)
    return payload


def settings_from_json(payload: dict) -> AlmaSettings:
    if payload.get("calibration_map_path"):
        payload = {**payload, "calibration_map_path": Path(payload["calibration_map_path"])}
    return AlmaSettings(**payload)
