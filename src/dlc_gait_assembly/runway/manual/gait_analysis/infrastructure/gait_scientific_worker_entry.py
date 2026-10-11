"""Execute a serialized gait request in the explicitly configured scientific runtime."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
    alma_input_from_json,
    run_alma_gait_analysis_in_process,
    settings_from_json,
)


def run_request(request_path: Path) -> None:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    inputs = request.get("inputs")
    if inputs is None:
        inputs = request["csv_files"]
    results = run_alma_gait_analysis_in_process(
        [alma_input_from_json(item) for item in inputs],
        Path(request["output_folder"]),
        settings_from_json(request["settings"]),
    )
    payload = {
        "results": [
            {
                "input_file": str(result.input_file),
                "output_files": [str(path) for path in result.output_files],
                "messages": list(result.messages),
            }
            for result in results
        ]
    }
    Path(request["result_path"]).write_text(json.dumps(payload), encoding="utf-8")


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-request":
        run_request(Path(sys.argv[2]))
        return
    raise SystemExit(
        "Usage: python -m dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_worker_entry --run-request REQUEST_JSON"
    )


if __name__ == "__main__":
    main()
