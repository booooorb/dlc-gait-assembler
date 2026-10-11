"""Preview, apply, resume, and roll back explicitly requested workspace migrations."""

import argparse
import json
from pathlib import Path

from dlc_gait_assembly.maintenance.migration_collision_policy import plan_migration
from dlc_gait_assembly.maintenance.migration_contracts import MigrationPlan
from dlc_gait_assembly.maintenance.migration_executor import apply_migration
from dlc_gait_assembly.maintenance.migration_inventory import inventory_outputs
from dlc_gait_assembly.maintenance.migration_journal import journal_plan, open_journal
from dlc_gait_assembly.maintenance.migration_rollback import rollback_migration
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import find_project_root, resolve_workspace


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("dry-run", "apply", "resume", "rollback"), nargs="?", default="dry-run")
    parser.add_argument("--source-root", type=Path, default=None)
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args(argv)
    if args.command == "dry-run":
        source = args.source_root or find_project_root()
        workspace = args.workspace or resolve_workspace(source).root
        plan = plan_migration(inventory_outputs(source), source, workspace)
        text = json.dumps(plan.as_dict(), indent=2) + "\n"
        if args.plan:
            args.plan.parent.mkdir(parents=True, exist_ok=True)
            with args.plan.open("x", encoding="utf-8") as stream:
                stream.write(text)
        else:
            print(text)
        return 0
    if args.journal is None:
        parser.error("--journal is required when applying, resuming, or rolling back")
    if args.command == "rollback":
        rollback_migration(args.journal)
    elif args.command == "resume":
        plan = journal_plan(open_journal(args.journal))
        apply_migration(plan, args.journal)
    else:
        if args.plan is None:
            parser.error("apply requires the --plan created by a reviewed dry run")
        plan = MigrationPlan.from_dict(json.loads(args.plan.read_text(encoding="utf-8")))
        apply_migration(plan, args.journal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
