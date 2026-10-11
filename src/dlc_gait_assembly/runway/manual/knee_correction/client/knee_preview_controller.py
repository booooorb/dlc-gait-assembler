"""Coordinate sampled knee previews, decoded media frames, caching, and invalidation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QMessageBox

from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import CoordinateFilePair
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_preview_sampling import (
    bodypart_point,
    previewable_frame_positions,
)
from dlc_gait_assembly.shared.business.media_access_contracts import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from dlc_gait_assembly.shared.client.qt_frame_conversion import rgb_array_to_qimage


class KneePreviewController:
    """KneePreviewController operates on its explicitly supplied KneeCorrectionWidget view."""

    def __init__(self, view):
        self.view = view

    def _set_preview_media(self, path: Path, notify: bool = True) -> bool:
        resolved = path.expanduser().absolute()
        extension = resolved.suffix.casefold()
        self._release_preview_capture()
        self.view.state.preview_media_path = None
        self.view._preview_static_image = None
        self.view.state.preview_video_frame_count = 0
        try:
            if extension in IMAGE_EXTENSIONS:
                self.view._preview_static_image = rgb_array_to_qimage(self.view.media_access.read_image(resolved))
            elif extension in VIDEO_EXTENSIONS:
                self.view._preview_capture = self.view.media_access.open_video(resolved)
                self.view.state.preview_video_frame_count = self.view._preview_capture.info.frame_count
            else:
                raise ValueError("The paired preview background must be an image or video file.")
        except (OSError, ValueError) as exc:
            if notify:
                QMessageBox.critical(self.view, "Could not load preview media", str(exc))
            return False
        self.view.state.preview_media_path = resolved
        if self.view.state.preview_original is not None:
            self._show_preview_frame(self.view.preview_slider.value())
        return True

    def _release_preview_capture(self) -> None:
        if self.view._preview_capture is not None:
            self.view._preview_capture.close()
            self.view._preview_capture = None

    def _preview_inputs_changed(self, *_args) -> None:
        self._invalidate_preview()
        self._maybe_generate_previews()

    def _invalidate_preview(self, *_args) -> None:
        self.view.state.preview_original = None
        self.view.state.preview_corrected = None
        self.view.state.preview_report = None
        self.view.state.preview_cache.clear()
        self.view.state.active_preview_pair_key = None
        self.view.state.preview_frame_positions = ()
        self.view.preview_slider.setEnabled(False)
        self.view.preview_slider.setRange(0, 0)
        self.view.preview_frame_label.setText("Frame —")
        self.view.preview_frame_label.setToolTip("")
        if self.view.state.pixels_per_cm is None:
            empty_message = "Import a calibration map to generate previews"
            status_message = "Preview unavailable until a calibration map is imported."
        elif not any(pair.is_paired for pair in self.view.state.pairs):
            empty_message = "Add a paired CSV, H5, and video to generate previews"
            status_message = "Preview unavailable until every dataset is paired."
        else:
            empty_message = "Generating previews…"
            status_message = "Generating previews after changing inputs."
        self.view.knee_preview.set_empty_message(empty_message)
        self.view.knee_preview.clear_points()
        self._update_preview_navigation()
        if hasattr(self.view, "preview_status_label"):
            self.view.preview_status_label.setText(status_message)

    def _preview_media_name(self) -> str:
        return self.view.state.preview_media_path.name if self.view.state.preview_media_path is not None else ""

    def _pair_key(self, pair: CoordinateFilePair) -> tuple[str, str, str] | None:
        if pair.csv_path is None or pair.h5_path is None or pair.video_path is None:
            return None
        return (str(pair.csv_path), str(pair.h5_path), str(pair.video_path))

    def _selected_preview_pair(self) -> CoordinateFilePair | None:
        selected = self.view.pair_table.selectedItems()
        if selected:
            index = self.view.pair_table.indexOfTopLevelItem(selected[0])
            if 0 <= index < len(self.view.state.pairs) and self.view.state.pairs[index].is_paired:
                return self.view.state.pairs[index]
        return next((pair for pair in self.view.state.pairs if pair.is_paired), None)

    def _generate_preview(self) -> None:
        self._generate_all_previews(show_errors=True)

    def _maybe_generate_previews(self) -> None:
        if self.view.state.pixels_per_cm is None:
            return
        if not any(pair.is_paired for pair in self.view.state.pairs):
            return
        self._generate_all_previews(show_errors=False)

    def _generate_all_previews(self, show_errors: bool) -> None:
        if self.view.state.pixels_per_cm is None:
            self._invalidate_preview()
            if show_errors:
                QMessageBox.information(self.view, "Calibration required", "Import a calibration map first.")
            return
        paired = [pair for pair in self.view.state.pairs if pair.is_paired]
        if not paired:
            self._invalidate_preview()
            if show_errors:
                QMessageBox.information(
                    self.view, "No paired dataset", "Add or select a paired CSV, H5, and video dataset."
                )
            return
        self.view.state.preview_cache.clear()
        errors: list[str] = []
        for pair in paired:
            key = self._pair_key(pair)
            if key is None or pair.csv_path is None:
                continue
            try:
                (original, corrected, reports) = self.view.use_cases.preview(pair, self.view.controller._settings())
            except Exception as exc:
                errors.append(f"{pair.stem}: {exc}")
                continue
            report = reports[0]
            self.view.state.preview_cache[key] = (
                original,
                corrected,
                report,
                previewable_frame_positions(report.frame_statuses),
            )
        if errors:
            for message in errors:
                self.view.log.appendPlainText(f"[Preview] {message}")
            if show_errors:
                QMessageBox.warning(self.view, "Some previews could not be generated", "\n".join(errors[:5]))
        if not self.view.state.preview_cache:
            self.view.state.active_preview_pair_key = None
            self.view.knee_preview.set_empty_message("Could not generate a preview")
            self.view.knee_preview.clear_points()
            self.view.preview_status_label.setText("Could not generate previews.")
            return
        self._show_selected_preview()
        self.view.log.appendPlainText(f"[Preview] Generated {len(self.view.state.preview_cache)} preview(s).")

    def _show_selected_preview(self) -> None:
        pair = self._selected_preview_pair()
        if pair is None or pair.csv_path is None or pair.video_path is None:
            if self.view.state.pixels_per_cm is None:
                self.view.knee_preview.set_empty_message("Import a calibration map to generate previews")
            else:
                self.view.knee_preview.set_empty_message("Add a paired CSV, H5, and video")
            self.view.knee_preview.clear_points()
            return
        key = self._pair_key(pair)
        if key is None:
            return
        if key not in self.view.state.preview_cache:
            if self.view.state.pixels_per_cm is None:
                self._invalidate_preview()
            else:
                self._maybe_generate_previews()
            if key not in self.view.state.preview_cache:
                self.view.knee_preview.set_empty_message("Preview could not be generated")
                self.view.knee_preview.clear_points()
                self.view.preview_status_label.setText(f"{pair.stem} • preview unavailable")
                return
        if self.view._preview_static_image is None and self.view.state.preview_media_path != pair.video_path:
            self._set_preview_media(pair.video_path, notify=False)
        (original, corrected, report, frame_positions) = self.view.state.preview_cache[key]
        self.view.state.active_preview_pair_key = key
        previous_value = self.view.preview_slider.value()
        self.view.state.preview_original = original
        self.view.state.preview_corrected = corrected
        self.view.state.preview_report = report
        self.view.state.preview_frame_positions = frame_positions
        self.view.preview_slider.blockSignals(True)
        self.view.preview_slider.setRange(0, max(0, len(frame_positions) - 1))
        self.view.preview_slider.setEnabled(len(frame_positions) > 0)
        self.view.preview_slider.setValue(min(previous_value, self.view.preview_slider.maximum()))
        self.view.preview_slider.blockSignals(False)
        if len(original) == 0:
            self.view.knee_preview.set_empty_message("Preview has no frames")
            self.view.knee_preview.clear_points()
            self.view.preview_status_label.setText(f"{pair.stem} • preview has no frames")
            self._update_preview_navigation()
            return
        if not frame_positions:
            self.view.knee_preview.set_empty_message("No frames meet the confidence cutoff")
            self.view.knee_preview.clear_points()
            self.view.preview_status_label.setText(f"{pair.stem} • no frames meet confidence cutoff")
            self.view.preview_frame_label.setText("Frame —")
            self.view.preview_frame_label.setToolTip("")
            self._update_preview_navigation()
            return
        media_name = self._preview_media_name()
        media_suffix = f" • frame: {media_name}" if media_name else ""
        self.view.preview_status_label.setText(f"{pair.stem} • {report.knee}{media_suffix}")
        self._show_preview_frame(self.view.preview_slider.value())
        self.view.knee_preview.setFocus()

    def _show_preview_frame(self, frame_position: int) -> None:
        if (
            self.view.state.preview_original is None
            or self.view.state.preview_corrected is None
            or self.view.state.preview_report is None
            or (len(self.view.state.preview_original) == 0)
            or (not self.view.state.preview_frame_positions)
        ):
            return
        preview_position = max(0, min(int(frame_position), len(self.view.state.preview_frame_positions) - 1))
        position = self.view.state.preview_frame_positions[preview_position]
        report = self.view.state.preview_report
        hip = bodypart_point(self.view.state.preview_original, report.hip, position)
        ankle = bodypart_point(self.view.state.preview_original, report.ankle, position)
        old_knee = bodypart_point(self.view.state.preview_original, report.knee, position)
        correction_status = report.frame_statuses[position]
        new_knee = (
            bodypart_point(self.view.state.preview_corrected, report.knee, position)
            if correction_status == "Corrected"
            else None
        )
        (background_frame, media_status) = self._preview_frame_image(position)
        self.view.knee_preview.set_points(
            hip, ankle, old_knee, new_knee, correction_status, background_frame=background_frame
        )
        frame_name = self.view.state.preview_original.index[position]
        unavailable = []
        if hip is None:
            unavailable.append("hip")
        if ankle is None:
            unavailable.append("ankle")
        if old_knee is None:
            unavailable.append("old knee")
        frame_status = "corrected" if correction_status == "Corrected" else f"retained: {correction_status}"
        if unavailable:
            frame_status += " • unavailable: " + ", ".join(unavailable)
        if media_status:
            frame_status += f" • {media_status}"
        frame_label = f"Frame {frame_name} • preview {preview_position + 1}/{len(self.view.state.preview_frame_positions)} • {frame_status}"
        self.view.preview_frame_label.setText(frame_label)
        self.view.preview_frame_label.setToolTip(frame_label)
        self._update_preview_navigation()

    def _step_preview_frame(self, delta: int) -> None:
        if not self.view.preview_slider.isEnabled():
            return
        current = self.view.preview_slider.value()
        target = max(self.view.preview_slider.minimum(), min(self.view.preview_slider.maximum(), current + int(delta)))
        if target != current:
            self.view.preview_slider.setValue(target)
        else:
            self._update_preview_navigation()
        self.view.knee_preview.setFocus()

    def _update_preview_navigation(self) -> None:
        has_frames = (
            self.view.preview_slider.isEnabled()
            and self.view.preview_slider.maximum() > self.view.preview_slider.minimum()
        )
        value = self.view.preview_slider.value()
        self.view.previous_frame_button.setEnabled(has_frames and value > self.view.preview_slider.minimum())
        self.view.next_frame_button.setEnabled(has_frames and value < self.view.preview_slider.maximum())

    def _preview_frame_image(self, position: int) -> tuple[QImage | None, str | None]:
        if self.view._preview_static_image is not None:
            return (self.view._preview_static_image, None)
        if self.view._preview_capture is None:
            return (None, None)
        frame = self.view._preview_capture.read_frame(position)
        return (None, "video frame unavailable") if frame is None else (rgb_array_to_qimage(frame), None)
