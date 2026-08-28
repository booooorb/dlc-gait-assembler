from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from dlc_gait_assembly.gui.automated_pipeline import worker as worker_module
from dlc_gait_assembly.gui.automated_pipeline.worker import AutomatedPipelineWorker
from dlc_gait_assembly.services.pipeline.automated import AutomatedStage, StageReview


class _SuccessfulPipeline:
    instances = []

    def __init__(self, *_args, **_kwargs):
        self.output_folder = Path("/tmp/automated-worker-output")
        self.stage_calls = []
        type(self).instances.append(self)

    def stage_enabled(self, stage_index):
        return stage_index != int(AutomatedStage.KNEE_CORRECTION)

    def stage_skip_reason(self, _stage_index):
        return "Knee correction excluded from this profile"

    def run_stage(self, stage_index, progress_callback):
        self.stage_calls.append(stage_index)
        progress_callback(1, 2, f"stage {stage_index} halfway")

    def review_artifacts(self, stage_index):
        return StageReview(AutomatedStage(stage_index), "videos")

    def result(self):
        return SimpleNamespace(output_folder=self.output_folder)


def test_worker_runs_all_stages_skips_disabled_stage_and_waits_for_reviews(monkeypatch):
    _SuccessfulPipeline.instances.clear()
    monkeypatch.setattr(worker_module, "AutomatedPipelineRun", _SuccessfulPipeline)
    worker = AutomatedPipelineWorker(
        SimpleNamespace(),
        [Path("source.mp4")],
        Path("."),
    )
    started = []
    progress = []
    skipped = []
    reviews = []
    completed = []
    worker.stage_started.connect(lambda index, label: started.append((index, label)))
    worker.stage_progress.connect(
        lambda stage, current, total, message: progress.append(
            (stage, current, total, message)
        )
    )
    worker.stage_skipped.connect(lambda index, reason: skipped.append((index, reason)))

    def approve_review(stage_index, artifacts):
        reviews.append((stage_index, artifacts))
        worker.approve_review()

    worker.review_requested.connect(approve_review)
    worker.run_completed.connect(completed.append)

    worker.run()

    assert [index for index, _label in started] == list(range(6))
    assert _SuccessfulPipeline.instances[0].stage_calls == list(range(6))
    assert skipped == [(2, "Knee correction excluded from this profile")]
    assert [index for index, _artifacts in reviews] == [0, 3, 4]
    assert all(isinstance(artifacts, StageReview) for _index, artifacts in reviews)
    assert any(item[:3] == (1, 1, 2) for item in progress)
    assert len(completed) == 1
    assert worker.waiting_for_review is False


def test_worker_reports_the_stage_that_failed(monkeypatch):
    class FailingPipeline(_SuccessfulPipeline):
        def run_stage(self, stage_index, progress_callback):
            if stage_index == 1:
                raise RuntimeError("pose analysis failed")
            super().run_stage(stage_index, progress_callback)

    monkeypatch.setattr(worker_module, "AutomatedPipelineRun", FailingPipeline)
    worker = AutomatedPipelineWorker(SimpleNamespace(), [Path("source.mp4")], Path("."))
    failures = []
    completions = []
    worker.review_requested.connect(lambda _index, _artifacts: worker.approve_review())
    worker.run_failed.connect(lambda index, message: failures.append((index, message)))
    worker.run_completed.connect(completions.append)

    worker.run()

    assert failures == [(1, "pose analysis failed")]
    assert completions == []
