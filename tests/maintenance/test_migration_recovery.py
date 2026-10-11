"""Resume metadata commits after interrupted backups and atomic replacements."""

import json
from pathlib import Path

import pytest

from dlc_gait_assembly.maintenance.migration_collision_policy import plan_migration
from dlc_gait_assembly.maintenance.migration_executor import apply_migration
from dlc_gait_assembly.maintenance.migration_inventory import inventory_outputs
from dlc_gait_assembly.maintenance.migration_rollback import rollback_migration


@pytest.mark.parametrize("partial_backup", [False, True])
def test_resume_metadata_write_preserves_original_and_external_paths(tmp_path, monkeypatch, partial_backup):
    source = tmp_path / "outputs/calibration/session/conversion.json"
    source.parent.mkdir(parents=True)
    original = json.dumps({"output_file": str(source), "source_video": "/external/input.mp4"}).encode()
    source.write_bytes(original)
    plan = plan_migration(inventory_outputs(tmp_path), tmp_path, tmp_path / "workspace")
    journal = tmp_path / "workspace/migrations/recovery.json"
    replace = Path.replace

    def crash(path, target):
        if path.name.endswith(".migration-writing"):
            raise InterruptedError("interrupted before metadata replacement")
        return replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", crash)
        with pytest.raises(InterruptedError):
            apply_migration(plan, journal)
    records = json.loads(journal.read_text())["metadata"]
    if partial_backup:
        Path(next(iter(records.values()))["backup"]).write_bytes(b"partial backup")
    assert apply_migration(plan, journal)["status"] == "complete"
    destination = Path(plan.moves[0].destination)
    assert json.loads(destination.read_text()) == {
        "output_file": str(destination),
        "source_video": "/external/input.mp4",
    }
    rollback_migration(journal)
    assert source.read_bytes() == original


@pytest.mark.parametrize("version", range(1, 6))
def test_migration_retains_profile_format_id_and_absolute_assets(tmp_path, version):
    root = tmp_path / "outputs/automated_profiles/id"
    root.mkdir(parents=True)
    asset = root / "calibration_map.json"
    asset.write_text("{}")
    profile = root / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "format_version": version,
                "id": "id",
                "calibration_map": str(asset),
                "deeplabcut_models": {"Left": "/external/dlc/config.yaml"},
            }
        )
    )
    plan = plan_migration(inventory_outputs(tmp_path), tmp_path, tmp_path / "workspace")
    apply_migration(plan, tmp_path / "workspace/migrations/profile.json")
    mapping = {move.source: move.destination for move in plan.moves}
    result = json.loads(Path(mapping[str(profile)]).read_text())
    assert result == {
        "format_version": version,
        "id": "id",
        "calibration_map": mapping[str(asset)],
        "deeplabcut_models": {"Left": "/external/dlc/config.yaml"},
    }


def test_cross_device_copy_interruption_can_resume_without_partial_destination(tmp_path, monkeypatch):
    import errno
    from dlc_gait_assembly.maintenance import migration_executor as executor

    source = tmp_path / "outputs/manual_pipeline/gait_analysis/recording.csv"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"preserved data\n" * 100)
    original = source.read_bytes()
    plan = plan_migration(inventory_outputs(tmp_path), tmp_path, tmp_path / "workspace")
    journal = tmp_path / "workspace/migrations/cross-device.json"
    destination = Path(plan.moves[0].destination)
    real_link = executor.os.link

    def cross_device(first, second):
        if Path(first) == source:
            raise OSError(errno.EXDEV, "cross-device test")
        return real_link(first, second)

    def interrupted_copy(incoming, outgoing, *args):
        outgoing.write(incoming.read(5))
        raise InterruptedError("partial transfer")

    monkeypatch.setattr(executor.os, "link", cross_device)
    with monkeypatch.context() as patch:
        patch.setattr(executor.shutil, "copyfileobj", interrupted_copy)
        with pytest.raises(InterruptedError):
            apply_migration(plan, journal)
    assert source.read_bytes() == original
    assert not destination.exists()
    assert apply_migration(plan, journal)["status"] == "complete"
    assert destination.read_bytes() == original
    assert not source.exists()
