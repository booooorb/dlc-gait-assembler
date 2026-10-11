"""Load paired datasets, reconstruct knees, and persist paired corrected results."""

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_coordinate_correction import correct_knee_dataframe
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_ports import (
    KneeCoordinateRepositoryPort,
    KneeResultWriterPort,
)


class KneeCorrectionUseCases:
    def __init__(self, coordinates: KneeCoordinateRepositoryPort, results: KneeResultWriterPort, settings=None):
        self.coordinates = coordinates
        self.results = results
        self.settings = settings

    def correct_pair(self, pair, output_folder, settings):
        if not pair.is_paired or pair.csv_path is None or pair.h5_path is None or (pair.video_path is None):
            raise ValueError(f'"{pair.stem}" does not have exactly one CSV, one H5, and one video file.')
        (csv_dataframe, h5_dataframe, h5_key) = self.coordinates.load(pair)
        if not csv_dataframe.columns.equals(h5_dataframe.columns) or not csv_dataframe.index.equals(h5_dataframe.index):
            raise ValueError(f'CSV and H5 labels do not match for "{pair.stem}".')
        (corrected, reports) = correct_knee_dataframe(csv_dataframe, settings)
        return self.results.write(pair, output_folder, corrected, h5_key, reports)

    def preview(self, pair, settings):
        original = self.coordinates.load_preview(pair)
        (corrected, reports) = correct_knee_dataframe(original, settings)
        return (original, corrected, reports)

    def save_settings(self, path, settings):
        return self.settings.write(path, settings)

    def calibration_scale(self, path):
        return self.settings.calibration_scale(path)

    def bodyparts(self, path):
        return self.coordinates.bodyparts(path)

    def input_files(self, directory):
        return self.coordinates.input_files(directory)

    def accepts_input(self, path):
        from dlc_gait_assembly.runway.manual.knee_correction.business.knee_coordinate_correction import PAIR_EXTENSIONS

        return self.coordinates.exists(path) and path.suffix.lower() in PAIR_EXTENSIONS

    def existing_outputs(self, folder, pairs):
        return [
            folder / f"{pair.stem}_knee_corrected{extension}"
            for pair in pairs
            for extension in (".csv", ".h5")
            if self.coordinates.exists(folder / f"{pair.stem}_knee_corrected{extension}")
        ]
