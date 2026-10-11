"""Persist matching corrected CSV/H5 tables with recording and marker metadata."""

from pathlib import Path

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionResult
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
        return KneeCorrectionResult(
            source_csv=pair.csv_path,
            source_h5=pair.h5_path,
            source_video=pair.video_path,
            output_csv=output_csv,
            output_h5=output_h5,
            markers=reports,
        )
