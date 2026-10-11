"""Apply verified, non-overwriting moves and backed-up metadata rewrites with resumable journaling."""

import errno
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from dlc_gait_assembly.maintenance.migration_inventory import file_digest, verify_file
from dlc_gait_assembly.maintenance.migration_journal import open_journal, save_journal
from dlc_gait_assembly.maintenance.migration_reference_rewriter import rewrite_metadata_bytes


def transfer_without_overwrite(source, destination, kind="file", *, temporary=None):
    (source, destination) = (Path(source), Path(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        os.symlink(os.readlink(source), destination)
    else:
        try:
            os.link(source, destination)
        except OSError as exc:
            if exc.errno not in {errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP}:
                raise
            # Copy on the destination filesystem, then publish without replacing
            # a concurrently created file. The journal owns resumable copy paths.
            if temporary is None:
                handle, name = tempfile.mkstemp(prefix=".migration-copy-", dir=destination.parent)
                os.close(handle)
                temporary = Path(name)
            else:
                temporary = Path(temporary)
            try:
                with source.open("rb") as incoming, temporary.open("wb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                verify_file(temporary, file_digest(source))
                shutil.copystat(source, temporary)
                if os.name == "nt":
                    os.rename(temporary, destination)
                else:
                    os.link(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)


def validate_plan_locations(plan):
    source_root = Path(plan.source_root).resolve() / "outputs"
    workspace = Path(plan.workspace_root).resolve()
    seen = set()
    for move in plan.moves:
        (source, destination) = (Path(move.source), Path(move.destination))
        if not source.is_absolute() or not source.parent.resolve().is_relative_to(source_root):
            raise ValueError(f"Migration source is outside inventoried outputs: {source}")
        if not destination.is_absolute() or not destination.parent.resolve().is_relative_to(workspace):
            raise ValueError(f"Migration destination is outside the workspace: {destination}")
        if destination in seen:
            raise ValueError(f"Duplicate migration destination: {destination}")
        seen.add(destination)


def apply_migration(plan, journal_path, *, after_operation=None):
    validate_plan_locations(plan)
    journal_path = Path(journal_path)
    journal = open_journal(journal_path, plan)
    if journal["status"] == "rolled_back":
        raise ValueError("This migration was rolled back; create a new plan and journal to apply again.")
    for index, move in enumerate(plan.moves):
        (source, destination) = (Path(move.source), Path(move.destination))
        phase = journal["operations"][index]
        if phase == "moved":
            metadata = journal["metadata"].get(str(destination), {})
            expected = metadata.get("rewritten_hash", move.sha256)
            current = file_digest(destination)
            if current not in {expected, move.sha256}:
                raise RuntimeError(f"Migrated file was subsequently changed: {destination}")
            continue
        if phase == "planned":
            verify_file(source, move.sha256)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Migration never overwrites an existing destination: {destination}")
            temporary = destination.with_name(
                "." + destination.name + ".migration-copy-" + hashlib.sha256(move.source.encode()).hexdigest()[:12]
            )
            if temporary.exists():
                raise FileExistsError(f"Migration temporary path is already occupied: {temporary}")
            journal.setdefault("temporary_copies", {})[str(index)] = str(temporary)
            journal["operations"][index] = "moving"
            save_journal(journal_path, journal)
        if source.exists() or source.is_symlink():
            verify_file(source, move.sha256)
            if not destination.exists() and (not destination.is_symlink()):
                transfer_without_overwrite(
                    source, destination, move.kind, temporary=journal.get("temporary_copies", {}).get(str(index))
                )
            verify_file(destination, move.sha256)
            source.unlink()
        else:
            verify_file(destination, move.sha256)
        journal["operations"][index] = "moved"
        save_journal(journal_path, journal)
        if after_operation is not None:
            after_operation(index, move)
    mapping = {move.source: move.destination for move in plan.moves}
    for move in plan.moves:
        path = Path(move.destination)
        if move.kind != "file" or path.suffix.lower() not in {".json", ".yaml", ".yml", ".md", ".html", ".htm"}:
            continue
        record = journal["metadata"].get(str(path))
        if record:
            backup = Path(record["backup"])
            if backup.exists() and file_digest(backup) == record["original_hash"]:
                original = backup.read_bytes()
            else:
                # The journal reserves the backup before writing it. An interrupted
                # write can be rebuilt only while the verified original still exists.
                verify_file(path, record["original_hash"])
                original = path.read_bytes()
            if file_digest(path) == record["rewritten_hash"]:
                verify_file(backup, record["original_hash"])
                continue
            verify_file(path, record["original_hash"])
        else:
            verify_file(path, move.sha256)
            original = path.read_bytes()
        remapped_id = next(
            (
                new_id
                for folder, new_id in plan.profile_id_remapping.items()
                if Path(move.source).is_relative_to(folder)
            ),
            None,
        )
        try:
            revised = rewrite_metadata_bytes(path, original, mapping, remapped_id)
        except (UnicodeDecodeError, ValueError):
            continue
        if revised == original:
            continue
        if record is None:
            backup = (
                journal_path.parent
                / (journal_path.stem + "_metadata")
                / hashlib.sha256(move.source.encode()).hexdigest()
            )
            temporary = path.with_name(path.name + ".migration-writing")
            if backup.exists() or temporary.exists():
                raise FileExistsError(f"Migration metadata path is already occupied: {backup} or {temporary}")
            record = {
                "backup": str(backup),
                "temporary": str(temporary),
                "original_hash": move.sha256,
                "rewritten_hash": hashlib.sha256(revised).hexdigest(),
            }
            journal["metadata"][str(path)] = record
            save_journal(journal_path, journal)
        backup = Path(record["backup"])
        temporary = Path(record.get("temporary", str(path) + ".migration-writing"))
        if not backup.exists() or file_digest(backup) != record["original_hash"]:
            verify_file(path, record["original_hash"])
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open("wb") as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
        verify_file(backup, record["original_hash"])
        with temporary.open("wb") as stream:
            stream.write(revised)
            stream.flush()
            os.fsync(stream.fileno())
        verify_file(path, record["original_hash"])
        temporary.replace(path)
        verify_file(path, record["rewritten_hash"])
    root = Path(plan.source_root) / "outputs"
    if root.is_dir():
        containers = sorted(
            (path for path in root.rglob("*") if path.is_dir() and (not path.is_symlink())),
            key=lambda path: len(path.parts),
            reverse=True,
        )
        for path in [*containers, root]:
            try:
                path.rmdir()
            except OSError:
                continue
            journal["removed_containers"].append(str(path))
            save_journal(journal_path, journal)
    journal["status"] = "complete"
    save_journal(journal_path, journal)
    return journal
