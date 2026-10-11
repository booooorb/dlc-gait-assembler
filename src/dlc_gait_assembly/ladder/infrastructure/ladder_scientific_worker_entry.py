"""Execute a serialized Ladder request within the explicitly configured scientific runtime."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderSettings
from dlc_gait_assembly.ladder.infrastructure.ladder_runtime_executor import run_in_process


def run_request(request_path: Path) -> None:
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    result = run_in_process(
        Path(payload["csv_file"]),
        Path(payload["output_folder"]),
        LadderSettings(**payload["settings"]),
        payload.get("bodyparts"),
    )
    Path(payload["result_path"]).write_text(
        json.dumps(
            {
                "input_file": str(result.input_file),
                "output_file": str(result.output_file),
                "events": [asdict(event) for event in result.events],
            }
        ),
        encoding="utf-8",
    )


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-request":
        run_request(Path(sys.argv[2]))
        return
    raise SystemExit(
        "Usage: python -m dlc_gait_assembly.ladder.infrastructure.ladder_scientific_worker_entry --run-request REQUEST.json"
    )


if __name__ == "__main__":
    main()
