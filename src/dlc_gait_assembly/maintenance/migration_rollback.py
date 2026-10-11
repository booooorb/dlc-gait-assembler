"""Reverse journaled moves only when neither outputs nor restored locations have changed."""

import os
from pathlib import Path

from dlc_gait_assembly.maintenance.migration_executor import transfer_without_overwrite
from dlc_gait_assembly.maintenance.migration_inventory import file_digest, verify_file
from dlc_gait_assembly.maintenance.migration_journal import journal_plan, open_journal, save_journal


def rollback_migration(journal_path):
    journal_path = Path(journal_path)
    journal = open_journal(journal_path)
    if journal["status"] == "rolled_back":
        return journal
    plan = journal_plan(journal)
    for index, move in enumerate(plan.moves):
        phase = journal["operations"][index]
        if phase in {"planned", "restored"}:
            continue
        (source, destination) = (Path(move.source), Path(move.destination))
        if not destination.exists() and (not destination.is_symlink()):
            if phase == "restoring":
                verify_file(source, move.sha256)
                continue
            if phase == "moving":
                verify_file(source, move.sha256)
                continue
            raise FileNotFoundError(destination)
        record = journal["metadata"].get(str(destination))
        allowed = {move.sha256, record["rewritten_hash"]} if record else {move.sha256}
        if file_digest(destination) not in allowed:
            raise RuntimeError(f"Refusing to roll back a subsequently changed file: {destination}")
        if record and file_digest(destination) != move.sha256:
            verify_file(Path(record["backup"]), record["original_hash"])
        if source.exists() or source.is_symlink():
            if phase not in {"moving", "restoring"}:
                raise FileExistsError(f"Original location is now occupied: {source}")
            verify_file(source, move.sha256)
    for index in reversed(range(len(plan.moves))):
        move = plan.moves[index]
        if journal["operations"][index] in {"planned", "restored"}:
            continue
        (source, destination) = (Path(move.source), Path(move.destination))
        journal["operations"][index] = "restoring"
        save_journal(journal_path, journal)
        if destination.exists() or destination.is_symlink():
            record = journal["metadata"].get(str(destination))
            if record and file_digest(destination) != move.sha256:
                backup = Path(record["backup"])
                verify_file(backup, record["original_hash"])
                temporary = Path(record.get("rollback_temporary", str(destination) + ".migration-rollback"))
                if "rollback_temporary" not in record:
                    if temporary.exists():
                        raise FileExistsError(f"Rollback temporary path is already occupied: {temporary}")
                    record["rollback_temporary"] = str(temporary)
                    save_journal(journal_path, journal)
                with temporary.open("wb") as stream:
                    stream.write(backup.read_bytes())
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(destination)
            if not source.exists() and (not source.is_symlink()):
                transfer_without_overwrite(destination, source, move.kind)
            verify_file(source, move.sha256)
            destination.unlink()
        else:
            verify_file(source, move.sha256)
        journal["operations"][index] = "restored"
        save_journal(journal_path, journal)
    journal["status"] = "rolled_back"
    save_journal(journal_path, journal)
    return journal
