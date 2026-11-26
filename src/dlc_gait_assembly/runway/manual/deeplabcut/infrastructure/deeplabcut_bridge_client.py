"""Serialize jobs and read results from the separate DeepLabCut environment."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

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
from dlc_gait_assembly.shared.infrastructure.windows_filesystem_paths import windows_filesystem_path


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
        payload = {**request, "result_path": str(result_path)}
        if request.get("operation") in ("analyze", "create_labeled_videos") and "jobs" in request:
            # DeepLabCut appends the video stem and model scorer inside the child process.
            # Even a short destination directory can produce a filename beyond MAX_PATH.
            payload["jobs"] = [dict(job) for job in request["jobs"]]
            for job in payload["jobs"]:
                for key in ("analysis_folder", "labeled_videos_folder"):
                    if key in job:
                        job[key] = str(windows_filesystem_path(Path(job[key])))
        request_path.write_text(json.dumps(payload), encoding="utf-8")
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


def _artifact_path(value: str) -> Path:
    path = Path(value)
    prefix = "\\\\?\\"
    unc_prefix = prefix + "UNC\\"
    if isinstance(path, PureWindowsPath) and value.startswith(prefix):
        if value.startswith(unc_prefix):
            ordinary = "\\\\" + value.removeprefix(unc_prefix)
        else:
            ordinary = value.removeprefix(prefix)
        # MAX_PATH counts UTF-16 code units and the terminating null.
        if len(ordinary.encode("utf-16-le", errors="surrogatepass")) < 2 * 260:
            return Path(ordinary)
    return path


def result_from_json(item: dict) -> DlcAnalysisResult:
    return DlcAnalysisResult(
        region=str(item["region"]),
        video_paths=tuple(Path(path) for path in item.get("video_paths", [])),
        csv_paths=tuple(map(_artifact_path, item.get("csv_paths", []))),
        h5_paths=tuple(map(_artifact_path, item.get("h5_paths", []))),
        labeled_video_paths=tuple(map(_artifact_path, item.get("labeled_video_paths", []))),
    )


class DeepLabCutBridgeClient:
    """Serialize bridge messages and interpret the child environment's artifact response."""

    request = staticmethod(run_bridge_request)
    decode_result = staticmethod(result_from_json)
