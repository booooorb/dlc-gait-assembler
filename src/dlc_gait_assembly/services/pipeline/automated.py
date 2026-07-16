from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from dlc_gait_assembly.services.analysis_manifests import (
    alma_settings_from_manifest,
    knee_settings_from_manifest,
    video_settings_from_manifest,
)
from dlc_gait_assembly.services.automated_profiles import AutomatedPipelineProfile
from dlc_gait_assembly.services.knee_correction import CoordinateFilePair, correct_knee_pair
from dlc_gait_assembly.services.pipeline.alma import (
    AlmaRunResult,
    AlmaViewCsvSet,
    default_alma_root,
    run_alma_gait_analysis,
)
from dlc_gait_assembly.services.pipeline.deeplabcut import (
    DlcAnalysisJob,
    DlcAnalysisResult,
    run_deeplabcut_analysis,
)
from dlc_gait_assembly.services.video_processing import process_video_outputs


ProgressCallback = Callable[[int, int, str], None]
VIEW_ALIASES = {
    "left": {"left", "lh", "leftside", "leftview"},
    "right": {"right", "rh", "rightside", "rightview"},
    "bottom": {"bottom", "down", "downward", "ventral", "below", "bottomview"},
}


@dataclass(frozen=True)
class AutomatedPipelineResult:
    output_folder: Path
    output_manifest: Path
    processed_videos: tuple[Path, ...]
    coordinate_csvs: tuple[Path, ...]
    labeled_videos: tuple[Path, ...]
    stickplots: tuple[Path, ...]
    analysis_outputs: tuple[Path, ...]


