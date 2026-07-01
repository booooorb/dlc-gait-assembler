from __future__ import annotations

import os
from pathlib import Path

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.gui.automated_pipeline import AutomatedPipelineProfilesWidget
from dlc_gait_assembly.services.automated_profiles import AutomatedProfileStore


def _profile_sources(tmp_path: Path, suffix: str = "") -> dict[str, Path]:
    calibration = tmp_path / f"conversion_factor_map{suffix}.json"
    calibration.write_text(f'{{"calibration": "{suffix or "first"}"}}', encoding="utf-8")
    model = tmp_path / f"model{suffix}"
    model.mkdir()
    (model / "weights.h5").write_text(f"weights-{suffix or 'first'}", encoding="utf-8")
    manifest = tmp_path / f"processing_manifest{suffix}.json"
    manifest.write_text(f'{{"manifest": "{suffix or "first"}"}}', encoding="utf-8")
    return {
        "calibration_map": calibration,
        "deeplabcut_model": model,
        "processing_manifest": manifest,
    }


def test_profile_store_copies_replaces_and_deletes_owned_assets(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    first_sources = _profile_sources(tmp_path)

    profile = store.save("Mouse treadmill", first_sources)

    assert profile.name == "Mouse treadmill"
    assert profile.calibration_map.read_text(encoding="utf-8") == '{"calibration": "first"}'
    assert (profile.deeplabcut_model / "weights.h5").read_text(encoding="utf-8") == "weights-first"
    assert profile.processing_manifest.name == "processing_manifest.json"
    assert all(path.exists() for path in first_sources.values())
    assert [saved.id for saved in store.list_profiles()] == [profile.id]

    replacement_sources = _profile_sources(tmp_path, "_new")
    replacement = store.save("Mouse treadmill updated", replacement_sources, profile.id)

    assert replacement.id == profile.id
    assert replacement.name == "Mouse treadmill updated"
    assert replacement.calibration_map.read_text(encoding="utf-8") == '{"calibration": "_new"}'
    assert not profile.calibration_map.exists()

    store.delete(profile.id)
    assert store.list_profiles() == []


def test_profile_store_rejects_duplicate_names(tmp_path):
    store = AutomatedProfileStore(tmp_path / "profiles")
    store.save("Treadmill", _profile_sources(tmp_path))

    with pytest.raises(ValueError, match="already exists"):
        store.save("treadmill", _profile_sources(tmp_path, "_other"))


def test_profile_widget_requires_confirmation_before_replace_or_delete(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    store = AutomatedProfileStore(tmp_path / "profiles")
    widget = AutomatedPipelineProfilesWidget(store)
    first_sources = _profile_sources(tmp_path)
    widget.profile_name.setText("Mouse treadmill")
    for key, path in first_sources.items():
        widget._set_asset_source(key, path)
    widget._save_profile()
    profile_id = widget._current_profile_id
    assert profile_id is not None

    replacement_sources = _profile_sources(tmp_path, "_new")
    widget._set_asset_source("calibration_map", replacement_sources["calibration_map"])
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
