"""Serialize jobs and read results from the separate DeepLabCut environment."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import (
    DlcAnalysisResult,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
    deeplabcut_analysis_arguments,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_progress_parser import (
    DLC_PROGRESS_SCALE as _DLC_PROGRESS_SCALE,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_progress_parser import (
    DlcProgressParser as _DlcProgressParser,
)
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionProgress
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession


def run_bridge_request(
    request: dict,
    total_videos: int,
    progress_phase: str,
    initial_message: str,
    failure_label: str,
    progress_callback: Callable[[int, int, str], None] | None,
    *,
    script_name: str = "deeplabcut_bridge_entry.py",
) -> dict:
    with tempfile.TemporaryDirectory(prefix="dlc-automated-") as temp_dir:
        temp_path = Path(temp_dir)
        request_path = temp_path / "request.json"
        result_path = temp_path / "result.json"
        request["result_path"] = str(result_path)
        request_path.write_text(json.dumps(request), encoding="utf-8")
        if progress_callback is not None:
            progress_callback(0, _DLC_PROGRESS_SCALE, initial_message)
        arguments = deeplabcut_analysis_arguments(Path(__file__).with_name(script_name), request_path)
        progress_parser = _DlcProgressParser(total_videos, progress_callback, phase=progress_phase)
        completed = ExternalProcessSession().run(
            ExternalCommand(arguments),
            progress_parser.feed,
            checkpoint=progress_callback.checkpoint if isinstance(progress_callback, ExecutionProgress) else None,
        )
        if completed.returncode != 0 or not result_path.is_file():
            reason = (
                f"failed with exit code {completed.returncode}"
                if completed.returncode != 0
                else "exited with code 0 without returning an output manifest"
            )
            output = completed.output.strip() or "(no output received)"
            raise RuntimeError(f"{failure_label} {reason}.\nProcess output:\n{output}")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        progress_parser.finish()
        return result


def result_from_json(item: dict) -> DlcAnalysisResult:
    return DlcAnalysisResult(
        region=str(item["region"]),
        video_paths=tuple(Path(path) for path in item.get("video_paths", [])),
        csv_paths=tuple(Path(path) for path in item.get("csv_paths", [])),
        h5_paths=tuple(Path(path) for path in item.get("h5_paths", [])),
        labeled_video_paths=tuple(Path(path) for path in item.get("labeled_video_paths", [])),
    )


class DeepLabCutBridgeClient:
    """Serialize bridge messages and interpret the child environment's artifact response."""

    request = staticmethod(run_bridge_request)
    decode_result = staticmethod(result_from_json)
