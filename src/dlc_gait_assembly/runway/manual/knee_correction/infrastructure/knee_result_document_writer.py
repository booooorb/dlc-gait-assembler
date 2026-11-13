"""Persist matching corrected CSV/H5 tables with recording and marker metadata."""

import json
from dataclasses import asdict
from pathlib import Path

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionResult
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_geometry_recovery import MOUSE_RATIO_SOURCE
from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import write_dlc_csv
from dlc_gait_assembly.shared.infrastructure.coordinate_h5_codec import write_dlc_h5


class KneeResultDocumentWriter:
    def write(self, pair, destination, corrected, h5_key, reports):
        destination = Path(destination).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        output_csv = destination / f"{pair.stem}_knee_corrected.csv"
        output_h5 = destination / f"{pair.stem}_knee_corrected.h5"
        write_dlc_csv(corrected, output_csv)
        write_dlc_h5(corrected, output_h5, h5_key, source_path=pair.h5_path)
        report_path = destination / f"{pair.stem}_knee_correction_report.json"
        report_path.write_text(
            json.dumps(
                {
                    "report_version": 1,
                    "frame_number_basis": "zero-based source row position",
                    "length_units": "pixels",
                    "fallback_ratio_source": MOUSE_RATIO_SOURCE,
                    "ratio_note": "Editable adult-mouse femur/tibia prior. Frame-local geometric lengths are estimates, not physical bone growth.",
                    "confidence_note": "Configured geometry inherits min(hip likelihood, ankle likelihood). Adjusted geometry is further penalized and capped. Temporal display coordinates have confidence zero. These scores are conservative proxies, not independently calibrated probabilities.",
                    "markers": [asdict(report) for report in reports],
                },
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        return KneeCorrectionResult(
            source_csv=pair.csv_path,
            source_h5=pair.h5_path,
            source_video=pair.video_path,
            output_csv=output_csv,
            output_h5=output_h5,
            markers=reports,
            report_path=report_path,
        )
