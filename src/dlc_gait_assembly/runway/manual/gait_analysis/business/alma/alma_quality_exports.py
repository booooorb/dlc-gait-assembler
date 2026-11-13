"""Persist ALMA coordinate provenance and per-recording quality reports through the output port."""

import json


def write_alma_quality_outputs(outputs, folder, side, result):
    parameters, coords = result[:2]
    report = parameters.attrs.get("analysis_report")
    if report is None or coords is None:
        return ()
    report_path = folder / f"{side}_analysis_report.json"
    coords_path = folder / f"{side}_coordinates.csv"
    outputs.write_text(report_path, json.dumps(report, indent=2, allow_nan=False) + "\n")
    outputs.write_table(coords, coords_path, index=False)
    outputs.validate_outputs((report_path,))
    outputs.validate_outputs((coords_path,), expected_rows=len(coords))
    return (report_path, coords_path)
