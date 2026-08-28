from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

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
from dlc_gait_assembly.services.pipeline.automated.models import (
    AutomatedPipelineResult,
    ReviewArtifact,
    StageReview,
)
from dlc_gait_assembly.services.pipeline.automated.stages import (
    AutomatedStage,
    coerce_automated_stage,
)
from dlc_gait_assembly.services.pipeline.deeplabcut import (
    DlcAnalysisJob,
    DlcAnalysisResult,
    run_deeplabcut_analysis,
    run_deeplabcut_labeled_video_creation,
)
from dlc_gait_assembly.services.video_processing import process_video_outputs

ProgressCallback = Callable[[int, int, str], None]
VIEW_ALIASES = {
    "left": {"left", "lh", "leftside", "leftview"},
    "right": {"right", "rh", "rightside", "rightview"},
    "bottom": {"bottom", "down", "downward", "ventral", "below", "bottomview"},
}


class AutomatedPipelineRun:
    """Stateful six-stage run whose outputs feed directly into the next stage."""

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
        if len(set(self.video_paths)) != len(self.video_paths):
            raise ValueError("Each source video may only be added to a pipeline run once.")
        missing = [path for path in self.video_paths if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"Source video no longer exists: {missing[0]}")
        if profile.processing_manifest is None:
            raise ValueError("The selected profile needs a video settings manifest.")
        if not Path(profile.processing_manifest).expanduser().is_file():
            raise FileNotFoundError(
                f"Video settings manifest no longer exists: {profile.processing_manifest}"
            )
        gait_requested = self.enable_gait_analysis and profile.gait_analysis_enabled
        if gait_requested and profile.analysis_manifest is None:
            raise ValueError("The selected profile needs a gait analysis manifest.")
        if gait_requested and profile.calibration_map is None:
            raise ValueError("The selected profile needs a calibration map for gait analysis.")
        if gait_requested and not Path(profile.analysis_manifest).expanduser().is_file():
            raise FileNotFoundError(
                f"Gait analysis manifest no longer exists: {profile.analysis_manifest}"
            )
        if gait_requested and not Path(profile.calibration_map).expanduser().is_file():
            raise FileNotFoundError(
                f"Calibration map no longer exists: {profile.calibration_map}"
            )
        knee_requested = self.enable_knee_correction and profile.knee_correction_enabled
        if knee_requested and profile.knee_manifest is None:
            raise ValueError("The selected profile needs a knee correction manifest.")
        if knee_requested and not Path(profile.knee_manifest).expanduser().is_file():
            raise FileNotFoundError(
                f"Knee correction manifest no longer exists: {profile.knee_manifest}"
            )

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
        self.dlc_jobs: list[DlcAnalysisJob] = []
        self.dlc_results: list[DlcAnalysisResult] = []
        self.analysis_csvs_by_region: dict[str, list[Path]] = {}
        self.stickplot_results: list[AlmaRunResult] = []
        self.gait_results: list[AlmaRunResult] = []
        self._completed_stages: set[AutomatedStage] = set()
        self._skipped_stages: set[AutomatedStage] = set()

    def run_stage(
        self,
        stage_index: int | AutomatedStage,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        stage = coerce_automated_stage(stage_index)
        stages = (
            self._process_videos,
            self._run_deeplabcut,
            self._correct_knees,
            self._create_labeled_videos,
            self._generate_stickplots,
            self._run_gait_analysis,
        )
        if stage in self._completed_stages:
            raise RuntimeError(f"{stage.name.replace('_', ' ').title()} has already run.")
        if not self.stage_enabled(stage):
            self._completed_stages.add(stage)
            self._skipped_stages.add(stage)
            if progress_callback is not None:
                progress_callback(1, 1, f"{self.stage_skip_reason(stage)}; skipped")
            return
        missing_predecessors = [
            predecessor
            for predecessor in AutomatedStage
            if predecessor < stage
            and self.stage_enabled(predecessor)
            and predecessor not in self._completed_stages
        ]
        if missing_predecessors:
            predecessor = missing_predecessors[0]
            raise RuntimeError(
                f"Run {predecessor.name.replace('_', ' ').title()} before "
                f"{stage.name.replace('_', ' ').title()}."
            )
        stages[int(stage)](progress_callback)
        self._completed_stages.add(stage)

    def stage_enabled(self, stage_index: int | AutomatedStage) -> bool:
        stage = coerce_automated_stage(stage_index)
        if stage is AutomatedStage.KNEE_CORRECTION:
            return (
                self.enable_knee_correction
                and self.profile.knee_correction_enabled
                and self.profile.knee_manifest is not None
            )
        if stage in (AutomatedStage.STICKPLOT, AutomatedStage.GAIT_ANALYSIS):
            return (
                self.enable_gait_analysis
                and self.profile.gait_analysis_enabled
                and self.profile.analysis_manifest is not None
                and self.profile.calibration_map is not None
            )
        return True

    def stage_skip_reason(self, stage_index: int | AutomatedStage) -> str:
        stage = coerce_automated_stage(stage_index)
        if stage is AutomatedStage.KNEE_CORRECTION:
            if not self.enable_knee_correction:
                return "Knee correction disabled for this run"
            if not self.profile.knee_correction_enabled:
                return "Knee correction excluded from this profile"
            return "No knee correction manifest in the profile"
        if stage in (AutomatedStage.STICKPLOT, AutomatedStage.GAIT_ANALYSIS):
            if not self.enable_gait_analysis:
                return "Gait analysis disabled for this run"
            return "Gait analysis excluded from this profile"
        return "Stage disabled for this run"

    def review_artifacts(self, stage_index: int | AutomatedStage) -> StageReview:
        stage = coerce_automated_stage(stage_index)
        if stage is AutomatedStage.VIDEO_PROCESSING:
            return StageReview(
                stage=stage,
                kind="videos",
                items=tuple(
                    ReviewArtifact(path=path, title=path.name, view=region)
                    for region, paths in self.processed_by_region.items()
                    for path in paths
                ),
            )
        if stage is AutomatedStage.LABELED_VIDEOS:
            return StageReview(
                stage=stage,
                kind="videos",
                items=tuple(
                    ReviewArtifact(path=path, title=path.name, view=result.region)
                    for result in self.dlc_results
                    for path in result.labeled_video_paths
                ),
            )
        if stage is AutomatedStage.STICKPLOT:
            return StageReview(
                stage=stage,
                kind="stickplots",
                items=tuple(
                    ReviewArtifact(path=path, title=path.name)
                    for result in self.stickplot_results
                    for path in result.output_files
                    if path.suffix.casefold() in {".svg", ".png", ".jpg", ".jpeg"}
                ),
            )
        return StageReview(stage=stage, kind="none")

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
        self.dlc_jobs = [
            DlcAnalysisJob(
                region=region,
                model_path=self.profile.deeplabcut_models[region],
                video_paths=tuple(paths),
            )
            for region, paths in self.processed_by_region.items()
        ]
        self.dlc_results = run_deeplabcut_analysis(
            self.dlc_jobs,
            self.deeplabcut_folder,
            progress_callback,
        )
        self.dlc_results = self._validate_dlc_results(self.dlc_results)
        self.analysis_csvs_by_region = {
            result.region: list(result.csv_paths) for result in self.dlc_results
        }

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
        work_folder = knee_output_folder / "work"
        prepared = []
        replacement_records = []
        try:
            for index, (region, pair) in enumerate(pair_jobs, start=1):
                result = correct_knee_pair(
                    pair,
                    work_folder / _safe_name(region),
                    settings,
                )
                if pair.csv_path is None or pair.h5_path is None:
                    raise RuntimeError(f"Knee correction lost the coordinate pair for {pair.stem}.")
                if not result.output_csv.is_file() or not result.output_h5.is_file():
                    raise RuntimeError(f"Knee correction did not produce both outputs for {pair.stem}.")
                prepared.append((region, pair, result))
                if progress_callback is not None:
                    progress_callback(index, total, f"Prepared correction for {pair.stem}")

            backups = []
            backup_folder = work_folder / "backups"
            backup_folder.mkdir(parents=True, exist_ok=True)
            for index, (_region, pair, _result) in enumerate(prepared, start=1):
                backup_csv = backup_folder / f"{index:04d}.csv"
                backup_h5 = backup_folder / f"{index:04d}.h5"
                shutil.copy2(pair.csv_path, backup_csv)
                shutil.copy2(pair.h5_path, backup_h5)
                backups.append((pair, backup_csv, backup_h5))

            try:
                for region, pair, result in prepared:
                    result.output_csv.replace(pair.csv_path)
                    result.output_h5.replace(pair.h5_path)
                    corrected.setdefault(region, []).append(pair.csv_path)
                    replacement_records.append(
                        {
                            "region": region,
                            "video": str(pair.video_path) if pair.video_path is not None else "",
                            "csv": str(pair.csv_path),
                            "h5": str(pair.h5_path),
                        }
                    )
            except Exception:
                for pair, backup_csv, backup_h5 in backups:
                    try:
                        shutil.copy2(backup_csv, pair.csv_path)
                        shutil.copy2(backup_h5, pair.h5_path)
                    except OSError:
                        pass
                raise
        finally:
            if work_folder.exists():
                shutil.rmtree(work_folder)
        (knee_output_folder / "correction_manifest.json").write_text(
            json.dumps({"replaced_coordinates": replacement_records}, indent=2) + "\n",
            encoding="utf-8",
        )
        self.analysis_csvs_by_region = corrected

    def _create_labeled_videos(
        self,
        progress_callback: ProgressCallback | None,
    ) -> None:
        coordinate_paths = {
            result.region: (result.csv_paths, result.h5_paths)
            for result in self.dlc_results
        }
        labeled_results = run_deeplabcut_labeled_video_creation(
            self.dlc_jobs,
            self.dlc_results,
            self.deeplabcut_folder,
            progress_callback,
        )
        self.dlc_results = self._validate_dlc_results(
            labeled_results,
            require_labeled_videos=True,
        )
        for result in self.dlc_results:
            if (result.csv_paths, result.h5_paths) != coordinate_paths[result.region]:
                raise RuntimeError(
                    f'DeepLabCut labeled-video creation changed the coordinate files for "{result.region}".'
                )

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
                generate_alma_representations=False,
                generate_rustlab1_parameters=False,
                stroke_analysis_enabled=False,
            ),
            default_alma_root(self.project_root),
            progress_callback,
        )
        self._validate_alma_results(self.stickplot_results, inputs, require_stickplot=True)

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
        self._validate_alma_results(self.gait_results, inputs)

    def _alma_inputs(self, input_mode: str) -> list[Path | AlmaViewCsvSet]:
        if "single" in input_mode.casefold():
            inputs = [
                path
                for region in self.analysis_csvs_by_region
                for path in self._ordered_region_csvs(region)
            ]
            if not inputs:
                raise RuntimeError("No coordinate CSVs are available for gait analysis.")
            return inputs

        roles = _view_regions(tuple(self.analysis_csvs_by_region))
        views = {
            role: self._ordered_region_csvs(region)
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

    def _ordered_region_csvs(self, region: str) -> list[Path]:
        paths = list(self.analysis_csvs_by_region.get(region, ()))
        job = next((item for item in self.dlc_jobs if item.region == region), None)
        if job is None:
            return sorted(paths)

        remaining = set(paths)
        ordered: list[Path] = []
        for video_path in job.video_paths:
            expected_stem = video_path.stem.casefold()
            matches = [
                path
                for path in remaining
                if _dlc_source_stem(path) == expected_stem
            ]
            if len(matches) != 1:
                raise ValueError(
                    f'DeepLabCut coordinates for region "{region}" could not be matched '
                    f'unambiguously to "{video_path.name}".'
                )
            ordered.append(matches[0])
            remaining.remove(matches[0])
        if remaining:
            raise ValueError(
                f'DeepLabCut returned coordinate CSVs for region "{region}" that do not '
                "match the processed videos."
            )
        return ordered

    def _validate_dlc_results(
        self,
        results: list[DlcAnalysisResult],
        *,
        require_labeled_videos: bool = False,
    ) -> list[DlcAnalysisResult]:
        jobs_by_region = {job.region: job for job in self.dlc_jobs}
        result_regions = [result.region for result in results]
        if len(set(result_regions)) != len(result_regions):
            raise RuntimeError("DeepLabCut returned duplicate region results.")
        if set(result_regions) != set(jobs_by_region):
            missing = sorted(set(jobs_by_region) - set(result_regions))
            unexpected = sorted(set(result_regions) - set(jobs_by_region))
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unexpected:
                details.append("unexpected " + ", ".join(unexpected))
            raise RuntimeError(
                "DeepLabCut results do not match the configured regions: "
                + "; ".join(details)
                + "."
            )

        by_region = {result.region: result for result in results}
        ordered_results = [by_region[job.region] for job in self.dlc_jobs]
        for result in ordered_results:
            job = jobs_by_region[result.region]
            if result.video_paths != job.video_paths:
                raise RuntimeError(
                    f'DeepLabCut returned the wrong video list for region "{result.region}".'
                )
            if len(result.csv_paths) != len(job.video_paths) or len(result.h5_paths) != len(job.video_paths):
                raise RuntimeError(
                    f'DeepLabCut did not return exactly one CSV and H5 coordinate file per video '
                    f'for region "{result.region}".'
                )
            missing_paths = [
                path
                for path in (*result.csv_paths, *result.h5_paths)
                if not path.is_file()
            ]
            if missing_paths:
                raise RuntimeError(f"DeepLabCut reported an output that does not exist: {missing_paths[0]}")
            incomplete_pairs = [pair for pair in _pair_dlc_result(result) if not pair.is_paired]
            if incomplete_pairs:
                raise RuntimeError(
                    f'DeepLabCut coordinate files could not be matched to every video for region '
                    f'"{result.region}".'
                )
            if require_labeled_videos:
                if len(result.labeled_video_paths) != len(job.video_paths):
                    raise RuntimeError(
                        f'DeepLabCut did not return exactly one labeled video per source video '
                        f'for region "{result.region}".'
                    )
                missing_labeled = [path for path in result.labeled_video_paths if not path.is_file()]
                if missing_labeled:
                    raise RuntimeError(
                        f"DeepLabCut reported a labeled video that does not exist: {missing_labeled[0]}"
                    )
        return ordered_results

    @staticmethod
    def _validate_alma_results(
        results: list[AlmaRunResult],
        inputs: list[Path | AlmaViewCsvSet],
        *,
        require_stickplot: bool = False,
    ) -> None:
        if len(results) != len(inputs):
            raise RuntimeError("Gait analysis returned an incomplete set of results.")
        missing_outputs = [
            path
            for result in results
            for path in result.output_files
            if not path.is_file()
        ]
        if missing_outputs:
            raise RuntimeError(f"Gait analysis reported an output that does not exist: {missing_outputs[0]}")
        if any(not result.output_files for result in results):
            raise RuntimeError("Gait analysis did not produce outputs for every recording.")
        if require_stickplot:
            preview_suffixes = {".svg", ".png", ".jpg", ".jpeg"}
            if any(
                not any(path.suffix.casefold() in preview_suffixes for path in result.output_files)
                for result in results
            ):
                raise RuntimeError("Stickplot generation did not produce a preview for every recording.")


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
