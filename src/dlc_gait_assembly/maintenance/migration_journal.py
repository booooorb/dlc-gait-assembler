"""Atomically persist resumable operation states and metadata backups."""

import json
import os
from pathlib import Path

from dlc_gait_assembly.maintenance.migration_contracts import MigrationPlan


def save_journal(path, journal):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".writing")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(journal, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def open_journal(path, plan=None):
    path = Path(path)
    if path.exists():
        journal = json.loads(path.read_text(encoding="utf-8"))
        if plan is not None and journal["plan"] != plan.as_dict():
            if json.dumps(journal["plan"], sort_keys=True) != json.dumps(plan.as_dict(), sort_keys=True):
                raise ValueError("This journal belongs to a different migration plan.")
        return journal
    if plan is None:
        raise FileNotFoundError(path)
    journal = {
        "version": 1,
        "status": "planned",
        "plan": plan.as_dict(),
        "operations": ["planned"] * len(plan.moves),
        "metadata": {},
        "removed_containers": [],
    }
    save_journal(path, journal)
    return journal


def journal_plan(journal):
    return MigrationPlan.from_dict(journal["plan"])
