"""Coordinate input validation, paw detection, and event persistence through ports."""

from pathlib import Path

from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderRunResult
from dlc_gait_assembly.ladder.business.ladder_analysis_ports import (
    LadderCoordinateInputPort,
    LadderEventExportPort,
    LadderScientificExecutionPort,
)
from dlc_gait_assembly.ladder.business.ladder_event_review_rules import review_ladder_event
from dlc_gait_assembly.ladder.business.ladder_footfall_detection import detect_bodypart
from dlc_gait_assembly.ladder.business.ladder_marker_selection import suggested_ladder_bodyparts


class LadderAnalysisUseCases:
    def __init__(
        self,
        coordinates: LadderCoordinateInputPort,
        events: LadderEventExportPort,
        defaults=None,
        *,
        execution: LadderScientificExecutionPort | None = None,
    ):
        self.coordinates = coordinates
        self.events = events
        self.defaults = defaults
        self.execution = execution

    def run(self, csv_file, output_folder, settings, bodyparts=None):
        if self.execution is not None:
            return self.execution(csv_file, output_folder, settings, bodyparts)
        import numpy as np
        from scipy import sparse
        from scipy.signal import find_peaks
        from scipy.sparse.linalg import spsolve

        (dataframe, detected) = self.coordinates.read(csv_file)
        selected = list(bodyparts) if bodyparts is not None else suggested_ladder_bodyparts(detected)
        unknown = [bodypart for bodypart in selected if bodypart not in detected]
        if unknown:
            raise ValueError("Body parts not found in the CSV: " + ", ".join(unknown))
        if not selected:
            raise ValueError("Select at least one body part for ladder analysis.")
        events = []
        for bodypart in selected:
            events.extend(detect_bodypart(dataframe, bodypart, settings, np, find_peaks, sparse, spsolve))
        events.sort(key=lambda event: (event.peak_frame, event.bodypart))
        output_file = self.events.write(events, Path(output_folder) / f"{Path(csv_file).stem}_ladder_footfalls.csv")
        return LadderRunResult(Path(csv_file), output_file, tuple(events))

    def bodyparts(self, path):
        return self.coordinates.bodyparts(path)

    def export_reviewed(self, events, destination, *, combined=False):
        reviewed = [review_ladder_event(event, event.classification, event.included) for event in events]
        return self.events.write(reviewed, destination, combined=combined)
