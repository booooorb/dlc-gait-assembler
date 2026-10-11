"""Read and write the reusable spatial conversion-map format."""

import json
from pathlib import Path

from dlc_gait_assembly.shared.business.calibration_scale_resolution import resolve_calibration_scale


def read_calibration_map(path):
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def write_calibration_map(path, payload):
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def pixels_per_cm_from_calibration_map(map_path, view_index=None):
    return resolve_calibration_scale(read_calibration_map(map_path), view_index)
