"""Verify preservation, schema-aware rewriting, collisions, interruption, and rollback."""

import json
from pathlib import Path
import pytest
from dlc_gait_assembly.maintenance.migration_collision_policy import plan_migration
from dlc_gait_assembly.maintenance.migration_executor import apply_migration
from dlc_gait_assembly.maintenance.migration_inventory import file_digest, inventory_outputs
from dlc_gait_assembly.maintenance.migration_rollback import rollback_migration


def put(root, relative, contents):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
    return path


def plan(root):
    return plan_migration(inventory_outputs(root), root, root / "workspace")


def test_pairs_collisions_references_resume_and_rollback(tmp_path):
    source = put(tmp_path, "outputs/manual_pipeline/processed_videos/legacy_migrated/recording.mp4", b"media")
    coordinates = put(
        tmp_path, "outputs/manual_pipeline/gait_analysis/legacy_migrated/recording.csv", b"frame,x\n0,1\n"
    )
    h5 = put(tmp_path, "outputs/manual_pipeline/gait_analysis/legacy_migrated/recording.h5", b"opaque-h5-bytes")
    manifest = put(
        tmp_path,
        "outputs/manual_pipeline/gait_analysis/legacy_migrated/analysis_manifest.json",
        json.dumps(
            {
                "files": [{"input": str(source), "outputs": [str(coordinates)]}],
                "external_input": "/external/recording.mp4",
                "description": str(source),
            }
        ),
    )
    existing = put(tmp_path, "workspace/runway/manual/gait_analysis/recording.csv", b"existing")
    originals = {path: path.read_bytes() for path in (source, coordinates, h5, manifest)}
    migration = plan(tmp_path)
    assert migration.collisions
    destinations = {Path(move.source): Path(move.destination) for move in migration.moves}
    assert destinations[coordinates].parent == destinations[h5].parent == destinations[manifest].parent
    assert "legacy_migrated" not in str(destinations[h5])
    journal = tmp_path / "workspace/migrations/journal.json"

    def interrupt(index, move):
        if index == 1:
            raise InterruptedError("test interruption")

    with pytest.raises(InterruptedError):
        apply_migration(migration, journal, after_operation=interrupt)
    result = apply_migration(migration, journal)
    assert result["status"] == "complete"
    assert apply_migration(migration, journal)["status"] == "complete"
    payload = json.loads(destinations[manifest].read_text())
    assert payload["files"][0]["input"] == str(destinations[source])
    assert payload["files"][0]["outputs"] == [str(destinations[coordinates])]
    assert payload["external_input"] == "/external/recording.mp4"
    assert payload["description"] == str(source)
    assert destinations[h5].read_bytes() == originals[h5]
    assert existing.read_bytes() == b"existing"
    rollback_migration(journal)
    for path, content in originals.items():
        assert path.read_bytes() == content
    assert existing.read_bytes() == b"existing"
    assert rollback_migration(journal)["status"] == "rolled_back"


def test_changed_source_or_destination_is_never_overwritten(tmp_path):
    source = put(tmp_path, "outputs/calibration/session/map.json", "{}")
    migration = plan(tmp_path)
    source.write_text("changed")
    with pytest.raises(RuntimeError, match="changed since inventory"):
        apply_migration(migration, tmp_path / "journal.json")
    assert source.read_text() == "changed"


def test_rollback_preflights_all_files_before_changing_any(tmp_path):
    first = put(tmp_path, "outputs/calibration/a.json", "{}")
    second = put(tmp_path, "outputs/calibration/b.json", "{}")
    migration = plan(tmp_path)
    journal = tmp_path / "journal.json"
    apply_migration(migration, journal)
    target = Path(migration.moves[1].destination)
    target.write_text("user edit")
    with pytest.raises(RuntimeError, match="subsequently changed"):
        rollback_migration(journal)
    assert not first.exists() and (not second.exists())
    assert target.read_text() == "user edit"


def test_divergent_profile_ids_preserve_both_profiles(tmp_path):
    profile = put(
        tmp_path,
        "outputs/automated_profiles/id123/profile.json",
        json.dumps({"format_version": 5, "id": "id123", "name": "old"}),
    )
    put(tmp_path, "outputs/automated_profiles/id123/processing_manifest/manifest.json", "{}")
    existing = put(
        tmp_path, "workspace/runway/automatic/profiles/id123/profile.json", json.dumps({"id": "id123", "name": "new"})
    )
    original_hash = file_digest(existing)
    migration = plan(tmp_path)
    assert len(migration.profile_id_remapping) == 1
    apply_migration(migration, tmp_path / "journal.json")
    target = next(Path(move.destination) for move in migration.moves if move.source == str(profile))
    assert json.loads(target.read_text())["id"] == target.parent.name != "id123"
    assert file_digest(existing) == original_hash


def test_an_empty_repeated_inventory_creates_no_moves(tmp_path):
    put(tmp_path, "outputs/ui-review/frame.png", b"png")
    migration = plan(tmp_path)
    apply_migration(migration, tmp_path / "journal.json")
    assert not plan(tmp_path).moves
