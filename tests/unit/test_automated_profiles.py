from __future__ import annotations

import os
from pathlib import Path
import json

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog, QPushButton

from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.gui.shared.progress import CircularProgressIndicator
from dlc_gait_assembly.services.analysis_manifests import (
    write_analysis_manifest,
    write_knee_analysis_manifest,
)
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedProfileStore,
    regions_from_processing_manifest,
)
from dlc_gait_assembly.services.knee_correction import KneeCorrectionSettings
from dlc_gait_assembly.services.pipeline.alma import AlmaSettings


def _profile_sources(tmp_path: Path, suffix: str = "") -> dict:
    calibration = tmp_path / f"conversion_factor_map{suffix}.json"
    calibration.write_text(f'{{"calibration": "{suffix or "first"}"}}', encoding="utf-8")
    models = {}
    for region in ("Front", "Rear"):
        model = tmp_path / f"model_{region.lower()}{suffix}"
        model.mkdir()
        (model / "config.yaml").write_text(
            "Task: fixture\ndate: Jan1\niteration: 0\nTrainingFraction: [0.95]\n",
            encoding="utf-8",
        )
        train_folder = (
            model
            / "dlc-models-pytorch"
            / "iteration-0"
            / "fixture-trainset95shuffle1"
            / "train"
        )
        train_folder.mkdir(parents=True)
        (train_folder / "pytorch_config.yaml").write_text("model: fixture\n", encoding="utf-8")
        (train_folder / "snapshot-1.pt").write_text(
            f"weights-{region.lower()}-{suffix or 'first'}",
            encoding="utf-8",
        )
        metadata_folder = (
            model
            / "training-datasets"
            / "iteration-0"
            / "UnaugmentedDataSet_fixtureJan1"
        )
        metadata_folder.mkdir(parents=True)
        (metadata_folder / "metadata.yaml").write_text(
            "shuffles:\n  fixture-trainset95shuffle1:\n"
            "    train_fraction: 0.95\n    index: 1\n    engine: pytorch\n",
            encoding="utf-8",
        )
        videos_folder = model / "videos"
        videos_folder.mkdir()
        (videos_folder / "training.mp4").write_text("not packaged", encoding="utf-8")
        models[region] = model
    manifest = tmp_path / f"processing_manifest{suffix}.json"
    manifest.write_text(
        json.dumps(
            {
                "operations": {
                    "crop_regions": [
                        {"name": "Front", "rect": {}},
                        {"name": "Rear", "rect": {}},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    analysis_manifest = write_analysis_manifest(
        tmp_path / f"analysis_manifest{suffix}.json",
        AlmaSettings(frame_rate=240.0),
    )
    knee_manifest = write_knee_analysis_manifest(
        tmp_path / f"knee_analysis_manifest{suffix}.json",
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.7,
            pixels_per_cm=42.0,
        ),
    )
    return {
        "analysis_manifest": analysis_manifest,
        "calibration_map": calibration,
        "deeplabcut_models": models,
        "knee_manifest": knee_manifest,
        "processing_manifest": manifest,
    }


def _save(store: AutomatedProfileStore, name: str, sources: dict, profile_id: str | None = None):
    return store.save(
        name,
        sources["processing_manifest"],
        sources["calibration_map"],
        sources["deeplabcut_models"],
        profile_id,
        analysis_manifest=sources["analysis_manifest"],
        knee_manifest=sources["knee_manifest"],
    )


def test_profile_store_copies_replaces_and_deletes_owned_assets(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    first_sources = _profile_sources(tmp_path)

    profile = _save(store, "Mouse treadmill", first_sources)

    assert profile.name == "Mouse treadmill"
    assert profile.calibration_map.read_text(encoding="utf-8") == '{"calibration": "first"}'
    stored_weights = next(profile.deeplabcut_models["Front"].rglob("snapshot-1.pt"))
    assert stored_weights.read_text(
        encoding="utf-8"
    ) == "weights-front-first"
    assert next(profile.deeplabcut_models["Front"].rglob("metadata.yaml")).is_file()
    assert not (profile.deeplabcut_models["Front"] / "videos").exists()
    assert set(profile.deeplabcut_models) == {"Front", "Rear"}
    assert profile.processing_manifest.name == "processing_manifest.json"
    assert profile.analysis_manifest is not None
    assert profile.analysis_manifest.name == "analysis_manifest.json"
    assert profile.knee_manifest is not None
    assert profile.knee_manifest.name == "knee_analysis_manifest.json"
    assert first_sources["calibration_map"].exists()
    assert all(path.exists() for path in first_sources["deeplabcut_models"].values())
    assert [saved.id for saved in store.list_profiles()] == [profile.id]

    replacement_sources = _profile_sources(tmp_path, "_new")
    replacement = _save(store, "Mouse treadmill updated", replacement_sources, profile.id)

    assert replacement.id == profile.id
    assert replacement.name == "Mouse treadmill updated"
    assert replacement.calibration_map.read_text(encoding="utf-8") == '{"calibration": "_new"}'
    assert not profile.calibration_map.exists()

    store.delete(profile.id)
    assert store.list_profiles() == []


def test_profile_store_packages_complete_project_when_config_file_is_selected(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    sources = _profile_sources(tmp_path)
    sources["deeplabcut_models"] = {
        region: model / "config.yaml"
        for region, model in sources["deeplabcut_models"].items()
    }

    profile = _save(store, "Config selections", sources)

    for stored_project in profile.deeplabcut_models.values():
        assert (stored_project / "config.yaml").is_file()
        assert next(stored_project.rglob("pytorch_config.yaml")).is_file()
        assert next(stored_project.rglob("snapshot-1.pt")).is_file()
        assert next(stored_project.rglob("metadata.yaml")).is_file()


def test_profile_store_rejects_duplicate_names(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    _save(store, "Treadmill", _profile_sources(tmp_path))

    with pytest.raises(ValueError, match="already exists"):
        _save(store, "treadmill", _profile_sources(tmp_path, "_other"))


def test_profile_store_rolls_back_failed_transactional_replacement(tmp_path, monkeypatch):
    store = AutomatedProfileStore(tmp_path / "profiles")
    original = _save(store, "Original profile", _profile_sources(tmp_path))
    original_rename = Path.rename

    def fail_staging_install(path: Path, target: Path):
        if path.name.endswith(".staging"):
            raise OSError("simulated install failure")
        return original_rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_staging_install)

    with pytest.raises(OSError, match="simulated install failure"):
        _save(store, "Replacement profile", _profile_sources(tmp_path, "_replacement"), original.id)

    restored = store.load(original.id)
    assert restored.name == "Original profile"
    assert restored.calibration_map.read_text(encoding="utf-8") == '{"calibration": "first"}'
    assert not list(store.root.glob(".*.staging"))
    assert not list(store.root.glob(".*.backup"))


def test_profile_store_persists_video_and_dlc_only_profile(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    sources = _profile_sources(tmp_path)

    profile = store.save(
        "DLC only",
        sources["processing_manifest"],
        None,
        sources["deeplabcut_models"],
        gait_analysis_enabled=False,
        knee_correction_enabled=False,
    )
    reloaded = store.load(profile.id)

    assert reloaded.calibration_map is None
    assert reloaded.analysis_manifest is None
    assert reloaded.knee_manifest is None
    assert reloaded.gait_analysis_enabled is False
    assert reloaded.knee_correction_enabled is False


def test_manifest_regions_define_ordered_model_requirements(tmp_path):
    sources = _profile_sources(tmp_path)

    assert regions_from_processing_manifest(sources["processing_manifest"]) == ("Front", "Rear")


def test_profile_widget_requires_confirmation_before_replace_or_delete(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = AutomatedProfileStore(tmp_path / "profiles")
    widget = AutomatedPipelineProfilesWidget(store)
    first_sources = _profile_sources(tmp_path)
    widget.profile_name.setText("Mouse treadmill")
    assert widget._set_manifest_source(first_sources["processing_manifest"])
    for region, path in first_sources["deeplabcut_models"].items():
        widget._set_model_source(region, path)
    widget._calibration_source = first_sources["calibration_map"]
    assert widget._set_analysis_manifest_source(first_sources["analysis_manifest"])
    assert widget._set_knee_manifest_source(first_sources["knee_manifest"])
    widget._refresh_paths()
    widget._save_profile()
    profile_id = widget._current_profile_id
    assert profile_id is not None

    replacement_sources = _profile_sources(tmp_path, "_new")
    widget._calibration_source = replacement_sources["calibration_map"]
    widget._refresh_paths()
    monkeypatch.setattr(widget, "_confirm_replace_profile", lambda _name: False)
    widget._save_profile()
    assert store.load(profile_id).calibration_map.read_text(encoding="utf-8") == '{"calibration": "first"}'

    monkeypatch.setattr(widget, "_confirm_replace_profile", lambda _name: True)
    widget._save_profile()
    assert store.load(profile_id).calibration_map.read_text(encoding="utf-8") == '{"calibration": "_new"}'

    monkeypatch.setattr(widget, "_confirm_delete_profile", lambda _name: False)
    widget._delete_profile()
    assert store.load(profile_id).name == "Mouse treadmill"

    monkeypatch.setattr(widget, "_confirm_delete_profile", lambda _name: True)
    widget._delete_profile()
    assert store.list_profiles() == []
    widget.close()
    app.processEvents()


def test_automation_menu_collects_supported_videos_without_running_pipeline(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AutomatedPipelineProfilesWidget(AutomatedProfileStore(tmp_path / "profiles"))
    first_video = tmp_path / "first.mp4"
    second_video = tmp_path / "second.avi"
    unsupported = tmp_path / "notes.txt"
    for path in (first_video, second_video, unsupported):
        path.write_bytes(b"fixture")

    widget._add_video_paths([first_video, second_video, unsupported, first_video])

    assert widget.video_list.count() == 2
    assert widget.video_count_label.text() == "2 videos"
    assert widget.video_hover_card.isHidden()
    assert widget.run_pipeline_button.isEnabled()
    assert "Added 2 video(s)" in widget.automation_console.toPlainText()
    widget.video_list.item(0).setSelected(True)
    widget._remove_selected_videos()
    assert widget.video_list.count() == 1
    widget.close()
    app.processEvents()


def test_large_video_preview_opens_with_seek_slider(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AutomatedPipelineProfilesWidget(AutomatedProfileStore(tmp_path / "profiles"))
    video = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "video"
        / "2019_09_19_RW_DRUGS_23.2099782.20190919151537.mp4"
    )
    widget._add_video_paths([video])

    item = widget.video_list.item(0)
    widget._start_hover_preview(item)
    assert widget._hover_preview_timer.isActive()
    assert not widget.video_hover_card.isHidden()
    assert widget.video_hover_name.text().endswith(".mp4")
    assert "fps" in widget.video_hover_details.text()
    assert not widget.video_hover_preview.pixmap().isNull()
    widget._stop_hover_preview()
    assert not widget._hover_preview_timer.isActive()
    assert widget.video_hover_card.isHidden()

    widget.video_list.itemDoubleClicked.emit(item)
    dialog = widget._large_preview_dialog

    assert dialog is not None
    assert dialog.frame_slider.maximum() > 0
    assert not dialog.preview.pixmap().isNull()
    dialog.frame_slider.setValue(dialog.frame_slider.maximum() // 2)
    assert "/" in dialog.frame_label.text()
    dialog.close()

    widget._pipeline_demo_total_videos = 1
    widget._populate_pipeline_review_preview(0)
    review_item = widget.pipeline_review_video_list.item(0)
    widget.pipeline_review_video_list.itemDoubleClicked.emit(review_item)
    review_dialog = widget._large_review_dialog
    assert review_dialog is not None
    assert review_dialog.frame_slider.maximum() > 0
    review_dialog.close()
    widget.close()
    app.processEvents()


def test_pipeline_progress_replaces_video_queue_while_running(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AutomatedPipelineProfilesWidget(AutomatedProfileStore(tmp_path / "profiles"))
    videos = [tmp_path / "first.mp4", tmp_path / "second.mp4"]
    for video in videos:
        video.write_bytes(b"fixture")
    widget._add_video_paths(videos)

    assert widget.automation_input_stack.currentWidget() is widget.video_panel

    widget.set_pipeline_running(True)

    assert widget.automation_input_stack.currentWidget() is widget.pipeline_status_panel
    assert widget.pipeline_stage_cards[0].property("pipelineState") == "active"
    assert len(widget.pipeline_stage_progress_bars) == len(widget.pipeline_stage_cards)
    assert all(
        isinstance(bar, CircularProgressIndicator)
        for bar in widget.pipeline_stage_progress_bars
    )
    assert widget.pipeline_stage_progress_bars[0].value() == 0
    assert widget.pipeline_video_progress_label.text() == "0 / 2 videos processed"
    output_folder = tmp_path / "automated_run"
    output_folder.mkdir()
    widget._pipeline_output_folder_ready(output_folder)
    assert not widget.open_pipeline_output_button.isHidden()
    assert widget.open_pipeline_output_button.toolTip() == str(output_folder.resolve())

    widget.set_pipeline_stage(
        1,
        progress=50,
        processed_videos=2,
        total_videos=2,
        status_text="Analyzing poses",
    )

    assert widget.pipeline_stage_cards[0].property("pipelineState") == "complete"
    assert widget.pipeline_stage_cards[1].property("pipelineState") == "active"
    assert widget.pipeline_stage_status_labels[1].text() == "Analyzing poses 50%"
    assert widget.pipeline_stage_progress_bars[0].value() == 100
    assert widget.pipeline_stage_progress_bars[1].value() == 50
    assert widget.pipeline_progress_bar.value() == 25
    assert widget.pipeline_video_progress_label.text() == "2 / 2 videos processed"

    detail = "Analyzing video 1 of 2: a_very_long_deeplabcut_video_name.mp4"
    widget._pipeline_stage_progressed(1, 425, 1000, detail)
    assert widget.pipeline_stage_status_labels[1].text() == "Analyzing video 1 of 2 42.5%"
    assert widget.pipeline_current_stage_label.text() == detail

    widget.complete_pipeline()
    assert widget.pipeline_progress_bar.value() == 100
    assert all(
        card.property("pipelineState") == "complete"
        for card in widget.pipeline_stage_cards
    )
    assert all(bar.value() == 100 for bar in widget.pipeline_stage_progress_bars)
    widget.set_pipeline_running(False)
    assert widget.automation_input_stack.currentWidget() is widget.video_panel
    widget.close()
    app.processEvents()


def test_run_button_plays_pipeline_ui_without_processing(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AutomatedPipelineProfilesWidget(AutomatedProfileStore(tmp_path / "profiles"))
    widget._regions = ("Front", "Rear")
    widget._model_sources = {"Front": None, "Rear": None}

    widget.run_pipeline_button.click()
    assert widget._pipeline_demo_timer.isActive()
    assert widget.automation_input_stack.currentWidget() is widget.pipeline_status_panel
    assert widget.run_pipeline_button.text() == "Stop preview"
    widget._pipeline_demo_timer.stop()

    review_stages = []
    for _ in range(150):
        if widget._pipeline_demo_complete:
            break
        if widget._pipeline_demo_waiting_for_review is not None:
            review_stage = widget._pipeline_demo_waiting_for_review
            review_stages.append(review_stage)
            if review_stage == 0:
                item_text = widget.pipeline_review_video_list.item(0).text()
                assert "Regions:" in item_text
                assert "Enhancements:" in item_text
            elif review_stage == 3:
                assert widget.pipeline_component_tabs.count() == 2
                assert widget.pipeline_component_tabs.tabText(0) == "Front"
                assert widget.pipeline_component_tabs.tabText(1) == "Rear"
                assert "_DLC.mp4" in widget.pipeline_component_video_lists["Front"].item(0).text()
            elif review_stage == 4:
                assert widget.pipeline_review_preview_stack.currentWidget() is (
                    widget.pipeline_stickplot_preview
                )
                assert not widget.pipeline_stickplot_preview.pixmap().isNull()
                widget.pipeline_stickplot_preview.double_clicked.emit()
                assert widget._large_review_dialog is not None
                widget._large_review_dialog.close()
            widget._approve_pipeline_review()
        widget._advance_pipeline_demo()

    assert widget._pipeline_demo_complete
    assert review_stages == [0, 3, 4]
    assert widget.pipeline_progress_bar.value() == 100
    assert widget.run_pipeline_button.text() == "Back to videos"
    console = widget.automation_console.toPlainText()
    assert "DLC analyzing videos" in console
    assert "Stickplot generation" in console
    assert "No processing was performed" in console

    widget.run_pipeline_button.click()
    assert widget.automation_input_stack.currentWidget() is widget.video_panel
    assert widget.run_pipeline_button.text() == "Run pipeline"
    widget.close()
    app.processEvents()


def test_run_button_starts_real_pipeline_when_profile_and_videos_are_ready(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    store = AutomatedProfileStore(tmp_path / "profiles")
    profile = _save(store, "Ready profile", _profile_sources(tmp_path))
    widget = AutomatedPipelineProfilesWidget(store)
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fixture")
    widget._add_video_paths([video])
    started = []
    monkeypatch.setattr(widget, "_start_pipeline", lambda selected: started.append(selected))

    widget.run_pipeline_button.click()

    assert started == [profile]
    assert not widget._pipeline_demo_timer.isActive()
    widget.close()
    app.processEvents()


def test_run_controls_do_not_include_stage_skip_buttons(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AutomatedPipelineProfilesWidget(AutomatedProfileStore(tmp_path / "profiles"))

    assert not widget.findChildren(QPushButton, "PipelineOptionButton")
    assert widget.run_pipeline_button.isVisibleTo(widget)
    assert widget.open_pipeline_output_button.isVisibleTo(widget)
    widget.close()
    app.processEvents()


def test_profile_can_be_created_without_gait_or_knee_uploads(tmp_path):
    app = QApplication.instance() or QApplication([])
    store = AutomatedProfileStore(tmp_path / "profiles")
    sources = _profile_sources(tmp_path)
    widget = AutomatedPipelineProfilesWidget(store)
    widget.profile_name.setText("Tracking only")
    assert widget._set_manifest_source(sources["processing_manifest"])
    for region, path in sources["deeplabcut_models"].items():
        widget._set_model_source(region, path)
    widget.include_gait_analysis_button.setChecked(False)

    widget._save_profile()

    profile = store.load(widget._current_profile_id)
    assert profile.calibration_map is None
    assert profile.analysis_manifest is None
    assert profile.knee_manifest is None
    assert profile.gait_analysis_enabled is False
    assert profile.knee_correction_enabled is False
    assert widget.profile_readiness_values["calibration"].text() == "Excluded"
    assert widget.profile_readiness_values["analysis"].text() == "Excluded"
    assert widget.profile_readiness_values["knee"].text() == "Excluded"
    widget.close()
    app.processEvents()


def test_rejected_pipeline_check_opens_correct_settings_and_rechecks_on_resume(tmp_path):
    app = QApplication.instance() or QApplication([])
    widget = AutomatedPipelineProfilesWidget(AutomatedProfileStore(tmp_path / "profiles"))
    widget.run_pipeline_button.click()
    widget._pipeline_demo_timer.stop()

    for _ in range(40):
        widget._advance_pipeline_demo()
        if widget._pipeline_demo_waiting_for_review is not None:
            break

    assert widget._pipeline_demo_waiting_for_review == 0
    assert widget.pipeline_review_title.text() == "Review processed videos"
    assert not widget.pipeline_review_panel.isHidden()
    assert widget.pipeline_review_video_list.count() == 4
    assert "Regions:" in widget.pipeline_review_video_list.item(0).text()
    assert not widget.run_pipeline_button.isEnabled()

    widget._reject_pipeline_review()
    assert widget._pipeline_demo_blocked_stage == 0
    assert widget.pipeline_stage_cards[0].property("pipelineState") == "blocked"
    assert widget.pipeline_stage_progress_bars[0].value() == 100
    assert widget.run_pipeline_button.text() == "Resume preview"

    widget.pipeline_change_settings_button.click()
    assert widget.workspace_stack.currentWidget() is widget.configuration_page
    assert widget.configuration_tabs.currentIndex() == 0
    widget.back_to_automation_button.click()
    widget.run_pipeline_button.click()
    assert widget._pipeline_demo_stage == 0
    assert widget._pipeline_demo_timer.isActive()
    widget._pipeline_demo_timer.stop()

    for _ in range(40):
        widget._advance_pipeline_demo()
        if widget._pipeline_demo_waiting_for_review is not None:
            break

    assert widget._pipeline_demo_waiting_for_review == 0
    assert "Replaying Video processing" in widget.automation_console.toPlainText()
    widget.close()
    app.processEvents()


def test_selected_profile_can_be_duplicated_under_a_new_name(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = AutomatedProfileStore(tmp_path / "profiles")
    _save(store, "Original", _profile_sources(tmp_path))
    widget = AutomatedPipelineProfilesWidget(store)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args: ("Original copy", True))

    widget._duplicate_profile()

    assert [profile.name for profile in store.list_profiles()] == ["Original", "Original copy"]
    assert widget.profile_name.text() == "Original copy"
    widget.close()
    app.processEvents()
