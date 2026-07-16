from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yaml


DLC_MODEL_FOLDER_NAMES = ("dlc-models-pytorch", "dlc-models")
DLC_TRAINING_DATASET_FOLDER_NAME = "training-datasets"
_DLC_PROGRESS_SCALE = 1000
_TQDM_PERCENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3})%\|")


@dataclass(frozen=True)
class DlcAnalysisJob:
    region: str
    model_path: Path
    video_paths: tuple[Path, ...]


@dataclass(frozen=True)
class DlcAnalysisResult:
    region: str
    video_paths: tuple[Path, ...]
    csv_paths: tuple[Path, ...]
    h5_paths: tuple[Path, ...]
    labeled_video_paths: tuple[Path, ...]


class _DlcProgressParser:
    """Translate DLC/tqdm process output into monotonic pipeline progress."""

    def __init__(
        self,
        total_videos: int,
        progress_callback: Callable[[int, int, str], None] | None,
        phase: str = "analysis",
    ):
        if phase not in {"analysis", "labels"}:
            raise ValueError(f"Unsupported DeepLabCut progress phase: {phase}")
        self.total_videos = max(1, total_videos)
        self.progress_callback = progress_callback
        self.expected_phase = phase
        self.phase = phase
        self.phase_index = 0
        self.video_name = ""
        self.last_value = -1
        self.analysis_step_offset = 0.0
        self.analysis_step_weight = 1.0
        self.detector_started = False

    def feed(self, output_line: str) -> None:
        line = output_line.strip()
        analysis_marker = "Starting to analyze "
        labels_marker = "Starting to process video:"
        if self.expected_phase == "analysis" and analysis_marker in line:
            video_path = line.split(analysis_marker, 1)[1].strip()
            self._begin_video("analysis", video_path)
            return
        if self.expected_phase == "labels" and labels_marker in line:
            video_path = line.split(labels_marker, 1)[1].strip()
            self._begin_video("labels", video_path)
            return
        if self.phase == "analysis" and "Running detector with batch size" in line:
            self.detector_started = True
            self.analysis_step_offset = 0.0
            self.analysis_step_weight = 0.3
            return
        if self.phase == "analysis" and "Running pose prediction with batch size" in line:
            self.analysis_step_offset = 0.3 if self.detector_started else 0.0
            self.analysis_step_weight = 0.7 if self.detector_started else 1.0
            return

        match = _TQDM_PERCENT_PATTERN.search(line)
        if match is not None and self.phase:
            video_percent = min(100, int(match.group(1)))
            if self.phase == "analysis":
                video_percent = round(
                    100
                    * (
                        self.analysis_step_offset
                        + self.analysis_step_weight * video_percent / 100.0
                    )
                )
            self._emit(video_percent)

    def finish(self) -> None:
        self.phase = self.expected_phase
        self.phase_index = self.total_videos
        self._emit(100, force=True)

    def _begin_video(self, phase: str, video_path: str) -> None:
        if phase != self.phase:
            self.phase = phase
            self.phase_index = 0
        self.phase_index = min(self.total_videos, self.phase_index + 1)
        self.video_name = Path(video_path).name
        self.analysis_step_offset = 0.0
        self.analysis_step_weight = 1.0
        self.detector_started = False
        self._emit(0, force=True)

    def _emit(self, video_percent: int, force: bool = False) -> None:
        if self.progress_callback is None:
            return
        completed_fraction = (
            (self.phase_index - 1 + video_percent / 100.0) / self.total_videos
        )
        overall_fraction = completed_fraction
        action = "Creating labeled" if self.phase == "labels" else "Analyzing"
        value = round(max(0.0, min(1.0, overall_fraction)) * _DLC_PROGRESS_SCALE)
        if value < self.last_value:
            return
        if not force and value == self.last_value:
            return
        self.last_value = value
        message = f"{action} video {self.phase_index} of {self.total_videos}"
        if self.video_name:
            message += f": {self.video_name}"
        self.progress_callback(value, _DLC_PROGRESS_SCALE, message)


def resolve_deeplabcut_config(model_path: str | Path) -> Path:
    """Resolve a saved model file/folder to one unambiguous DLC config.yaml."""
    candidate = Path(model_path).expanduser().resolve()
    if candidate.is_file() and candidate.name.casefold() == "config.yaml":
        return candidate

    if candidate.is_file():
        for parent in candidate.parents:
            config = parent / "config.yaml"
            if config.is_file():
                return config

    search_root = candidate if candidate.is_dir() else candidate.parent
    direct = search_root / "config.yaml"
    if direct.is_file():
        return direct

    configs = sorted(search_root.rglob("config.yaml")) if search_root.exists() else []
    if len(configs) == 1:
        return configs[0]
    if not configs:
        raise FileNotFoundError(
            f'No DeepLabCut config.yaml was found in "{candidate.name}".'
        )
    raise ValueError(
        f'"{candidate.name}" contains multiple DeepLabCut projects. Select one project folder.'
    )


