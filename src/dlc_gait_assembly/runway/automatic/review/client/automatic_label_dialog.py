"""Review filtered video frames and edit DeepLabCut markers before saving."""

from __future__ import annotations

from collections import OrderedDict

import numpy as np
from PySide6.QtCore import QAbstractListModel, QEvent, QItemSelectionModel, QSignalBlocker, Qt
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.automatic.review.business.automatic_label_correction import (
    LabelCorrection,
    LabelEdit,
    confidence_scores,
    frame_positions,
    knee_distance_errors,
    marker_columns,
)
from dlc_gait_assembly.runway.automatic.review.client.automatic_label_canvas import LabelCanvas, marker_color
from dlc_gait_assembly.shared.client.qt_frame_conversion import rgb_array_to_qimage
from dlc_gait_assembly.shared.client.theme import theme_application_state as theme


class ReviewFrames(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.frames = ()

    def replace(self, frames):
        self.beginResetModel()
        self.frames = tuple(frames)
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.frames)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            return f"Frame {self.frames[index.row()] + 1}"
        return None


class LabelCorrectionDialog(QDialog):
    FILTERS = ("Low confidence", "Knee distance outliers", "Either issue", "All frames")

    def __init__(self, parent, review, artifacts, media_access, preferred=None):
        super().__init__(parent)
        self.setWindowTitle("Correct DeepLabCut labels")
        self.resize(1090, 690)
        self.setMinimumSize(820, 535)
        self.review = review
        self.artifacts = artifacts
        self.media_access = media_access
        self.edits = {edit.key: edit for edit in review.label_draft}
        self.undo_stack = []
        self.clipboard = {}
        self.clipboard_source = None
        self.model_markers = {}
        self.correction = None
        self.capture = None
        self.table = None
        self.frame = None
        self.frame_images = OrderedDict()
        self.recording_frames = {}
        self.offset = (0, 0)
        self.columns = {}
        self.source = None
        self.points = {}
        self.active_marker = None
        self.mode = "select"
        self._build()
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        initial_index = next(
            (index for index, source in enumerate(self.review.label_sources) if source == preferred), 0
        )
        self.recording.setCurrentIndex(initial_index)
        if initial_index == 0:
            self._load_recording(0)
        self.canvas.setFocus()

    def _build(self):
        layout = QVBoxLayout(self)
        recording_row = QHBoxLayout()
        self.recording = QComboBox()
        self.recording.setAccessibleName("Recording and region")
        for source in self.review.label_sources:
            self.recording.addItem(f"{source.region} · {source.video.name}")
        recording_label = QLabel("Recording")
        recording_label.setBuddy(self.recording)
        recording_row.addWidget(recording_label)
        recording_row.addWidget(self.recording, 1)
        layout.addLayout(recording_row)

        body = QHBoxLayout()
        side = QVBoxLayout()
        side.addWidget(QLabel("Frames"))
        self.filter = QComboBox()
        self.filter.addItems(self.FILTERS)
        self.filter.setAccessibleName("Frame filter")
        side.addWidget(self.filter)
        self.confidence_row, self.confidence = self._percentage("Confidence below", 80, side)
        self.distance_row, self.distance = self._percentage("Knee error at least", 20, side)
        self.distance.setToolTip(
            "Difference from the calibrated segment lengths, or from the recording’s typical lengths "
            "when knee calibration is unavailable."
        )
        self.frame_summary = QLabel()
        side.addWidget(self.frame_summary)
        self.frame_list = QListView()
        self.frame_list.setAccessibleName("Matching frames")
        self.frame_list.setMaximumWidth(200)
        self.frame_list.setUniformItemSizes(True)
        self.frame_model = ReviewFrames(self)
        self.frame_list.setModel(self.frame_model)
        side.addWidget(self.frame_list, 1)
        self.show_all = self._button(side, "Show all frames", lambda: self.filter.setCurrentIndex(3))
        self.show_all.hide()
        navigation = QHBoxLayout()
        self.previous = self._button(navigation, "Previous", lambda: self._navigate(-1))
        self.next = self._button(navigation, "Next", lambda: self._navigate(1))
        side.addLayout(navigation)
        body.addLayout(side)

        center = QVBoxLayout()
        tools = QHBoxLayout()
        self.canvas = LabelCanvas(self)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for name, mode, key in (("Select", "select", "3"), ("Place", "add", "2"), ("Pan", "pan", "1")):
            button = self._button(tools, f"{name}  {key}", lambda _checked=False, value=mode: self._set_mode(value))
            button.setCheckable(True)
            button.setStyleSheet(f"QPushButton:checked {{ background: {theme.SOFT}; border-color: {theme.TOOL_1}; }}")
            self.mode_group.addButton(button)
            button.setChecked(mode == "select")
            self.mode_buttons[ord(key)] = button
        self.mode_buttons[Qt.Key_4] = self.mode_buttons[Qt.Key_1]
        tools.addStretch()
        self.fit_button = self._button(tools, "Fit", self.canvas.fit_frame)
        center.addLayout(tools)
        self.preview = QStackedWidget()
        self.preview.addWidget(self.canvas)
        self.empty_preview = QLabel()
        self.empty_preview.setAlignment(Qt.AlignCenter)
        self.empty_preview.setWordWrap(True)
        self.preview.addWidget(self.empty_preview)
        center.addWidget(self.preview, 1)
        self.frame_status = QLabel()
        self.frame_status.setWordWrap(True)
        center.addWidget(self.frame_status)
        self.tool_hint = QLabel()
        self.tool_hint.setWordWrap(True)
        center.addWidget(self.tool_hint)
        body.addLayout(center, 1)

        markers = QVBoxLayout()
        markers.addWidget(QLabel("Markers"))
        self.marker_list = QListWidget()
        self.marker_list.setMaximumWidth(200)
        self.marker_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.marker_list.setAccessibleName("Frame markers")
        markers.addWidget(self.marker_list, 1)
        self.marker_status = QLabel()
        self.marker_status.setWordWrap(True)
        markers.addWidget(self.marker_status)
        clipboard_actions = QHBoxLayout()
        self.copy_button = self._button(clipboard_actions, "Copy", self._copy)
        self.paste_button = self._button(clipboard_actions, "Paste", self._paste)
        markers.addLayout(clipboard_actions)
        edit_actions = QHBoxLayout()
        self.remove_button = self._button(edit_actions, "Remove", self._delete)
        self.undo_button = self._button(edit_actions, "Undo", self._undo)
        markers.addLayout(edit_actions)
        self.keep_button = self._button(markers, "Keep visible labels", self._confirm_visible)
        self.keep_button.setToolTip("Mark all visible labels on this frame as reviewed.")
        body.addLayout(markers)
        layout.addLayout(body, 1)

        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.PlainText)
        self.error.hide()
        layout.addWidget(self.error)
        if self.review.label_error:
            self._show_error(self.review.label_error)

        footer = QHBoxLayout()
        self.saved_status = QLabel()
        footer.addWidget(self.saved_status)
        footer.addStretch()
        self._button(footer, "Cancel", self.reject)
        self.frame_save = self._button(footer, "Save corrections", lambda: self._save(False))
        self.frame_save.setToolTip("Update this batch’s coordinates and regenerate its previews.")
        self.tune_save = self._button(footer, "Save and fine-tune", lambda: self._save(True))
        self.tune_save.setObjectName("PrimaryButton")
        self.tune_save.setToolTip(
            f"Add reviewed frames to the original DLC project, train for {self.review.fine_tune_epochs} epochs, "
            "and rerun this batch."
        )
        layout.addLayout(footer)

        self.recording.currentIndexChanged.connect(self._load_recording)
        self.filter.currentIndexChanged.connect(self._filter_frames)
        self.confidence.valueChanged.connect(self._filter_frames)
        self.distance.valueChanged.connect(self._filter_frames)
        self.frame_list.selectionModel().currentChanged.connect(lambda current, _: self._load_frame(current.row()))
        self.canvas.positions_changed.connect(self._edit)
        self.canvas.selection_changed.connect(self._select_from_canvas)
        self.marker_list.itemSelectionChanged.connect(self._marker_selection)
        self.marker_list.currentItemChanged.connect(lambda *_: self._marker_selection())
        self._update_save()

    def _button(self, layout, text, action):
        button = QPushButton(text)
        button.setAutoDefault(False)
        button.setFocusPolicy(Qt.TabFocus)
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def _percentage(self, title, value, layout):
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setSuffix("%")
        spin.setValue(value)
        label.setBuddy(spin)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(spin)
        layout.addWidget(container)
        return container, spin

    def _load_recording(self, index):
        if index < 0:
            return
        if self.source is not None and self.frame is not None:
            self.recording_frames[self.source] = self.frame
        self._close_capture()
        self.frame_images.clear()
        self.frame = None
        self.table = None
        self.source = self.review.label_sources[index]
        self._show_error(self.review.label_error)
        try:
            self.table, raw, self.offset = self.artifacts.label_artifacts(self.source)
            self.columns = marker_columns(self.table)
            self.model_markers[self.source.region, self.source.video] = set(marker_columns(raw))
            self.confidences = confidence_scores(raw)
            self.knee_errors = knee_distance_errors(raw, self.review.knee_settings)
            self.capture = self.media_access.open_video(self.source.video)
            count = self.capture.info.frame_count or len(self.table)
            if count != len(self.table) or len(raw) != len(self.table):
                raise ValueError(f"The video has {count} frames and its tracking table has {len(self.table)} rows.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._close_capture()
            self.table = None
            self.columns = {}
            self._show_error(str(exc))
        self._build_markers()
        self._filter_frames(preferred_frame=self.recording_frames.get(self.source))
        self._update_save()

    def _filter_frames(self, *_, preferred_frame=None):
        old_frame = self.frame if preferred_frame is None else preferred_frame
        with QSignalBlocker(self.frame_list.selectionModel()):
            if self.table is None:
                self.frame_model.replace(())
            else:
                mode = self.filter.currentIndex()
                low = self.confidences < self.confidence.value() / 100
                knee = self.knee_errors >= self.distance.value() / 100
                matches = (low, knee, low | knee, np.ones(len(low), dtype=bool))[mode]
                order = (self.confidences, -self.knee_errors, np.arange(len(low)), np.arange(len(low)))[mode]
                indices = np.argsort(order, kind="stable")
                self.frame_model.replace(indices[matches[indices]])
        self.confidence_row.setVisible(self.filter.currentIndex() in (0, 2))
        self.distance_row.setVisible(self.filter.currentIndex() in (1, 2))
        frames = self.frame_model.frames
        count = len(frames)
        self.frame_summary.setText(f"{count:,} frame{'s' if count != 1 else ''}")
        self.show_all.setVisible(not count and self.table is not None and self.filter.currentIndex() != 3)
        if frames:
            row = frames.index(old_frame) if old_frame in frames else 0
            self.frame_list.setCurrentIndex(self.frame_model.index(row, 0))
            if self.frame != frames[row]:
                self._load_frame(row)
            self._update_navigation()
        else:
            message = "No frames match this filter."
            if self.table is None:
                message = "This recording could not be opened."
            elif self.filter.currentIndex() == 1 and not np.isfinite(self.knee_errors).any():
                message = "Knee distances are unavailable for this recording."
            self._show_empty_frame(message)
            self._update_navigation()

    def _show_empty_frame(self, message):
        self.frame = None
        self.points = {}
        self.frame_status.clear()
        self.canvas.set_frame(QPixmap(), {}, (), self.offset)
        self.empty_preview.setText(message)
        self.preview.setCurrentWidget(self.empty_preview)
        self._update_marker_actions()

    def _navigate(self, step):
        row = self.frame_list.currentIndex().row() + step
        if 0 <= row < len(self.frame_model.frames):
            self.frame_list.setCurrentIndex(self.frame_model.index(row, 0))
            self.canvas.setFocus()

    def _update_navigation(self):
        row = self.frame_list.currentIndex().row()
        self.previous.setEnabled(row > 0)
        self.next.setEnabled(0 <= row < len(self.frame_model.frames) - 1)

    def _load_frame(self, row):
        if self.capture is None or not 0 <= row < len(self.frame_model.frames):
            return
        frame = int(self.frame_model.frames[row])
        pixmap = self._frame_image(frame)
        self._update_navigation()
        if pixmap.isNull():
            self._show_empty_frame(f"Frame {frame + 1:,} could not be read. Select another frame.")
            self._show_error(self.review.label_error)
            return
        fit = self.frame is None
        self.frame = frame
        self._refresh_points()
        self.preview.setCurrentWidget(self.canvas)
        self.canvas.set_frame(pixmap, self.points, self.columns, self.offset, fit=fit)
        knee = self.knee_errors[frame]
        details = f"Frame {frame + 1:,} / {len(self.table):,}  ·  Lowest confidence {self.confidences[frame]:.0%}"
        if np.isfinite(knee):
            details += f"  ·  Knee distance error {knee:.0%}"
        self.frame_status.setText(details)
        self._update_marker_actions()
        self._show_error(self.review.label_error)

    def _frame_image(self, frame):
        if frame in self.frame_images:
            self.frame_images.move_to_end(frame)
            return self.frame_images[frame]
        rgb = self.capture.read_frame(frame)
        if rgb is None:
            return QPixmap()
        pixmap = QPixmap.fromImage(rgb_array_to_qimage(rgb))
        frame_bytes = max(1, pixmap.width() * pixmap.height() * 4)
        limit = min(6, max(1, (24 * 1024**2) // frame_bytes))
        if len(self.frame_images) >= limit:
            self.frame_images.popitem(last=False)
        self.frame_images[frame] = pixmap
        return pixmap

    def _build_markers(self):
        with QSignalBlocker(self.marker_list):
            self.marker_list.clear()
            for index, marker in enumerate(self.columns):
                item = QListWidgetItem(" / ".join(marker), self.marker_list)
                item.setData(Qt.UserRole, marker)
                swatch = QPixmap(12, 12)
                swatch.fill(Qt.transparent)
                with QPainter(swatch) as painter:
                    painter.setRenderHint(QPainter.Antialiasing)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(marker_color(index))
                    painter.drawEllipse(1, 1, 10, 10)
                item.setIcon(QIcon(swatch))
                if marker not in self.model_markers.get((self.source.region, self.source.video), ()):
                    item.setToolTip("Generated by knee correction. You can edit this marker in the batch output.")
            if self.marker_list.count():
                self.marker_list.setCurrentRow(0)
        self._marker_selection()

    def _selected(self):
        return {tuple(item.data(Qt.UserRole)) for item in self.marker_list.selectedItems()}

    def _marker_selection(self):
        self.canvas.set_selected(self._selected())
        item = self.marker_list.currentItem()
        self.active_marker = tuple(item.data(Qt.UserRole)) if item else None
        self.canvas.active_marker = self.active_marker
        self._update_marker_actions()

    def _select_from_canvas(self, markers):
        with QSignalBlocker(self.marker_list):
            for row in range(self.marker_list.count()):
                item = self.marker_list.item(row)
                marker = tuple(item.data(Qt.UserRole))
                if len(markers) == 1 and marker in markers:
                    self.marker_list.setCurrentItem(item, QItemSelectionModel.NoUpdate)
                item.setSelected(marker in markers)
        self._marker_selection()

    def _set_mode(self, mode):
        self.mode = mode
        self.canvas.set_mode(mode)
        self.canvas.setFocus()
        self._update_tool_hint()

    def _update_tool_hint(self):
        if self.frame is None:
            self.tool_hint.clear()
            return
        if self.mode == "add" and self.active_marker:
            guidance = f"Click to place {' / '.join(self.active_marker)}."
        elif self.mode == "pan":
            guidance = "Drag to pan."
        else:
            guidance = "Drag a marker to move it. Shift-click or drag a box to select several."
        self.tool_hint.setText(f"{guidance}  Scroll to zoom · Hold Space to pan")

    def _update_marker_actions(self, message=None):
        selected = len(self._selected() & self.points.keys())
        showing_frame = self.frame is not None
        for button in self.mode_group.buttons():
            button.setEnabled(showing_frame)
        self.fit_button.setEnabled(showing_frame)
        self.copy_button.setEnabled(selected > 0)
        self.remove_button.setEnabled(selected > 0)
        self.paste_button.setEnabled(showing_frame and self.source == self.clipboard_source and bool(self.clipboard))
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.keep_button.setEnabled(bool(self.points))
        status = f"{selected} selected" if selected else "Select a marker"
        self.marker_status.setText(message or (status if showing_frame else ""))
        self._update_tool_hint()

    def _refresh_points(self):
        self.points = frame_positions(self.table, self.columns, self.frame)
        for marker in self.columns:
            edit = self.edits.get((self.source.region, self.source.video, self.frame, marker))
            if edit is not None:
                if edit.point is None:
                    self.points.pop(marker, None)
                else:
                    self.points[marker] = edit.point

    def _edit(self, updates):
        if self.frame is None or not updates:
            return
        old_values = {}
        for marker, point in updates.items():
            edit = LabelEdit(self.source.region, self.source.video, self.frame, marker, point)
            old_values[edit.key] = self.edits.get(edit.key)
            self.edits[edit.key] = edit
        self.undo_stack.append(old_values)
        self._refresh_points()
        self.canvas.set_points(self.points, self.columns)
        self._update_save()
        self._update_marker_actions()

    def _undo(self):
        if not self.undo_stack:
            return
        previous = self.undo_stack.pop()
        for key, edit in previous.items():
            if edit is None:
                self.edits.pop(key, None)
            else:
                self.edits[key] = edit
        if self.frame is not None:
            self._refresh_points()
            self.canvas.set_points(self.points, self.columns)
        self._update_save()
        _, video, frame, _ = next(iter(previous))
        location = f"frame {frame + 1:,}"
        if self.source is not None and video != self.source.video:
            location += f" of {video.name}"
        self._update_marker_actions(f"Undid change on {location}")

    def _select_all_visible(self):
        markers = set(self.points)
        self.canvas.set_selected(markers)
        self._select_from_canvas(markers)

    def _copy(self):
        copied = {marker: self.points[marker] for marker in self._selected() if marker in self.points}
        if copied:
            self.clipboard_source = self.source
            self.clipboard = copied
            self._update_marker_actions(f"{len(copied)} copied")

    def _paste(self):
        if self.frame is None or self.source != self.clipboard_source:
            return
        matching = {marker: point for marker, point in self.clipboard.items() if marker in self.columns}
        if matching:
            self._edit(matching)
            self._update_marker_actions(f"{len(matching)} pasted")

    def _delete(self):
        self._edit(dict.fromkeys(self._selected() & self.points.keys()))

    def _confirm_visible(self):
        self._edit(self.points)

    def _update_save(self):
        count = len({edit.key[:3] for edit in self.edits.values()})
        self.saved_status.setText(
            f"{count} frame{'s' if count != 1 else ''} ready to save"
            if count
            else "Edit a marker or keep the visible labels."
        )
        self.frame_save.setEnabled(count > 0)
        self.tune_save.setEnabled(
            any(
                edit.point is not None
                and (edit.key[:2] not in self.model_markers or edit.marker in self.model_markers[edit.key[:2]])
                for edit in self.edits.values()
            )
        )

    def _show_error(self, message):
        lines = message.strip().splitlines()
        details = next((line for line in reversed(lines) if "Error:" in line), lines[0] if lines else "")
        self.error.setText(details)
        self.error.setToolTip(message)
        self.error.setVisible(bool(message))

    def _save(self, fine_tune):
        self.correction = LabelCorrection(tuple(self.edits.values()), fine_tune)
        self.accept()

    def _close_capture(self):
        if self.capture is not None:
            self.capture.close()
            self.capture = None

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.WindowDeactivate:
            self.canvas.hold_pan(False)
        if kind in (QEvent.ShortcutOverride, QEvent.KeyPress, QEvent.KeyRelease):
            on_canvas = watched is self.canvas or self.canvas.isAncestorOf(watched)
            if on_canvas or watched in (self.frame_list, self.marker_list):
                if event.key() == Qt.Key_Space:
                    if kind != QEvent.ShortcutOverride and not event.isAutoRepeat():
                        self.canvas.hold_pan(kind == QEvent.KeyPress)
                    event.accept()
                    return True
                if kind != QEvent.KeyRelease:
                    action = self._editor_key_action(event, on_canvas)
                    if action is not None:
                        if kind == QEvent.KeyPress:
                            action()
                        event.accept()
                        return True
        return super().eventFilter(watched, event)

    def _editor_key_action(self, event, on_canvas):
        for shortcut, action in (
            (QKeySequence.StandardKey.Copy, self._copy),
            (QKeySequence.StandardKey.Paste, self._paste),
            (QKeySequence.StandardKey.Undo, self._undo),
        ):
            if event.matches(shortcut):
                return action
        key, modifiers = event.key(), event.modifiers()
        if key in (Qt.Key_Left, Qt.Key_Right) and (
            modifiers == Qt.AltModifier or (on_canvas and modifiers == Qt.NoModifier)
        ):
            return self.previous.click if key == Qt.Key_Left else self.next.click
        if modifiers not in (Qt.NoModifier, Qt.KeypadModifier):
            return None
        if key in self.mode_buttons:
            return self.mode_buttons[key].click
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            return self._delete
        if key == Qt.Key_A:
            return self._select_all_visible
        return None

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.fit_frame()

    def done(self, result):
        self._close_capture()
        super().done(result)
