from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from dlc_gait_assembly.services.analysis_manifests import (
    write_analysis_manifest,
    write_video_settings_manifest,
)
from dlc_gait_assembly.services.automated_profiles import AutomatedPipelineProfile
from dlc_gait_assembly.services.domain.regions import CropRegion, NormalizedRect
from dlc_gait_assembly.services.pipeline import automated
from dlc_gait_assembly.services.pipeline.automated import run as automated_run
from dlc_gait_assembly.services.pipeline.alma import AlmaRunResult, AlmaSettings, AlmaViewCsvSet
from dlc_gait_assembly.services.pipeline.deeplabcut import (
    DlcAnalysisResult,
    DlcAnalysisJob,
    _DlcProgressParser,
    _run_request,
    resolve_deeplabcut_config,
    validate_deeplabcut_project,
)
from dlc_gait_assembly.services.video_processing import ProcessingOptions, ProcessingResult


def test_automated_pipeline_hands_outputs_through_all_six_stages(tmp_path, monkeypatch):
    regions = ("Left view", "Right view", "Bottom view")
    processing_manifest = tmp_path / "video_settings.json"
    write_video_settings_manifest(
        processing_manifest,
        ProcessingOptions(
            crop_enabled=True,
            crop_regions=tuple(
                CropRegion(name, NormalizedRect(index / 4, 0, 0.2, 0.8))
                for index, name in enumerate(regions)
            ),
        ),
    )
    analysis_manifest = tmp_path / "gait_settings.json"
    write_analysis_manifest(
        analysis_manifest,
        AlmaSettings(input_mode="Multi side view"),
    )
    calibration_map = tmp_path / "calibration.csv"
    calibration_map.write_text("fixture", encoding="utf-8")
    models = {}
    for region in regions:
        model = tmp_path / f"model_{region.split()[0].lower()}"
        model.mkdir()
        (model / "config.yaml").write_text("Task: fixture\n", encoding="utf-8")
        models[region] = model
    profile = AutomatedPipelineProfile(
        id="a" * 32,
        name="Three views",
        processing_manifest=processing_manifest,
        calibration_map=calibration_map,
        deeplabcut_models=models,
        analysis_manifest=analysis_manifest,
    )
    videos = [tmp_path / "mouse_1.mp4", tmp_path / "mouse_2.mp4"]
    for video in videos:
        video.write_bytes(b"fixture")

    def fake_process(input_path, output_dir, options):
        results = []
        for region in options.effective_crop_regions():
            output = Path(output_dir) / region.name.replace(" ", "_") / f"{Path(input_path).stem}_processed.mp4"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"video")
            results.append(
                ProcessingResult(Path(input_path), output, [], crop_region_name=region.name)
            )
        return results

    def fake_dlc(jobs, output_folder, progress_callback=None):
        results = []
        for index, job in enumerate(jobs, start=1):
            region_name = job.region.replace(" ", "_")
            analysis_folder = Path(output_folder) / "analyzed_videos" / region_name
            analysis_folder.mkdir(parents=True, exist_ok=True)
            csvs = []
            h5s = []
            for video in job.video_paths:
                csv_path = analysis_folder / f"{video.stem}DLC_fixture.csv"
                h5_path = analysis_folder / f"{video.stem}DLC_fixture.h5"
                csv_path.write_text("coordinates", encoding="utf-8")
                h5_path.write_bytes(b"coordinates")
                csvs.append(csv_path)
                h5s.append(h5_path)
            results.append(
                DlcAnalysisResult(
                    job.region,
                    job.video_paths,
                    tuple(csvs),
                    tuple(h5s),
                    (),
                )
            )
            if progress_callback is not None:
                progress_callback(index, len(jobs), job.region)
        return results

    def fake_create_labeled(jobs, analysis_results, output_folder, progress_callback=None):
        completed = []
        for index, (job, result) in enumerate(zip(jobs, analysis_results), start=1):
            labeled_folder = (
                Path(output_folder)
                / "labeled_videos"
                / job.region.replace(" ", "_")
            )
            labeled_folder.mkdir(parents=True, exist_ok=True)
            overlays = []
            for video in job.video_paths:
                overlay = labeled_folder / f"{video.stem}DLC_fixture_labeled.mp4"
                overlay.write_bytes(b"video")
                overlays.append(overlay)
            completed.append(
                DlcAnalysisResult(
                    result.region,
                    result.video_paths,
                    result.csv_paths,
                    result.h5_paths,
                    tuple(overlays),
                )
            )
            if progress_callback is not None:
                progress_callback(index, len(jobs), job.region)
        return completed

    alma_calls = []

    def fake_alma(inputs, output_folder, settings, alma_root, progress_callback=None):
        assert all(isinstance(item, AlmaViewCsvSet) for item in inputs)
        assert all(item.left_csv.is_file() for item in inputs)
        assert settings.calibration_map_path == calibration_map.resolve()
        alma_calls.append((tuple(inputs), settings))
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        results = []
        for index, item in enumerate(inputs, start=1):
            suffix = ".svg" if settings.generate_stickplot else ".csv"
            output = Path(output_folder) / f"{item.name}{suffix}"
            output.write_text("result", encoding="utf-8")
            results.append(AlmaRunResult(item.left_csv, (output,)))
            if progress_callback is not None:
                progress_callback(index, len(inputs), item.name)
        return results

    monkeypatch.setattr(automated_run, "process_video_outputs", fake_process)
    monkeypatch.setattr(automated_run, "run_deeplabcut_analysis", fake_dlc)
    monkeypatch.setattr(
        automated_run,
        "run_deeplabcut_labeled_video_creation",
        fake_create_labeled,
    )
    monkeypatch.setattr(automated_run, "run_alma_gait_analysis", fake_alma)

    run = automated.AutomatedPipelineRun(profile, videos, tmp_path, tmp_path / "runs")
    for stage in range(6):
        run.run_stage(stage)

    result = run.result()
    assert len(result.processed_videos) == 6
    assert len(result.coordinate_csvs) == 6
    assert len(result.labeled_videos) == 6
    assert len(result.stickplots) == 2
    assert len(result.analysis_outputs) == 2
    assert len(alma_calls) == 2
    assert alma_calls[0][1].generate_stickplot is True
    assert alma_calls[0][1].generate_alma_representations is False
    assert alma_calls[0][1].generate_rustlab1_parameters is False
    assert alma_calls[0][1].stroke_analysis_enabled is False
    assert alma_calls[1][1].generate_stickplot is False
    assert alma_calls[1][1].generate_alma_representations is True
    assert len(run.review_artifacts(0).items) == 6
    assert len(run.review_artifacts(3).items) == 6
    assert len(run.review_artifacts(4).items) == 2
    assert result.output_manifest.is_file()
    manifest = json.loads(result.output_manifest.read_text(encoding="utf-8"))
    assert Path(manifest["folders"]["analyzed_videos"]) == run.analyzed_videos_folder
    assert Path(manifest["folders"]["labeled_videos"]) == run.labeled_videos_folder
    assert all(run.analyzed_videos_folder in path.parents for path in result.coordinate_csvs)
    assert all(run.labeled_videos_folder in path.parents for path in result.labeled_videos)