def validate_deeplabcut_project(model_path: str | Path) -> Path:
    """Return the project config after checking that trained inference files exist."""
    config_path = resolve_deeplabcut_config(model_path)
    project_root = config_path.parent
    model_folders = [
        project_root / name
        for name in DLC_MODEL_FOLDER_NAMES
        if (project_root / name).is_dir()
    ]
    has_pytorch_model = any(
        any(folder.rglob("pytorch_config.yaml"))
        and (any(folder.rglob("*.pt")) or any(folder.rglob("*.pth")))
        for folder in model_folders
    )
    has_tensorflow_model = any(
        any(folder.rglob("pose_cfg.yaml"))
        and (any(folder.rglob("*.index")) or any(folder.rglob("*.h5")))
        for folder in model_folders
    )
    if not has_pytorch_model and not has_tensorflow_model:
        raise FileNotFoundError(
            "The selected DeepLabCut project has no complete trained model. Select its "
            "config.yaml or project folder with the trained model directory intact."
        )
    training_dataset_folder = project_root / DLC_TRAINING_DATASET_FOLDER_NAME
    has_shuffle_metadata = _has_deeplabcut_shuffle_metadata(
        config_path,
        training_dataset_folder,
        allow_pytorch=has_pytorch_model,
        allow_tensorflow=has_tensorflow_model,
    )
    if not has_shuffle_metadata:
        raise ValueError(
            "The selected DeepLabCut project metadata does not define shuffle 1 for its first "
            "TrainingFraction with the trained model engine. Select the original complete "
            "project, including its training-datasets directory."
        )
    return config_path


def _has_deeplabcut_shuffle_metadata(
    config_path: Path,
    training_dataset_folder: Path,
    *,
    allow_pytorch: bool,
    allow_tensorflow: bool,
) -> bool:
    if not training_dataset_folder.is_dir():
        return False
    try:
        project_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, TypeError, yaml.YAMLError):
        return False
    task = str(project_config.get("Task", "")).strip()
    date = str(project_config.get("date", "")).strip()
    try:
        iteration = int(project_config.get("iteration", 0))
    except (TypeError, ValueError):
        return False
    if not task or not date:
        return False
    training_fractions = project_config.get("TrainingFraction")
    if not isinstance(training_fractions, list) or not training_fractions:
        return False
    try:
        expected_fraction = float(training_fractions[0])
    except (TypeError, ValueError):
        return False

    dataset_folder = (
        training_dataset_folder
        / f"iteration-{iteration}"
        / f"UnaugmentedDataSet_{task}{date}"
    )
    metadata_path = dataset_folder / "metadata.yaml"
    if metadata_path.is_file():
        try:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        except (OSError, TypeError, yaml.YAMLError):
            return False
        shuffles = metadata.get("shuffles")
        if not isinstance(shuffles, dict):
            return False
        for shuffle in shuffles.values():
            if not isinstance(shuffle, dict):
                continue
            try:
                fraction_matches = abs(
                    float(shuffle.get("train_fraction")) - expected_fraction
                ) <= 1e-9
                index_matches = int(shuffle.get("index")) == 1
            except (TypeError, ValueError):
                continue
            engine = str(shuffle.get("engine", "")).strip().casefold()
            engine_matches = (
                allow_pytorch and engine in {"pytorch", "torch"}
            ) or (
                allow_tensorflow and engine in {"tensorflow", "tf"}
            )
            if fraction_matches and index_matches and engine_matches:
                return True
        return False
    return allow_tensorflow and any(dataset_folder.glob("Documentation_data-*.pickle"))


