"""Bridge paired knee reconstruction progress, reports, and completion into Qt signals."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import (
    CoordinateFilePair,
    KneeCorrectionResult,
    KneeCorrectionSettings,
)


class KneeCorrectionThread(QThread):
    progress_updated = Signal(int, str)
    completed = Signal(bool, str)

    def __init__(
        self, pairs: tuple[CoordinateFilePair, ...], output_folder: Path, settings: KneeCorrectionSettings, *, use_cases
    ):
        super().__init__()
        self.setStackSize(8 * 1024 * 1024)
        self.use_cases = use_cases
        self._pairs = pairs
        self._output_folder = output_folder
        self._settings = settings
        self.results: list[KneeCorrectionResult] = []

    def run(self) -> None:
        try:
            for index, pair in enumerate(self._pairs, start=1):
                if self.isInterruptionRequested():
                    self.completed.emit(False, "Knee correction was stopped.")
                    return
                self.progress_updated.emit(
                    round((index - 1) / len(self._pairs) * 100), f"Correcting {pair.stem} ({index}/{len(self._pairs)})…"
                )
                result = self.use_cases.correct_pair(pair, self._output_folder, self._settings)
                self.results.append(result)
                for marker in result.markers:
                    self.progress_updated.emit(
                        round(index / len(self._pairs) * 100),
                        f"{pair.stem}: {marker.knee} corrected in {marker.corrected_frames} frame(s).",
                    )
                    retained_reasons = Counter(status for status in marker.frame_statuses if status != "Corrected")
                    for reason, count in sorted(retained_reasons.items()):
                        self.progress_updated.emit(
                            round(index / len(self._pairs) * 100), f"{pair.stem}: retained {count} frame(s) — {reason}."
                        )
            self.completed.emit(True, f"Created corrected CSV and H5 files for {len(self.results)} dataset(s).")
        except Exception as exc:
            self.completed.emit(False, str(exc))