class AutomatedPipelineRun:
    """Stateful five-stage run whose outputs feed directly into the next stage."""

    def __init__(
        self,
        profile: AutomatedPipelineProfile,
        video_paths: list[str | Path],
        project_root: str | Path,
        output_root: str | Path | None = None,
        enable_knee_correction: bool = True,
        enable_gait_analysis: bool = True,
    ):
        self.profile = profile
        self.enable_knee_correction = bool(enable_knee_correction)
        self.enable_gait_analysis = bool(enable_gait_analysis)
        self.video_paths = tuple(Path(path).expanduser().resolve() for path in video_paths)
        if not self.video_paths:
            raise ValueError("Add at least one source video before running the pipeline.")
        missing = [path for path in self.video_paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Source video no longer exists: {missing[0]}")
        gait_requested = self.enable_gait_analysis and profile.gait_analysis_enabled
        if gait_requested and profile.analysis_manifest is None:
            raise ValueError("The selected profile needs a gait analysis manifest.")
        if gait_requested and profile.calibration_map is None:
            raise ValueError("The selected profile needs a calibration map for gait analysis.")

        self.project_root = Path(project_root).expanduser().resolve()
        base = (
            Path(output_root).expanduser().resolve()
            if output_root is not None
            else self.project_root / "outputs" / "automated_pipeline"
        )
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.output_folder = _unique_run_folder(
            base / f"{timestamp}_{_safe_name(profile.name)}"
        )
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.processed_videos_folder = self.output_folder / "01_processed_videos"
        self.deeplabcut_folder = self.output_folder / "02_deeplabcut"
        self.analyzed_videos_folder = self.deeplabcut_folder / "analyzed_videos"
        self.labeled_videos_folder = self.deeplabcut_folder / "labeled_videos"
        self.knee_correction_folder = self.output_folder / "03_knee_correction"
        self.stickplots_folder = self.output_folder / "04_stickplots"
        self.gait_analysis_folder = self.output_folder / "05_gait_analysis"
        for folder in (
            self.processed_videos_folder,
            self.analyzed_videos_folder,
            self.labeled_videos_folder,
            self.knee_correction_folder,
            self.stickplots_folder,
            self.gait_analysis_folder,
        ):
            folder.mkdir(parents=True, exist_ok=True)

        self.processed_by_region: dict[str, list[Path]] = {}
        self.dlc_results: list[DlcAnalysisResult] = []
        self.analysis_csvs_by_region: dict[str, list[Path]] = {}
        self.stickplot_results: list[AlmaRunResult] = []
        self.gait_results: list[AlmaRunResult] = []

    def run_stage(
        self,
        stage_index: int,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        stages = (
            self._process_videos,
            self._run_deeplabcut,
            self._correct_knees,
            self._generate_stickplots,
            self._run_gait_analysis,
        )
        if not 0 <= stage_index < len(stages):
            raise ValueError(f"Unknown automated pipeline stage: {stage_index}")
        if not self.stage_enabled(stage_index):
            if progress_callback is not None:
                progress_callback(1, 1, f"{self.stage_skip_reason(stage_index)}; skipped")
            return
        stages[stage_index](progress_callback)

    def stage_enabled(self, stage_index: int) -> bool:
        if stage_index == 2:
            return (
                self.enable_knee_correction
                and self.profile.knee_correction_enabled
                and self.profile.knee_manifest is not None
            )
        if stage_index in (3, 4):
            return (
                self.enable_gait_analysis
                and self.profile.gait_analysis_enabled
                and self.profile.analysis_manifest is not None
                and self.profile.calibration_map is not None
            )
        return True

    def stage_skip_reason(self, stage_index: int) -> str:
        if stage_index == 2:
            if not self.enable_knee_correction:
                return "Knee correction disabled for this run"
            if not self.profile.knee_correction_enabled:
                return "Knee correction excluded from this profile"
            return "No knee correction manifest in the profile"
        if stage_index in (3, 4):
            if not self.enable_gait_analysis:
                return "Gait analysis disabled for this run"
            return "Gait analysis excluded from this profile"
        return "Stage disabled for this run"

    def review_artifacts(self, stage_index: int) -> dict[str, object]:
        if stage_index == 0:
            return {
                "kind": "videos",
                "items": [
                    {"path": path, "title": path.name, "view": region}
                    for region, paths in self.processed_by_region.items()
                    for path in paths
                ],
            }
        if stage_index == 1:
            return {
                "kind": "videos",
                "items": [
                    {"path": path, "title": path.name, "view": result.region}
                    for result in self.dlc_results
                    for path in result.labeled_video_paths
                ],
            }
        if stage_index == 3:
            return {
                "kind": "stickplots",
                "items": [
                    path
                    for result in self.stickplot_results
                    for path in result.output_files
                    if path.suffix.casefold() in {".svg", ".png", ".jpg", ".jpeg"}
                ],
            }
        return {"kind": "none", "items": []}

    def result(self) -> AutomatedPipelineResult:
        result = AutomatedPipelineResult(
            output_folder=self.output_folder,
            output_manifest=self.output_folder / "run_manifest.json",
            processed_videos=tuple(
                path for paths in self.processed_by_region.values() for path in paths
            ),
            coordinate_csvs=tuple(
                path for paths in self.analysis_csvs_by_region.values() for path in paths
            ),
            labeled_videos=tuple(
                path for result in self.dlc_results for path in result.labeled_video_paths
            ),
            stickplots=tuple(
                path
                for result in self.stickplot_results
                for path in result.output_files
                if path.suffix.casefold() in {".svg", ".png", ".jpg", ".jpeg"}
            ),
            analysis_outputs=tuple(
                path for result in self.gait_results for path in result.output_files
            ),
        )
        self._write_run_manifest(result)
        return result

    def _write_run_manifest(self, result: AutomatedPipelineResult) -> None:
        folders = {
            "processed_videos": self.processed_videos_folder,
            "analyzed_videos": self.analyzed_videos_folder,
            "labeled_videos": self.labeled_videos_folder,
            "knee_correction": self.knee_correction_folder,
            "stickplots": self.stickplots_folder,
            "gait_analysis": self.gait_analysis_folder,
        }
        artifacts = {
            "processed_videos": result.processed_videos,
            "coordinate_csvs": result.coordinate_csvs,
            "labeled_videos": result.labeled_videos,
            "stickplots": result.stickplots,
            "gait_analysis": result.analysis_outputs,
        }
        payload = {
            "profile": {"id": self.profile.id, "name": self.profile.name},
            "output_folder": str(self.output_folder),
            "folders": {name: str(path) for name, path in folders.items()},
            "artifacts": {
                name: [str(path) for path in paths]
                for name, paths in artifacts.items()
            },
        }
        result.output_manifest.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _process_videos(self, progress_callback: ProgressCallback | None) -> None:
        options, trim_ranges = video_settings_from_manifest(self.profile.processing_manifest)
        destination = self.processed_videos_folder
        total = len(self.video_paths)
        for index, video_path in enumerate(self.video_paths, start=1):
            trims = _trim_ranges_for_video(trim_ranges, video_path)
            results = process_video_outputs(
                video_path,
                destination,
                replace(options, trim_ranges=trims),
            )
            for result in results:
                region = result.crop_region_name or "Full frame"
                self.processed_by_region.setdefault(region, []).append(result.output_path)
            if progress_callback is not None:
                progress_callback(index, total, f"Processed {video_path.name}")
        if not self.processed_by_region:
            raise RuntimeError("Video processing did not produce any output videos.")

    def _run_deeplabcut(self, progress_callback: ProgressCallback | None) -> None:
        missing_models = set(self.processed_by_region) - set(self.profile.deeplabcut_models)
        if missing_models:
            names = ", ".join(sorted(missing_models))
            raise ValueError(f"The profile has no DeepLabCut model assigned for: {names}.")
        jobs = [
            DlcAnalysisJob(
                region=region,
                model_path=self.profile.deeplabcut_models[region],
                video_paths=tuple(paths),
            )
            for region, paths in self.processed_by_region.items()
        ]
        self.dlc_results = run_deeplabcut_analysis(
            jobs,
            self.deeplabcut_folder,
            progress_callback,
        )
        self.analysis_csvs_by_region = {
            result.region: list(result.csv_paths) for result in self.dlc_results
        }
        empty_regions = [region for region, paths in self.analysis_csvs_by_region.items() if not paths]
        if empty_regions:
            raise RuntimeError(
                "DeepLabCut did not produce coordinate CSVs for: "
                + ", ".join(empty_regions)
            )

    def _correct_knees(self, progress_callback: ProgressCallback | None) -> None:
        if self.profile.knee_manifest is None:
            if progress_callback is not None:
                progress_callback(1, 1, "No knee manifest; using DeepLabCut coordinates")
            return

        settings = knee_settings_from_manifest(self.profile.knee_manifest)
        pair_jobs = []
        corrected: dict[str, list[Path]] = {}
        region_roles = {result.region: _view_role(result.region) for result in self.dlc_results}
        three_view = set(region_roles.values()) >= {"left", "right", "bottom"}
        for result in self.dlc_results:
            if three_view and region_roles[result.region] == "bottom":
                corrected[result.region] = list(result.csv_paths)
                continue
            pairs = _pair_dlc_result(result)
            incomplete = [pair for pair in pairs if not pair.is_paired]
            if incomplete:
                details = ", ".join(f"{pair.stem}: {pair.status}" for pair in incomplete)
                raise ValueError(f"Could not pair DeepLabCut outputs for {result.region}: {details}")
            pair_jobs.extend((result.region, pair) for pair in pairs)

        if not pair_jobs:
            raise RuntimeError("No DeepLabCut coordinate sets were available for knee correction.")
        total = max(1, len(pair_jobs))
        knee_output_folder = getattr(
            self,
            "knee_correction_folder",
            self.output_folder / "03_knee_correction",
        )
        for index, (region, pair) in enumerate(pair_jobs, start=1):
            result = correct_knee_pair(
                pair,
                knee_output_folder / _safe_name(region),
                settings,
            )
            corrected.setdefault(region, []).append(result.output_csv)
            if progress_callback is not None:
                progress_callback(index, total, f"Corrected {pair.stem}")
        self.analysis_csvs_by_region = corrected

    def _generate_stickplots(self, progress_callback: ProgressCallback | None) -> None:
        settings = alma_settings_from_manifest(
            self.profile.analysis_manifest,
            self.profile.calibration_map,
        )
        inputs = self._alma_inputs(settings.input_mode)
        self.stickplot_results = run_alma_gait_analysis(
            inputs,
            self.stickplots_folder,
            replace(
                settings,
                generate_stickplot=True,
                generate_rustlab1_parameters=False,
            ),
            default_alma_root(self.project_root),
            progress_callback,
        )

    def _run_gait_analysis(self, progress_callback: ProgressCallback | None) -> None:
        settings = alma_settings_from_manifest(
            self.profile.analysis_manifest,
            self.profile.calibration_map,
        )
        inputs = self._alma_inputs(settings.input_mode)
        self.gait_results = run_alma_gait_analysis(
            inputs,
            self.gait_analysis_folder,
            replace(settings, generate_stickplot=False),
            default_alma_root(self.project_root),
            progress_callback,
        )

    def _alma_inputs(self, input_mode: str) -> list[Path | AlmaViewCsvSet]:
        if "single" in input_mode.casefold():
            inputs = [
                path
                for region in self.analysis_csvs_by_region.values()
                for path in sorted(region)
            ]
            if not inputs:
                raise RuntimeError("No coordinate CSVs are available for gait analysis.")
            return inputs

        roles = _view_regions(tuple(self.analysis_csvs_by_region))
        views = {
            role: sorted(self.analysis_csvs_by_region[region])
            for role, region in roles.items()
        }
        counts = {role: len(paths) for role, paths in views.items()}
        if not counts or not counts.get("left"):
            raise RuntimeError("No complete left/right/bottom CSV set is available.")
        if len(set(counts.values())) != 1:
            raise ValueError(
                "Left, right, and bottom views produced different CSV counts: "
                + ", ".join(f"{role}={count}" for role, count in counts.items())
            )
        return [
            AlmaViewCsvSet(
                name=_input_name(views["left"][index], index),
                left_csv=views["left"][index],
                right_csv=views["right"][index],
                bottom_csv=views["bottom"][index],
            )
            for index in range(counts["left"])
        ]


def _trim_ranges_for_video(trim_ranges: dict[str, tuple], video_path: Path) -> tuple:
    resolved = str(video_path.resolve())
    for key in (resolved, str(video_path), video_path.name, video_path.stem):
        if key in trim_ranges:
            return trim_ranges[key]
    for key, ranges in trim_ranges.items():
        if Path(key).name == video_path.name:
            return ranges
    return ()


def _view_regions(regions: tuple[str, ...]) -> dict[str, str]:
    matches: dict[str, list[str]] = {role: [] for role in VIEW_ALIASES}
    for region in regions:
        role = _view_role(region)
        if role is not None:
            matches[role].append(region)
    invalid = [role for role, names in matches.items() if len(names) != 1]
    if invalid:
        raise ValueError(
            "Multi side view requires exactly one crop region named for each view: "
            "left, right, and bottom. Rename the regions in the video settings manifest."
        )
    return {role: names[0] for role, names in matches.items()}


def _view_role(region: str) -> str | None:
    tokens = set(re.findall(r"[a-z0-9]+", region.casefold()))
    compact = "".join(tokens)
    matching_roles = [
        role
        for role, names in VIEW_ALIASES.items()
        if tokens & names or compact in names
    ]
    return matching_roles[0] if len(matching_roles) == 1 else None


def _input_name(path: Path, index: int) -> str:
    stem = re.split(r"DLC(?:_|-)?", path.stem, maxsplit=1, flags=re.IGNORECASE)[0]
    stem = re.sub(r"(?i)(?:_processed|_knee_corrected)$", "", stem).strip("._- ")
    return stem or f"recording_{index + 1}"


def _pair_dlc_result(result: DlcAnalysisResult) -> list[CoordinateFilePair]:
    pairs = []
    for video_path in result.video_paths:
        base = video_path.stem.casefold()
        csv_paths = tuple(path for path in result.csv_paths if _dlc_source_stem(path) == base)
        h5_paths = tuple(path for path in result.h5_paths if _dlc_source_stem(path) == base)
        pairs.append(
            CoordinateFilePair(
                directory=csv_paths[0].parent if csv_paths else video_path.parent,
                stem=video_path.stem,
                csv_paths=csv_paths,
                h5_paths=h5_paths,
                video_paths=(video_path,),
            )
        )
    return pairs


def _dlc_source_stem(path: Path) -> str:
    stem = re.split(r"DLC(?:_|-)?", path.stem, maxsplit=1, flags=re.IGNORECASE)[0]
    return re.sub(r"(?i)(?:_filtered)$", "", stem).rstrip("._- ").casefold()


def _safe_name(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in "-_" else "_" for character in value)
    return safe.strip("_") or "pipeline"


def _unique_run_folder(candidate: Path) -> Path:
    if not candidate.exists():
        return candidate
    suffix = 2
    while (numbered := candidate.with_name(f"{candidate.name}_{suffix}")).exists():
        suffix += 1
    return numbered
