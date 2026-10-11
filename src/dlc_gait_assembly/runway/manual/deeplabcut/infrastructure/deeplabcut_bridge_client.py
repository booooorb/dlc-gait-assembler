"""Serialize jobs and read results from the separate DeepLabCut environment."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import (
    DlcAnalysisResult,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_progress_parser import (
    DLC_PROGRESS_SCALE as _DLC_PROGRESS_SCALE,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_progress_parser import (
    DlcProgressParser as _DlcProgressParser,
)
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionProgress


def run_bridge_request(
    request: dict,
    total_videos: int,
    progress_phase: str,
    initial_message: str,
    failure_label: str,
    progress_callback: Callable[[int, int, str], None] | None,
) -> dict:
    from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
        deeplabcut_analysis_command,
    )

    with tempfile.TemporaryDirectory(prefix="dlc-automated-") as temp_dir:
        temp_path = Path(temp_dir)
        request_path = temp_path / "request.json"
        result_path = temp_path / "result.json"
        request["result_path"] = str(result_path)
        request_path.write_text(json.dumps(request), encoding="utf-8")
        if progress_callback is not None:
            progress_callback(0, _DLC_PROGRESS_SCALE, initial_message)
        command = deeplabcut_analysis_command(Path(__file__).with_name("deeplabcut_bridge_entry.py"), request_path)
        progress_parser = _DlcProgressParser(total_videos, progress_callback, phase=progress_phase)
        from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
        from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession

        arguments = ("cmd.exe", "/d", "/s", "/c", command) if os.name == "nt" else ("/bin/bash", "-lc", command)
        completed = ExternalProcessSession().run(
            ExternalCommand(arguments),
            progress_parser.feed,
            checkpoint=progress_callback.checkpoint if isinstance(progress_callback, ExecutionProgress) else None,
        )
        return_code, output = completed.returncode, completed.output
        if return_code != 0:
            raise RuntimeError(f"{failure_label} failed.\nprocess output:\n{output}")
        progress_parser.finish()
        if not result_path.exists():
            raise RuntimeError(f"{failure_label} finished without returning an output manifest.")
        return json.loads(result_path.read_text(encoding="utf-8"))


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