def test_deeplabcut_config_resolution_requires_one_project(tmp_path):
    project = tmp_path / "model"
    project.mkdir()
    config = project / "config.yaml"
    config.write_text(
        "Task: fixture\ndate: Jan1\niteration: 0\nTrainingFraction: [0.95]\n",
        encoding="utf-8",
    )

    assert resolve_deeplabcut_config(project) == config
    assert resolve_deeplabcut_config(config) == config

    second = project / "nested" / "config.yaml"
    second.parent.mkdir()
    second.write_text("Task: second\n", encoding="utf-8")
    config.unlink()
    assert resolve_deeplabcut_config(project) == second

    (project / "other" / "config.yaml").parent.mkdir()
    (project / "other" / "config.yaml").write_text("Task: other\n", encoding="utf-8")
    try:
        resolve_deeplabcut_config(project)
    except ValueError as exc:
        assert "multiple DeepLabCut projects" in str(exc)
    else:
        raise AssertionError("Expected an ambiguous model folder to be rejected")


def test_deeplabcut_bridge_separates_analyzed_data_and_labeled_videos(
    tmp_path,
    monkeypatch,
):
    video = tmp_path / "mouse.mp4"
    video.write_bytes(b"video")
    analysis_folder = tmp_path / "run" / "analyzed_videos" / "Bottom"
    labeled_folder = tmp_path / "run" / "labeled_videos" / "Bottom"
    result_path = tmp_path / "result.json"
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(
            {
                "operation": "analyze",
                "jobs": [
                    {
                        "region": "Bottom",
                        "config_path": str(tmp_path / "config.yaml"),
                        "video_paths": [str(video)],
                        "analysis_folder": str(analysis_folder),
                    }
                ],
                "result_path": str(result_path),
            }
        ),
        encoding="utf-8",
    )

    def fake_analyze(_config, videos, destfolder, save_as_csv):
        assert save_as_csv is True
        destination = Path(destfolder)
        for source in videos:
            stem = Path(source).stem
            (destination / f"{stem}DLC_fixture.csv").write_text("csv", encoding="utf-8")
            (destination / f"{stem}DLC_fixture.h5").write_bytes(b"h5")

    def fake_create_labeled(_config, videos, destfolder):
        destination = Path(destfolder)
        for source in videos:
            (destination / f"{Path(source).stem}DLC_fixture_labeled.mp4").write_bytes(
                b"labeled"
            )

    fake_deeplabcut = SimpleNamespace(
        analyze_videos=fake_analyze,
        create_labeled_video=fake_create_labeled,
    )
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "deeplabcut", fake_deeplabcut)

    _run_request(request_path)

    analyzed = json.loads(result_path.read_text(encoding="utf-8"))["results"][0]
    assert len(analyzed["csv_paths"]) == 1
    assert len(analyzed["h5_paths"]) == 1
    assert analyzed["labeled_video_paths"] == []
    assert Path(analyzed["csv_paths"][0]).parent == analysis_folder

    request_path.write_text(
        json.dumps(
            {
                "operation": "create_labeled_videos",
                "jobs": [
                    {
                        "region": "Bottom",
                        "config_path": str(tmp_path / "config.yaml"),
                        "video_paths": [str(video)],
                        "analysis_folder": str(analysis_folder),
                        "labeled_videos_folder": str(labeled_folder),
                        "csv_paths": analyzed["csv_paths"],
                        "h5_paths": analyzed["h5_paths"],
                    }
                ],
                "result_path": str(result_path),
            }
        ),
        encoding="utf-8",
    )
    _run_request(request_path)

    labeled = json.loads(result_path.read_text(encoding="utf-8"))["results"][0]
    assert len(labeled["labeled_video_paths"]) == 1
    assert Path(labeled["labeled_video_paths"][0]).parent == labeled_folder
    assert not list(analysis_folder.glob("*_labeled.mp4"))


