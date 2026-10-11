"""Execute automatic stage handoffs through injected manual operations and persistence ports."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import ReviewArtifact, StageReview
from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import (
    AutomatedStage,
    coerce_automated_stage,
)
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.runs.business.automatic_recording_pairing import (
    dlc_source_stem,
    input_name,
    pair_dlc_result,
    view_regions,
)
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_contracts import (
    AutomatedPipelineResult,
    ProgressCallback,
)
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_plan import AutomaticRunPlan
from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_preflight import preflight_automatic_run
from dlc_gait_assembly.runway.automatic.runs.business.stages.automatic_deeplabcut_analysis_stage import (
    execute_deeplabcut_analysis,
)
from dlc_gait_assembly.runway.automatic.runs.business.stages.automatic_gait_analysis_stage import execute_gait_analysis
from dlc_gait_assembly.runway.automatic.runs.business.stages.automatic_knee_correction_stage import (
    execute_knee_correction,
)
from dlc_gait_assembly.runway.automatic.runs.business.stages.automatic_labeled_video_stage import execute_labeled_video
from dlc_gait_assembly.runway.automatic.runs.business.stages.automatic_stickplot_stage import execute_stickplot
from dlc_gait_assembly.runway.automatic.runs.business.stages.automatic_video_processing_stage import (
    execute_video_processing,
)
from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_job_contracts import (
    DlcAnalysisJob,
    DlcAnalysisResult,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_contracts import AlmaRunResult
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionProgress


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
        *,
        operations,
        storage,
    ):
        self.operations = operations
        self.storage = storage
        self.profile = profile
        self.enable_knee_correction = bool(enable_knee_correction)
        self.enable_gait_analysis = bool(enable_gait_analysis)
        self.video_paths = preflight_automatic_run(
            profile, video_paths, storage, self.enable_knee_correction, self.enable_gait_analysis
        )
        self.plan = AutomaticRunPlan(profile, self.enable_knee_correction, self.enable_gait_analysis)
        self.storage.allocate(self, project_root, output_root, profile)
        self.processed_by_region: dict[str, list[Path]] = {}
        self.dlc_jobs: list[DlcAnalysisJob] = []
        self.dlc_results: list[DlcAnalysisResult] = []
        self.analysis_csvs_by_region: dict[str, list[Path]] = {}
        self.stickplot_results: list[AlmaRunResult] = []
        self.gait_results: list[AlmaRunResult] = []
        self._completed_stages: set[AutomatedStage] = set()
        self._skipped_stages: set[AutomatedStage] = set()

    def run_stage(self, stage_index: int | AutomatedStage, progress_callback: ProgressCallback | None = None) -> None:
        stage = coerce_automated_stage(stage_index)
        stages = (
            lambda progress: execute_video_processing(self, progress),
            lambda progress: execute_deeplabcut_analysis(self, progress),
            lambda progress: execute_knee_correction(self, progress),
            lambda progress: execute_labeled_video(self, progress),
            lambda progress: execute_stickplot(self, progress),
            lambda progress: execute_gait_analysis(self, progress),
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
            if predecessor < stage and self.stage_enabled(predecessor) and (predecessor not in self._completed_stages)
        ]
        if missing_predecessors:
            predecessor = missing_predecessors[0]
            raise RuntimeError(
                f"Run {predecessor.name.replace('_', ' ').title()} before {stage.name.replace('_', ' ').title()}."
            )
        stages[int(stage)](progress_callback)
        self._completed_stages.add(stage)

    def stage_enabled(self, stage_index: int | AutomatedStage) -> bool:
        return self.plan.stage_enabled(stage_index)

    def stage_skip_reason(self, stage_index: int | AutomatedStage) -> str:
        return self.plan.stage_skip_reason(stage_index)

    def review_artifacts(self, stage_index: int | AutomatedStage) -> StageReview:
        stage = coerce_automated_stage(stage_index)
        if stage is AutomatedStage.VIDEO_PROCESSING:
            return StageReview(
                stage=stage,
                kind="videos",
                items=tuple(
                    ReviewArtifact(path=path, title=path.name, view=region)
                    for (region, paths) in self.processed_by_region.items()
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
            processed_videos=tuple(path for paths in self.processed_by_region.values() for path in paths),
            coordinate_csvs=tuple(path for paths in self.analysis_csvs_by_region.values() for path in paths),
            labeled_videos=tuple(path for result in self.dlc_results for path in result.labeled_video_paths),
            stickplots=tuple(
                path
                for result in self.stickplot_results
                for path in result.output_files
                if path.suffix.casefold() in {".svg", ".png", ".jpg", ".jpeg"}
            ),
            analysis_outputs=tuple(dict.fromkeys(path for result in self.gait_results for path in result.output_files)),
        )
        self.storage.write_manifest(self, result)
        return result

    def _alma_inputs(self, input_mode: str) -> list[Path | AlmaViewCsvSet]:
        if "single" in input_mode.casefold():
            inputs = [path for region in self.analysis_csvs_by_region for path in self._ordered_region_csvs(region)]
            if not inputs:
                raise RuntimeError("No coordinate CSVs are available for gait analysis.")
            return inputs
        roles = view_regions(tuple(self.analysis_csvs_by_region))
        views = {role: self._ordered_region_csvs(region) for (role, region) in roles.items()}
        counts = {role: len(paths) for (role, paths) in views.items()}
        if not counts or not counts.get("left"):
            raise RuntimeError("No complete left/right/bottom CSV set is available.")
        if len(set(counts.values())) != 1:
            raise ValueError(
                "Left, right, and bottom views produced different CSV counts: "
                + ", ".join(f"{role}={count}" for (role, count) in counts.items())
            )
        return [
            AlmaViewCsvSet(
                name=input_name(views["left"][index], index),
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
            matches = [path for path in remaining if dlc_source_stem(path) == expected_stem]
            if len(matches) != 1:
                raise ValueError(
                    f'DeepLabCut coordinates for region "{region}" could not be matched unambiguously to "{video_path.name}".'
                )
            ordered.append(matches[0])
            remaining.remove(matches[0])
        if remaining:
            raise ValueError(
                f'DeepLabCut returned coordinate CSVs for region "{region}" that do not match the processed videos.'
            )
        return ordered

    def _validate_dlc_results(
        self, results: list[DlcAnalysisResult], *, require_labeled_videos: bool = False
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
            raise RuntimeError("DeepLabCut results do not match the configured regions: " + "; ".join(details) + ".")
        by_region = {result.region: result for result in results}
        ordered_results = [by_region[job.region] for job in self.dlc_jobs]
        for result in ordered_results:
            job = jobs_by_region[result.region]
            if result.video_paths != job.video_paths:
                raise RuntimeError(f'DeepLabCut returned the wrong video list for region "{result.region}".')
            if len(result.csv_paths) != len(job.video_paths) or len(result.h5_paths) != len(job.video_paths):
                raise RuntimeError(
                    f'DeepLabCut did not return exactly one CSV and H5 coordinate file per video for region "{result.region}".'
                )
            missing_paths = [path for path in (*result.csv_paths, *result.h5_paths) if not self.storage.is_file(path)]
            if missing_paths:
                raise RuntimeError(f"DeepLabCut reported an output that does not exist: {missing_paths[0]}")
            incomplete_pairs = [pair for pair in pair_dlc_result(result) if not pair.is_paired]
            if incomplete_pairs:
                raise RuntimeError(
                    f'DeepLabCut coordinate files could not be matched to every video for region "{result.region}".'
                )
            if require_labeled_videos:
                if len(result.labeled_video_paths) != len(job.video_paths):
                    raise RuntimeError(
                        f'DeepLabCut did not return exactly one labeled video per source video for region "{result.region}".'
                    )
                missing_labeled = [path for path in result.labeled_video_paths if not self.storage.is_file(path)]
                if missing_labeled:
                    raise RuntimeError(f"DeepLabCut reported a labeled video that does not exist: {missing_labeled[0]}")
        return ordered_results

    def _validate_alma_results(
        self, results: list[AlmaRunResult], inputs: list[Path | AlmaViewCsvSet], *, require_stickplot: bool = False
    ) -> None:
        if len(results) != len(inputs):
            raise RuntimeError("Gait analysis returned an incomplete set of results.")
        missing_outputs = [path for result in results for path in result.output_files if not self.storage.is_file(path)]
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


def execute_automatic_run(pipeline, events, control):
    """Execute stage handoffs and review gates through client-independent callbacks."""
    from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AUTOMATED_STAGE_SPECS

    for spec in AUTOMATED_STAGE_SPECS:
        stage = int(spec.stage)
        control.current_stage = stage
        control.check_cancelled()
        events.stage_started(stage, spec.label)
        enabled = pipeline.stage_enabled(stage)
        events.log_message(f"Started {spec.label}" if enabled else pipeline.stage_skip_reason(stage))

        def report(current, total, message, stage=stage):
            control.check_cancelled()
            events.stage_progress(stage, current, total, message)

        pipeline.run_stage(stage, ExecutionProgress(report, control.check_cancelled))
        if not enabled:
            events.stage_skipped(stage, pipeline.stage_skip_reason(stage))
            events.log_message(f"Skipped {spec.label}")
            continue
        events.stage_progress(stage, 1, 1, f"{spec.label} complete")
        events.log_message(f"Completed {spec.label}")
        control.check_cancelled()
        if spec.review_kind is not None:
            control.review(pipeline.review_artifacts(stage), events.review_requested)
            events.log_message(f"Approved {spec.label} review")
    control.check_cancelled()
    return pipeline.result()
