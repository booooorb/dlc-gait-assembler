"""Load recording views through the common coordinate codec and preserve frame indices."""

from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_marker_reader import read_dlc_bodyparts
from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import read_analysis_csv
from dlc_gait_assembly.shared.infrastructure.media_metadata_reader import probe_video


def merge_multiview_rustlab1_dataframe(view_set, pd, view_mappings=None):
    frames = {
        view: read_analysis_csv(path)
        for (view, path) in (
            ("left", view_set.left_csv),
            ("right", view_set.right_csv),
            ("bottom", view_set.bottom_csv),
        )
    }
    return align_multiview_coordinates(frames, pd, view_mappings)


class GaitInputReader:
    bodyparts = staticmethod(read_dlc_bodyparts)
    probe_video = staticmethod(probe_video)

    def csv_files(self, directory):
        return tuple(path for path in Path(directory).rglob("*") if path.is_file() and path.suffix.lower() == ".csv")