def test_deeplabcut_project_validation_accepts_snapshot_selection(tmp_path):
    project = tmp_path / "model"
    train = project / "dlc-models-pytorch" / "iteration-0" / "run" / "train"
    train.mkdir(parents=True)
    config = project / "config.yaml"
    config.write_text(
        "Task: fixture\ndate: Jan1\niteration: 0\nTrainingFraction: [0.95]\n",
        encoding="utf-8",
    )
    (train / "pytorch_config.yaml").write_text("model: fixture\n", encoding="utf-8")
    snapshot = train / "snapshot-10.pt"
    snapshot.write_text("weights", encoding="utf-8")
    metadata = (
        project
        / "training-datasets"
        / "iteration-0"
        / "UnaugmentedDataSet_fixtureJan1"
        / "metadata.yaml"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "shuffles:\n  fixture-trainset95shuffle1:\n"
        "    train_fraction: 0.95\n    index: 1\n    engine: pytorch\n",
        encoding="utf-8",
    )

    assert validate_deeplabcut_project(snapshot) == config


def test_deeplabcut_project_validation_rejects_config_without_trained_model(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("Task: fixture\n", encoding="utf-8")

    try:
        validate_deeplabcut_project(config)
    except FileNotFoundError as exc:
        assert "no complete trained model" in str(exc)
    else:
        raise AssertionError("Expected an incomplete DeepLabCut project to be rejected")


def test_deeplabcut_project_validation_rejects_empty_shuffle_metadata(tmp_path):
    project = tmp_path / "model"
    train = project / "dlc-models-pytorch" / "iteration-0" / "run" / "train"
    train.mkdir(parents=True)
    config = project / "config.yaml"
    config.write_text(
        "Task: fixture\ndate: Jan1\niteration: 0\nTrainingFraction: [0.95]\n",
        encoding="utf-8",
    )
    (train / "pytorch_config.yaml").write_text("model: fixture\n", encoding="utf-8")
    (train / "snapshot-10.pt").write_text("weights", encoding="utf-8")
    metadata = (
        project
        / "training-datasets"
        / "iteration-0"
        / "UnaugmentedDataSet_fixtureJan1"
        / "metadata.yaml"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_text("shuffles: {}\n", encoding="utf-8")

    try:
        validate_deeplabcut_project(project)
    except ValueError as exc:
        assert "does not define shuffle 1" in str(exc)
    else:
        raise AssertionError("Expected empty shuffle metadata to be rejected")


def test_deeplabcut_project_validation_rejects_wrong_shuffle_metadata(tmp_path):
    project = tmp_path / "model"
    train = project / "dlc-models-pytorch" / "iteration-0" / "run" / "train"
    train.mkdir(parents=True)
    config = project / "config.yaml"
    config.write_text(
        "Task: fixture\ndate: Jan1\niteration: 0\nTrainingFraction: [0.95]\n",
        encoding="utf-8",
    )
    (train / "pytorch_config.yaml").write_text("model: fixture\n", encoding="utf-8")
    (train / "snapshot-10.pt").write_text("weights", encoding="utf-8")
    metadata = (
        project
        / "training-datasets"
        / "iteration-0"
        / "UnaugmentedDataSet_fixtureJan1"
        / "metadata.yaml"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "shuffles:\n  fixture-trainset95shuffle2:\n"
        "    train_fraction: 0.95\n    index: 2\n    engine: pytorch\n",
        encoding="utf-8",
    )

    try:
        validate_deeplabcut_project(project)
    except ValueError as exc:
        assert "does not define shuffle 1" in str(exc)
    else:
        raise AssertionError("Expected mismatched shuffle metadata to be rejected")


def test_deeplabcut_progress_parser_reports_analysis_and_label_rendering():
    analysis_updates = []
    parser = _DlcProgressParser(2, lambda current, total, message: analysis_updates.append(
        (current, total, message)
    ))

    parser.feed("Starting to analyze /videos/first.mp4\n")
    parser.feed(" 50%|#####     | 50/100 [00:01<00:01, 40.0it/s]\r")
    parser.feed("Starting to analyze /videos/second.mp4\n")
    parser.feed("100%|##########| 100/100 [00:02<00:00, 40.0it/s]\r")
    parser.finish()

    label_updates = []
    label_parser = _DlcProgressParser(
        2,
        lambda current, total, message: label_updates.append((current, total, message)),
        phase="labels",
    )
    label_parser.feed("Starting to process video: /videos/first.mp4\n")
    label_parser.feed(" 50%|#####     | 50/100 [00:01<00:01, 40.0it/s]\r")
    label_parser.feed("Starting to process video: /videos/second.mp4\n")
    label_parser.finish()

    assert [current for current, _total, _message in analysis_updates] == sorted(
        current for current, _total, _message in analysis_updates
    )
    assert analysis_updates[-1][0] == analysis_updates[-1][1] == 1000
    assert label_updates[-1][0] == label_updates[-1][1] == 1000
    assert any(
        "Analyzing video 1 of 2: first.mp4" in message
        for _, _, message in analysis_updates
    )
    assert any(
        "Creating labeled video 1 of 2" in message
        for _, _, message in label_updates
    )


def test_deeplabcut_progress_parser_combines_detector_and_pose_passes():
    updates = []
    parser = _DlcProgressParser(1, lambda current, total, message: updates.append(
        (current, total, message)
    ))

    parser.feed("Starting to analyze /videos/multianimal.mp4\n")
    parser.feed("Running detector with batch size 8\n")
    parser.feed("100%|##########| 100/100 [00:02<00:00, 40.0it/s]\r")
    detector_value = updates[-1][0]
    parser.feed("Running pose prediction with batch size 8\n")
    parser.feed("  0%|          | 0/100 [00:00<?, ?it/s]\r")
    parser.feed("100%|##########| 100/100 [00:02<00:00, 40.0it/s]\r")

    values = [current for current, _total, _message in updates]
    assert values == sorted(values)
    assert detector_value < updates[-1][0] == 1000


def test_three_view_knee_stage_leaves_bottom_coordinates_unchanged(tmp_path, monkeypatch):
    dlc_results = []
    for region in ("Left hindlimb", "Right hindlimb", "Bottom view"):
        slug = region.split()[0].lower()
        video = tmp_path / f"mouse_{slug}_processed.mp4"
        csv_path = tmp_path / f"{video.stem}DLC_fixture.csv"
        h5_path = tmp_path / f"{video.stem}DLC_fixture.h5"
        csv_path.write_text(f"raw {region}", encoding="utf-8")
        h5_path.write_bytes(f"raw {region}".encode())
        dlc_results.append(
            DlcAnalysisResult(region, (video,), (csv_path,), (h5_path,), ())
        )

    run = automated.AutomatedPipelineRun.__new__(automated.AutomatedPipelineRun)
    run.profile = SimpleNamespace(knee_manifest=tmp_path / "knee.json")
    run.output_folder = tmp_path / "run"
    run.dlc_results = dlc_results
    run.analysis_csvs_by_region = {}
    corrected_regions = []

    monkeypatch.setattr(automated_run, "knee_settings_from_manifest", lambda _path: object())

    def fake_correct(pair, output_folder, settings):
        corrected_regions.append(Path(output_folder).name)
        output_csv = Path(output_folder) / f"{pair.stem}_knee_corrected.csv"
        output_h5 = Path(output_folder) / f"{pair.stem}_knee_corrected.h5"
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        output_csv.write_text(f"corrected {pair.stem}", encoding="utf-8")
        output_h5.write_bytes(f"corrected {pair.stem}".encode())
        return SimpleNamespace(output_csv=output_csv, output_h5=output_h5)

    monkeypatch.setattr(automated_run, "correct_knee_pair", fake_correct)

    run._correct_knees(None)

    assert len(corrected_regions) == 2
    for result in dlc_results[:2]:
        assert result.csv_paths[0].read_text(encoding="utf-8").startswith("corrected")
        assert result.h5_paths[0].read_bytes().startswith(b"corrected")
    assert run.analysis_csvs_by_region["Bottom view"] == list(
        dlc_results[2].csv_paths
    )
    assert dlc_results[2].csv_paths[0].read_text(encoding="utf-8") == "raw Bottom view"
    assert dlc_results[2].h5_paths[0].read_bytes() == b"raw Bottom view"
    assert (run.output_folder / "03_knee_correction" / "correction_manifest.json").is_file()


def test_knee_and_gait_stages_can_be_independently_disabled(tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture")
    processing_manifest = write_video_settings_manifest(
        tmp_path / "video.json",
        ProcessingOptions(),
    )
    profile = AutomatedPipelineProfile(
        id="b" * 32,
        name="Selective run",
        processing_manifest=processing_manifest,
        calibration_map=tmp_path / "calibration.json",
        deeplabcut_models={"Full frame": tmp_path / "model"},
        analysis_manifest=tmp_path / "analysis.json",
        knee_manifest=tmp_path / "knee.json",
    )
    run = automated.AutomatedPipelineRun(
        profile,
        [video],
        tmp_path,
        tmp_path / "runs",
        enable_knee_correction=False,
        enable_gait_analysis=False,
    )
    monkeypatch.setattr(
        run,
        "_correct_knees",
        lambda _callback: (_ for _ in ()).throw(AssertionError("knee stage ran")),
    )
    monkeypatch.setattr(
        run,
        "_run_gait_analysis",
        lambda _callback: (_ for _ in ()).throw(AssertionError("gait stage ran")),
    )
    messages = []

    run.run_stage(2, lambda current, total, message: messages.append(message))
    run.run_stage(4, lambda current, total, message: messages.append(message))

    assert run.stage_enabled(2) is False
    assert run.stage_enabled(4) is False
    assert messages == [
        "Knee correction disabled for this run; skipped",
        "Gait analysis disabled for this run; skipped",
    ]


def test_profile_without_analysis_assets_skips_stickplot_and_gait_stages(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture")
    processing_manifest = write_video_settings_manifest(
        tmp_path / "video.json",
        ProcessingOptions(),
    )
    profile = AutomatedPipelineProfile(
        id="c" * 32,
        name="Tracking only",
        processing_manifest=processing_manifest,
        calibration_map=None,
        deeplabcut_models={"Full frame": tmp_path / "model"},
        gait_analysis_enabled=False,
        knee_correction_enabled=False,
    )

    run = automated.AutomatedPipelineRun(
        profile,
        [video],
        tmp_path,
        tmp_path / "runs",
    )

    assert run.stage_enabled(3) is True
    assert run.stage_enabled(4) is False
    assert run.stage_enabled(5) is False
    assert run.stage_skip_reason(4) == "Gait analysis excluded from this profile"


def test_pipeline_run_rejects_incomplete_inputs_before_creating_outputs(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture")
    incomplete = AutomatedPipelineProfile(
        id="d" * 32,
        name="Incomplete",
        processing_manifest=None,
        calibration_map=None,
        deeplabcut_models={},
        gait_analysis_enabled=False,
    )

    with pytest.raises(ValueError, match="video settings manifest"):
        automated.AutomatedPipelineRun(incomplete, [video], tmp_path, tmp_path / "runs")

    stale = AutomatedPipelineProfile(
        id="0" * 32,
        name="Stale manifest",
        processing_manifest=tmp_path / "missing-video.json",
        calibration_map=None,
        deeplabcut_models={},
        gait_analysis_enabled=False,
    )
    with pytest.raises(FileNotFoundError, match="Video settings manifest no longer exists"):
        automated.AutomatedPipelineRun(stale, [video], tmp_path, tmp_path / "runs")

    profile = AutomatedPipelineProfile(
        id="e" * 32,
        name="Duplicate sources",
        processing_manifest=tmp_path / "video.json",
        calibration_map=None,
        deeplabcut_models={"Full frame": tmp_path / "model"},
        gait_analysis_enabled=False,
    )
    with pytest.raises(ValueError, match="only be added"):
        automated.AutomatedPipelineRun(profile, [video, video], tmp_path, tmp_path / "runs")

    assert not (tmp_path / "runs").exists()


def test_pipeline_run_rejects_out_of_order_and_repeated_stages(tmp_path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture")
    manifest = write_video_settings_manifest(
        tmp_path / "video.json",
        ProcessingOptions(),
    )
    profile = AutomatedPipelineProfile(
        id="f" * 32,
        name="Stage ordering",
        processing_manifest=manifest,
        calibration_map=None,
        deeplabcut_models={"Full frame": tmp_path / "model"},
        gait_analysis_enabled=False,
    )
    run = automated.AutomatedPipelineRun(profile, [video], tmp_path, tmp_path / "runs")

    with pytest.raises(RuntimeError, match="Video Processing before Deeplabcut Analysis"):
        run.run_stage(1)

    run._completed_stages.add(automated.AutomatedStage.VIDEO_PROCESSING)
    with pytest.raises(RuntimeError, match="already run"):
        run.run_stage(0)


def test_pipeline_rejects_deeplabcut_results_for_the_wrong_region(tmp_path, monkeypatch):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture")
    manifest = write_video_settings_manifest(tmp_path / "video.json", ProcessingOptions())
    profile = AutomatedPipelineProfile(
        id="1" * 32,
        name="DLC validation",
        processing_manifest=manifest,
        calibration_map=None,
        deeplabcut_models={"Full frame": tmp_path / "model"},
        gait_analysis_enabled=False,
    )
    run = automated.AutomatedPipelineRun(profile, [video], tmp_path, tmp_path / "runs")
    processed = tmp_path / "source_processed.mp4"
    processed.write_bytes(b"video")
    run.processed_by_region = {"Full frame": [processed]}

    monkeypatch.setattr(
        automated_run,
        "run_deeplabcut_analysis",
        lambda *_args, **_kwargs: [
            DlcAnalysisResult("Wrong view", (processed,), (), (), ())
        ],
    )

    with pytest.raises(RuntimeError, match="do not match the configured regions"):
        run._run_deeplabcut(None)


def test_multiview_csvs_follow_processed_video_order_instead_of_filename_sort(tmp_path):
    run = automated.AutomatedPipelineRun.__new__(automated.AutomatedPipelineRun)
    run.analysis_csvs_by_region = {}
    run.dlc_jobs = []
    for region in ("Left view", "Right view", "Bottom view"):
        slug = region.split()[0]
        videos = (
            tmp_path / f"zeta_processed_{slug}.mp4",
            tmp_path / f"alpha_processed_{slug}.mp4",
        )
        csvs = []
        for video in reversed(videos):
            csv_path = tmp_path / f"{video.stem}DLC_fixture.csv"
            csv_path.write_text("coordinates", encoding="utf-8")
            csvs.append(csv_path)
        run.dlc_jobs.append(DlcAnalysisJob(region, tmp_path / "model", videos))
        run.analysis_csvs_by_region[region] = csvs

    inputs = run._alma_inputs("Multi side view")

    assert [item.name for item in inputs] == [
        "zeta_processed_Left",
        "alpha_processed_Left",
    ]
    assert inputs[0].left_csv.name.startswith("zeta_processed_Left")
    assert inputs[0].right_csv.name.startswith("zeta_processed_Right")
    assert inputs[0].bottom_csv.name.startswith("zeta_processed_Bottom")


def test_knee_correction_preparation_failure_leaves_all_coordinates_unchanged(
    tmp_path,
    monkeypatch,
):
    videos = (tmp_path / "first_processed.mp4", tmp_path / "second_processed.mp4")
    csvs = tuple(tmp_path / f"{video.stem}DLC_fixture.csv" for video in videos)
    h5s = tuple(tmp_path / f"{video.stem}DLC_fixture.h5" for video in videos)
    for index, (csv_path, h5_path) in enumerate(zip(csvs, h5s, strict=True), start=1):
        csv_path.write_text(f"original csv {index}", encoding="utf-8")
        h5_path.write_bytes(f"original h5 {index}".encode())

    run = automated.AutomatedPipelineRun.__new__(automated.AutomatedPipelineRun)
    run.profile = SimpleNamespace(knee_manifest=tmp_path / "knee.json")
    run.output_folder = tmp_path / "run"
    run.knee_correction_folder = run.output_folder / "03_knee_correction"
    run.dlc_results = [
        DlcAnalysisResult("Side view", videos, csvs, h5s, ())
    ]
    run.analysis_csvs_by_region = {"Side view": list(csvs)}
    monkeypatch.setattr(automated_run, "knee_settings_from_manifest", lambda _path: object())
    calls = 0

    def fail_second_pair(pair, output_folder, _settings):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated correction failure")
        output_folder.mkdir(parents=True, exist_ok=True)
        output_csv = output_folder / f"{pair.stem}.csv"
        output_h5 = output_folder / f"{pair.stem}.h5"
        output_csv.write_text("corrected csv", encoding="utf-8")
        output_h5.write_bytes(b"corrected h5")
        return SimpleNamespace(output_csv=output_csv, output_h5=output_h5)

    monkeypatch.setattr(automated_run, "correct_knee_pair", fail_second_pair)

    with pytest.raises(RuntimeError, match="simulated correction failure"):
        run._correct_knees(None)

    assert [path.read_text(encoding="utf-8") for path in csvs] == [
        "original csv 1",
        "original csv 2",
    ]
    assert [path.read_bytes() for path in h5s] == [b"original h5 1", b"original h5 2"]
    assert not (run.knee_correction_folder / "work").exists()
    assert not (run.knee_correction_folder / "correction_manifest.json").exists()
