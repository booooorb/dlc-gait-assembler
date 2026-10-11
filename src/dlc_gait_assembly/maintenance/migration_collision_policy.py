"""Allocate deterministic session destinations without overwriting or deduplicating files."""

import hashlib
from collections import defaultdict
from pathlib import Path, PurePosixPath

from dlc_gait_assembly.maintenance.migration_contracts import MigrationCollision, MigrationPlan, PlannedMove
from dlc_gait_assembly.maintenance.migration_path_mapping import owning_relative_path, recording_bundle


def plan_migration(entries, source_root, workspace_root):
    workspace = Path(workspace_root).resolve()
    grouped = defaultdict(list)
    for entry in entries:
        grouped[str(recording_bundle(entry.relative))].append(entry)
    reserved = set()
    (moves, collisions, remapping) = ([], [], {})
    for bundle, members in sorted(grouped.items()):
        destinations = [workspace / owning_relative_path(entry.relative) for entry in members]
        conflict = any(path in reserved or path.exists() or path.is_symlink() for path in destinations)
        if conflict:
            token = hashlib.sha256(bundle.encode()).hexdigest()[:12]
            is_profile = bundle.startswith("outputs/automated_profiles/")
            if is_profile:
                old_id = PurePosixPath(bundle).name
                new_id = f"{old_id}_{token}"
                root = workspace / "runway/automatic/profiles" / new_id
                while root.exists() or any(path.is_relative_to(root) for path in reserved):
                    new_id += "_2"
                    root = root.with_name(new_id)
                remapping[str(Path(source_root) / bundle)] = new_id
                destinations = [root / PurePosixPath(entry.relative).relative_to(bundle) for entry in members]
            else:
                base = workspace / owning_relative_path(str(PurePosixPath(bundle) / "_bundle_marker")).parent
                root = base / f"session_{token}"
                suffix = 2
                while root.exists() or any(path.is_relative_to(root) for path in reserved):
                    root = base / f"session_{token}_{suffix}"
                    suffix += 1
                destinations = [root / PurePosixPath(entry.relative).relative_to(bundle) for entry in members]
            collisions.append(
                MigrationCollision(bundle, str(workspace / owning_relative_path(members[0].relative)), str(root))
            )
        for entry, destination in zip(members, destinations, strict=True):
            if destination in reserved:
                raise ValueError(f"Ambiguous migration destination: {destination}")
            reserved.add(destination)
            moves.append(PlannedMove(entry.source, str(destination), entry.size, entry.sha256, entry.kind))
    return MigrationPlan(str(Path(source_root).resolve()), str(workspace), tuple(moves), tuple(collisions), remapping)