def run_deeplabcut_analysis(
    jobs: list[DlcAnalysisJob],
    output_folder: str | Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[DlcAnalysisResult]:
    """Run DLC pose analysis without creating labeled review videos."""
    if not jobs:
        return []

    destination = Path(output_folder).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    request_jobs = []
    total = len(jobs)
    total_videos = sum(len(job.video_paths) for job in jobs)
    for index, job in enumerate(jobs, start=1):
        config_path = validate_deeplabcut_project(job.model_path)
        region_name = _safe_name(job.region)
        analysis_folder = destination / "analyzed_videos" / region_name
        analysis_folder.mkdir(parents=True, exist_ok=True)
        request_jobs.append(
            {
                "region": job.region,
                "config_path": str(config_path),
                "video_paths": [str(Path(path).expanduser().resolve()) for path in job.video_paths],
                "analysis_folder": str(analysis_folder),
            }
        )
        if progress_callback is not None:
            progress_callback(
                0,
                _DLC_PROGRESS_SCALE,
                f"Validating DeepLabCut model for {job.region}",
            )

    payload = _run_bridge_request(
        {"operation": "analyze", "jobs": request_jobs},
        total_videos,
        "analysis",
        "Initializing DeepLabCut model",
        "DeepLabCut analysis",
        progress_callback,
    )
    results = [_result_from_json(item) for item in payload.get("results", [])]
    if len(results) != len(jobs):
        raise RuntimeError("DeepLabCut returned an incomplete set of region results.")
    if progress_callback is not None:
        progress_callback(total, total, "DeepLabCut analysis complete")
    return results


def run_deeplabcut_labeled_video_creation(
    jobs: list[DlcAnalysisJob],
    analysis_results: list[DlcAnalysisResult],
    output_folder: str | Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[DlcAnalysisResult]:
    """Create review videos from the current, potentially corrected, coordinates."""
    if not jobs:
        return []
    results_by_region = {result.region: result for result in analysis_results}
    if set(results_by_region) != {job.region for job in jobs}:
        raise ValueError("DeepLabCut analysis results do not match the configured regions.")

    destination = Path(output_folder).expanduser().resolve()
    request_jobs = []
    total_videos = sum(len(job.video_paths) for job in jobs)
    for job in jobs:
        result = results_by_region[job.region]
        coordinate_paths = (*result.csv_paths, *result.h5_paths)
        coordinate_folders = {path.parent.resolve() for path in coordinate_paths}
        if len(coordinate_folders) != 1:
            raise ValueError(
                f'Analyzed files for region "{job.region}" are not in one output folder.'
            )
        config_path = validate_deeplabcut_project(job.model_path)
        labeled_videos_folder = destination / "labeled_videos" / _safe_name(job.region)
        labeled_videos_folder.mkdir(parents=True, exist_ok=True)
        request_jobs.append(
            {
                "region": job.region,
                "config_path": str(config_path),
                "video_paths": [str(path) for path in job.video_paths],
                "analysis_folder": str(next(iter(coordinate_folders))),
                "labeled_videos_folder": str(labeled_videos_folder),
                "csv_paths": [str(path) for path in result.csv_paths],
                "h5_paths": [str(path) for path in result.h5_paths],
            }
        )

    payload = _run_bridge_request(
        {"operation": "create_labeled_videos", "jobs": request_jobs},
        total_videos,
        "labels",
        "Preparing corrected coordinates for labeled videos",
        "DeepLabCut labeled-video creation",
        progress_callback,
    )
    results = [_result_from_json(item) for item in payload.get("results", [])]
    if len(results) != len(jobs):
        raise RuntimeError("DeepLabCut returned an incomplete set of labeled videos.")
    if progress_callback is not None:
        progress_callback(1, 1, "Labeled videos complete")
    return results


def _run_bridge_request(
    request: dict,
    total_videos: int,
    progress_phase: str,
    initial_message: str,
    failure_label: str,
    progress_callback: Callable[[int, int, str], None] | None,
) -> dict:
    from dlc_gait_assembly.services.imports import deeplabcut_analysis_command

    with tempfile.TemporaryDirectory(prefix="dlc-automated-") as temp_dir:
        temp_path = Path(temp_dir)
        request_path = temp_path / "request.json"
        result_path = temp_path / "result.json"
        request["result_path"] = str(result_path)
        request_path.write_text(json.dumps(request), encoding="utf-8")
        if progress_callback is not None:
            progress_callback(0, _DLC_PROGRESS_SCALE, initial_message)
        command = deeplabcut_analysis_command(Path(__file__), request_path)
        progress_parser = _DlcProgressParser(
            total_videos,
            progress_callback,
            phase=progress_phase,
        )
        process = subprocess.Popen(
            command,
            shell=True,
            executable=None if os.name == "nt" else "/bin/bash",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        output_lines: list[str] = []
        if process.stdout is not None:
            for output_line in process.stdout:
                output_lines.append(output_line)
                progress_parser.feed(output_line)
        return_code = process.wait()
        output = "".join(output_lines)
        if return_code != 0:
            raise RuntimeError(f"{failure_label} failed.\nprocess output:\n{output}")
        progress_parser.finish()
        if not result_path.exists():
            raise RuntimeError(
                f"{failure_label} finished without returning an output manifest."
            )
        return json.loads(result_path.read_text(encoding="utf-8"))


def _run_request(request_path: Path) -> None:
    # Running this file directly would otherwise make it shadow the installed
    # ``deeplabcut`` package because both have the same module filename.
    bridge_folder = Path(__file__).resolve().parent
    sys.path = [
        entry
        for entry in sys.path
        if Path(entry or os.curdir).resolve() != bridge_folder
    ]
    import deeplabcut

    request = json.loads(request_path.read_text(encoding="utf-8"))
    operation = request.get("operation")
    if operation == "analyze":
        results = _run_analysis_jobs(request["jobs"], deeplabcut)
    elif operation == "create_labeled_videos":
        results = _run_labeled_video_jobs(request["jobs"], deeplabcut)
    else:
        raise ValueError(f"Unsupported DeepLabCut bridge operation: {operation}")
    Path(request["result_path"]).write_text(
        json.dumps({"results": results}), encoding="utf-8"
    )


def _run_analysis_jobs(jobs: list[dict], deeplabcut) -> list[dict]:
    results = []
    for job in jobs:
        config_path = Path(job["config_path"])
        video_paths = [Path(path) for path in job["video_paths"]]
        analysis_folder = Path(job["analysis_folder"])
        analysis_folder.mkdir(parents=True, exist_ok=True)
        before = {path.resolve() for path in analysis_folder.iterdir() if path.is_file()}
        deeplabcut.analyze_videos(
            str(config_path),
            [str(path) for path in video_paths],
            destfolder=str(analysis_folder),
            save_as_csv=True,
        )
        produced = sorted(
            path.resolve()
            for path in analysis_folder.iterdir()
            if path.is_file() and path.resolve() not in before
        )
        csv_paths = [path for path in produced if path.suffix.casefold() == ".csv"]
        h5_paths = [
            path for path in produced if path.suffix.casefold() in {".h5", ".hdf5"}
        ]
        if len(csv_paths) < len(video_paths) or len(h5_paths) < len(video_paths):
            raise RuntimeError(
                f'DeepLabCut did not create CSV and H5 coordinates for region "{job["region"]}".'
            )
        results.append(
            {
                "region": job["region"],
                "video_paths": [str(path) for path in video_paths],
                "csv_paths": [str(path) for path in csv_paths],
                "h5_paths": [str(path) for path in h5_paths],
                "labeled_video_paths": [],
            }
        )
    return results


def _run_labeled_video_jobs(jobs: list[dict], deeplabcut) -> list[dict]:
    results = []
    for job in jobs:
        config_path = Path(job["config_path"])
        video_paths = [Path(path) for path in job["video_paths"]]
        analysis_folder = Path(job["analysis_folder"])
        labeled_videos_folder = Path(job["labeled_videos_folder"])
        analysis_folder.mkdir(parents=True, exist_ok=True)
        labeled_videos_folder.mkdir(parents=True, exist_ok=True)
        before = {path.resolve() for path in analysis_folder.iterdir() if path.is_file()}
        deeplabcut.create_labeled_video(
            str(config_path),
            [str(path) for path in video_paths],
            destfolder=str(analysis_folder),
        )
        produced = sorted(
            path.resolve()
            for path in analysis_folder.iterdir()
            if path.is_file() and path.resolve() not in before
        )
        csv_paths = [Path(path).resolve() for path in job["csv_paths"]]
        h5_paths = [Path(path).resolve() for path in job["h5_paths"]]
        labeled_paths = [
            path
            for path in produced
            if path.suffix.casefold() in {".mp4", ".avi", ".mov", ".mkv"}
            and "label" in path.stem.casefold()
        ]
        organized_labeled_paths = []
        for labeled_path in labeled_paths:
            destination = labeled_videos_folder / labeled_path.name
            shutil.move(str(labeled_path), str(destination))
            organized_labeled_paths.append(destination.resolve())
        labeled_paths = organized_labeled_paths
        if len(labeled_paths) < len(video_paths):
            raise RuntimeError(
                f'DeepLabCut did not create labeled review videos for region "{job["region"]}".'
            )
        results.append(
            {
                "region": job["region"],
                "video_paths": [str(path) for path in video_paths],
                "csv_paths": [str(path) for path in csv_paths],
                "h5_paths": [str(path) for path in h5_paths],
                "labeled_video_paths": [str(path) for path in labeled_paths],
            }
        )
    return results


def _result_from_json(item: dict) -> DlcAnalysisResult:
    return DlcAnalysisResult(
        region=str(item["region"]),
        video_paths=tuple(Path(path) for path in item.get("video_paths", [])),
        csv_paths=tuple(Path(path) for path in item.get("csv_paths", [])),
        h5_paths=tuple(Path(path) for path in item.get("h5_paths", [])),
        labeled_video_paths=tuple(Path(path) for path in item.get("labeled_video_paths", [])),
    )


def _safe_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    return safe.strip("_") or "region"


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-request", type=Path)
    args = parser.parse_args()
    if args.run_request is None:
        parser.error("--run-request is required")
    _run_request(args.run_request)


if __name__ == "__main__":
    _main()
