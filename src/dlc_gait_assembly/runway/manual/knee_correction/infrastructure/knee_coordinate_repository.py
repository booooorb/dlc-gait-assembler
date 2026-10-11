"""Read paired DeepLabCut coordinates using the shared CSV/H5 codecs."""

from pathlib import Path

from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import read_dlc_bodyparts, read_dlc_csv
from dlc_gait_assembly.shared.infrastructure.coordinate_h5_codec import read_dlc_h5


class KneeCoordinateRepository:
    def load_preview(self, pair):
        return read_dlc_csv(pair.csv_path)

    def load(self, pair):
        csv_frame = read_dlc_csv(pair.csv_path)
        (h5_frame, key) = read_dlc_h5(pair.h5_path)
        return (csv_frame, h5_frame, key)

    def bodyparts(self, path):
        return read_dlc_bodyparts(path)

    def input_files(self, directory):
        return tuple(path for path in Path(directory).rglob("*") if path.is_file())

    def exists(self, path):
        return Path(path).is_file()
