from __future__ import annotations

import os
from pathlib import Path
import json

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog

from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedProfileStore,
    regions_from_processing_manifest,
)


def _profile_sources(tmp_path: Path, suffix: str = "") -> dict:
    calibration = tmp_path / f"conversion_factor_map{suffix}.json"
    calibration.write_text(f'{{"calibration": "{suffix or "first"}"}}', encoding="utf-8")
    models = {}
    for region in ("Front", "Rear"):
        model = tmp_path / f"model_{region.lower()}{suffix}"
        model.mkdir()
        (model / "weights.h5").write_text(
            f"weights-{region.lower()}-{suffix or 'first'}",
            encoding="utf-8",
        )
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
    return {
        "calibration_map": calibration,
        "deeplabcut_models": models,
        "processing_manifest": manifest,
    }


def _save(store: AutomatedProfileStore, name: str, sources: dict, profile_id: str | None = None):
    return store.save(
        name,
        sources["processing_manifest"],
        sources["calibration_map"],
        sources["deeplabcut_models"],
        profile_id,
    )


def test_profile_store_copies_replaces_and_deletes_owned_assets(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    first_sources = _profile_sources(tmp_path)

    profile = _save(store, "Mouse treadmill", first_sources)

    assert profile.name == "Mouse treadmill"
    assert profile.calibration_map.read_text(encoding="utf-8") == '{"calibration": "first"}'
    assert (profile.deeplabcut_models["Front"] / "weights.h5").read_text(
        encoding="utf-8"
    ) == "weights-front-first"
    assert set(profile.deeplabcut_models) == {"Front", "Rear"}
    assert profile.processing_manifest.name == "processing_manifest.json"
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


def test_profile_store_rejects_duplicate_names(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    _save(store, "Treadmill", _profile_sources(tmp_path))

    with pytest.raises(ValueError, match="already exists"):
        _save(store, "treadmill", _profile_sources(tmp_path, "_other"))


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
    assert not widget.run_pipeline_button.isEnabled()
    assert "Added 2 video(s)" in widget.automation_console.toPlainText()
    widget.video_list.item(0).setSelected(True)
    widget._remove_selected_videos()
    assert widget.video_list.count() == 1
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
