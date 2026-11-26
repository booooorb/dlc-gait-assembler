"""Review filtered video frames and edit DeepLabCut markers before saving."""

from __future__ import annotations

from collections import OrderedDict, defaultdict

import numpy as np
from PySide6.QtCore import QAbstractListModel, QEvent, QItemSelectionModel, QSignalBlocker, Qt
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
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
    frame_confidences,
    frame_positions,
    knee_distance_errors,
    marker_columns,
)
from dlc_gait_assembly.runway.automatic.review.client.automatic_confidence_timeline import ConfidenceTimeline
from dlc_gait_assembly.runway.automatic.review.client.automatic_label_canvas import LabelCanvas, marker_color
from dlc_gait_assembly.shared.client.qt_frame_conversion import rgb_array_to_qimage
from dlc_gait_assembly.shared.client.theme import theme_application_state as theme


class ReviewFrames(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.frames = ()
        self.rows = {}
        self.edited = set()
        self.checked = set()

    def replace(self, frames):
        self.beginResetModel()
        self.frames = tuple(frames)
        self.rows = {frame: row for row, frame in enumerate(self.frames)}
        self.endResetModel()

    def rowCount(self, parent=None):
        return 0 if parent is not None and parent.isValid() else len(self.frames)

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and role == Qt.DisplayRole:
            frame = self.frames[index.row()]
            status = " · Checked" if frame in self.checked else " · Edited" if frame in self.edited else ""
            return f"Frame {frame + 1:,}{status}"
        return None

    def set_edit_status(self, edited, checked):
        changed = (self.edited ^ edited) | (self.checked ^ checked)
        self.edited = edited
        self.checked = checked.copy()
        for frame in changed & self.rows.keys():
            index = self.index(self.rows[frame], 0)
            self.dataChanged.emit(index, index, [Qt.DisplayRole])


class LabelCorrectionDialog(QDialog):
    FILTERS = ("Low confidence", "Knee distance outliers", "Either issue", "All frames", "Edited frames")
    ALL_FRAMES = 3
    EDITED_FRAMES = 4
    TRAIL_FRAMES = 12

    def __init__(self, parent, review, artifacts, media_access, preferred=None):
        super().__init__(parent)
        self.setWindowTitle("Correct DeepLabCut labels")
        self.resize(1090, 730)
        self.setMinimumWidth(820)
        self.review = review
        self.artifacts = artifacts
        self.media_access = media_access
        self.edits = {edit.key: edit for edit in review.label_draft}
        self.edited_frames = self._index_edited_frames(self.edits)
        self.saved_edit_keys = {edit.key for edit in review.saved_label_edits}
        self.applied_frames = self._index_edited_frames(self.saved_edit_keys)
        self.checked_frames = defaultdict(set)
        self.checking = False
        self.undo_stack = []
        self.clipboard = {}
        self.clipboard_source = None
        self.model_markers = {}
        self.correction = None
        self.capture = None
        self.table = None
        self.frame = None
        self.frame_confidence = None
        self.fps = 0.0
        self.frame_images = OrderedDict()
        self.recording_frames = {}
        self.offset = (0, 0)
        self.columns = {}
        self.source = None
        self.points = {}
        self.manual_markers = set()
        self.active_marker = None
        self.mode = "select"
        self._build()
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        first_edited = next(
            (index for index, source in enumerate(review.label_sources) if (source.region, source.video) in self.edited_frames),
            0,
        )
        initial_index = next((index for index, source in enumerate(review.label_sources) if source == preferred), first_edited)
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
        if self.edits:
            self.filter.setCurrentIndex(self.EDITED_FRAMES)
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
        self.show_all = self._button(side, "Show all frames", lambda: self.filter.setCurrentIndex(self.ALL_FRAMES))
        self.show_all.hide()
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
        self.trails_toggle = QCheckBox("Show trails")
        self.trails_toggle.setToolTip(
            f"Show each marker’s path {self.TRAIL_FRAMES} frames before and after the current frame. "
            "Dashed lines lead to later frames. Hover over a marker to highlight its trail."
        )
        self.trails_toggle.toggled.connect(self._update_trails)
        tools.addWidget(self.trails_toggle)
        self.fit_button = self._button(tools, "Fit", self.canvas.fit_frame)
        center.addLayout(tools)
        self.preview = QStackedWidget()
        self.preview.addWidget(self.canvas)
        self.empty_preview = QLabel()
        self.empty_preview.setAlignment(Qt.AlignCenter)
        self.empty_preview.setWordWrap(True)
        self.preview.addWidget(self.empty_preview)
        center.addWidget(self.preview, 1)
        navigation = QHBoxLayout()
        self.previous = self._button(navigation, "← Previous frame", lambda: self._navigate(-1))
        self.next = self._button(navigation, "Next frame →", lambda: self._navigate(1))
        self.previous.setToolTip("Go back one video frame (Left arrow).")
        self.next.setToolTip("Go forward one video frame (Right arrow).")
        navigation.addStretch()
        center.addLayout(navigation)
        timeline_row = QHBoxLayout()
        timeline_label = QLabel("Scrub frames · Confidence")
        self.confidence_mode = QComboBox()
        self.confidence_mode.addItems(("Mean", "Min"))
        self.confidence_mode.setAccessibleName("Timeline confidence metric")
        self.confidence_mode.setToolTip("Show the mean or lowest model keypoint confidence for each frame.")
        timeline_label.setBuddy(self.confidence_mode)
        timeline_row.addWidget(timeline_label)
        timeline_row.addStretch()
        self.timeline_value = QLabel()
        timeline_row.addWidget(self.timeline_value)
        timeline_row.addWidget(self.confidence_mode)
        center.addLayout(timeline_row)
        self.timeline = ConfidenceTimeline()
        center.addWidget(self.timeline)
        self.frame_status = QLabel()
        self.frame_status.setWordWrap(True)
        center.addWidget(self.frame_status)
        self.tool_hint = QLabel()
        self.tool_hint.setWordWrap(True)
        center.addWidget(self.tool_hint)
        body.addLayout(center, 1)

        markers = QVBoxLayout()
        markers.addWidget(QLabel("Markers"))
        legend = QLabel("● Automatic    ◆ Manual")
        legend.setToolTip("Circles show automatic labels. Diamonds show labels you edited or kept.")
        markers.addWidget(legend)
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
        self.copy_previous_button = self._button(markers, "Use previous labels (P)", self._copy_previous)
        self.copy_previous_button.setToolTip(
            "Overwrite the selected markers with their positions from the previous video frame. "
            "Use Undo to restore their current positions."
        )
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

        self.check_panel = QWidget()
        check_layout = QHBoxLayout(self.check_panel)
        check_layout.setContentsMargins(0, 0, 0, 0)
        self.check_status = QLabel()
        self.check_status.setWordWrap(True)
        check_layout.addWidget(self.check_status, 1)
        self.go_unchecked = self._button(check_layout, "Go to unchecked frame", self._go_to_unchecked)
        self.check_frame = self._button(check_layout, "Check frame and advance", self._check_current_frame)
        self.check_panel.hide()
        layout.addWidget(self.check_panel)

        footer = QHBoxLayout()
        self.saved_status = QLabel()
        footer.addWidget(self.saved_status)
        footer.addStretch()
        self._button(footer, "Cancel", self.reject)
        self.frame_save = self._button(footer, "Save corrections", lambda: self._save(False))
        self.frame_save.setToolTip("Save the edits in this run so you can reopen them later.")
        self.tune_save = self._button(footer, "Review and fine-tune", self._review_or_fine_tune)
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
        self.frame_list.selectionModel().currentChanged.connect(self._frame_selected)
        self.timeline.frame_requested.connect(self._seek_frame)
        self.confidence_mode.currentIndexChanged.connect(self._update_confidence_plot)
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
        self.frame_confidence = None
        self.fps = 0.0
        self.source = self.review.label_sources[index]
        self._show_error(self.review.label_error)
        try:
            self.table, raw, self.offset = self.artifacts.label_artifacts(self.source)
            self.columns = marker_columns(self.table)
            self.model_markers[self.source.region, self.source.video] = set(marker_columns(raw))
            self.capture = self.media_access.open_video(self.source.video)
            count = self.capture.info.frame_count or len(self.table)
            if count != len(self.table) or len(raw) != len(self.table):
                raise ValueError(f"The video has {count} frames and its tracking table has {len(self.table)} rows.")
            self.knee_errors = knee_distance_errors(raw, self.review.knee_settings)
            self.frame_confidence = frame_confidences(raw)
            self.fps = getattr(self.capture.info, "fps", 0.0)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._close_capture()
            self.table = None
            self.columns = {}
            self._show_error(str(exc))
        with QSignalBlocker(self.timeline):
            self.timeline.set_recording(len(self.table) if self.table is not None else 0, self.fps)
        self.confidence_mode.setEnabled(self.frame_confidence is not None and self.frame_confidence.mean is not None)
        self._update_confidence_plot()
        self._build_markers()
        self._filter_frames(preferred_frame=self.recording_frames.get(self.source))
        self._update_save()

    @property
    def recording_key(self):
        return (self.source.region, self.source.video) if self.source is not None else None

    @staticmethod
    def _index_edited_frames(edit_keys):
        frames_by_recording = defaultdict(set)
        for region, video, frame, _marker in edit_keys:
            frames_by_recording[region, video].add(frame)
        return dict(frames_by_recording)

    def _edited_frames_for_recording(self):
        draft = self.edited_frames.get(self.recording_key, set())
        return draft if self.checking else draft | self.applied_frames.get(self.recording_key, set())

    def _filter_frames(self, *_, preferred_frame=None):
        old_frame = self.frame
        mode = self.filter.currentIndex()
        edited = self._edited_frames_for_recording()
        with QSignalBlocker(self.frame_list.selectionModel()):
            self.frame_model.set_edit_status(edited, self.checked_frames[self.recording_key])
            if self.table is None:
                self.frame_model.replace(())
            elif mode == self.EDITED_FRAMES:
                self.frame_model.replace(sorted(frame for frame in edited if 0 <= frame < len(self.table)))
            elif mode == self.ALL_FRAMES:
                self.frame_model.replace(range(len(self.table)))
            else:
                minimum = self.frame_confidence.minimum
                low = minimum < self.confidence.value() / 100
                knee = self.knee_errors >= self.distance.value() / 100
                matches = (low, knee, low | knee)[mode]
                order = (minimum, -self.knee_errors, np.arange(len(low)))[mode]
                indices = np.argsort(order, kind="stable")
                self.frame_model.replace(indices[matches[indices]])
        self.confidence_row.setVisible(mode in (0, 2))
        self.distance_row.setVisible(mode in (1, 2))
        frames = self.frame_model.frames
        count = len(frames)
        category = "edited" if mode == self.EDITED_FRAMES else "matching"
        self.frame_summary.setText(f"{count:,} {category} frame{'s' if count != 1 else ''}")
        self.show_all.setVisible(not count and self.table is not None and mode != self.ALL_FRAMES)
        if preferred_frame is not None and self.table is not None:
            self._seek_frame(preferred_frame)
        elif frames:
            self._seek_frame(old_frame if old_frame in self.frame_model.rows else int(frames[0]))
        else:
            message = "No frames match this filter."
            if self.table is None:
                message = "This recording could not be opened."
            elif mode == self.EDITED_FRAMES:
                message = "No edited frames in this recording."
            elif mode == 1 and not np.isfinite(self.knee_errors).any():
                message = "Knee distances are unavailable for this recording."
            self._show_empty_frame(message)
            self.timeline.set_current_frame(None)
            self._update_timeline_value()
            self._update_navigation()
            self._update_check_controls()

    def _show_empty_frame(self, message):
        self.frame = None
        self.points = {}
        self.manual_markers = set()
        self.frame_status.clear()
        self.canvas.set_frame(QPixmap(), {}, (), self.offset)
        self.canvas.set_trails({})
        self.empty_preview.setText(message)
        self.preview.setCurrentWidget(self.empty_preview)
        self._update_marker_actions()

    def _navigate(self, step):
        frame = self.timeline.value() + step
        if self.table is not None and 0 <= frame < len(self.table):
            self._seek_frame(frame)
            self.canvas.setFocus()

    def _update_navigation(self):
        frame = self.timeline.value()
        self.previous.setEnabled(self.table is not None and frame > 0)
        self.next.setEnabled(self.table is not None and frame + 1 < len(self.table))

    def _frame_selected(self, current, _previous):
        if current.isValid():
            self._select_frame(int(self.frame_model.frames[current.row()]))

    def _seek_frame(self, frame):
        row = self.frame_model.rows.get(frame)
        if row is None:
            self.frame_list.selectionModel().clear()
        elif row != self.frame_list.currentIndex().row():
            self.frame_list.setCurrentIndex(self.frame_model.index(row, 0))
            return
        self._select_frame(frame)

    def _select_frame(self, frame):
        if self.capture is None or not 0 <= frame < len(self.table):
            return
        with QSignalBlocker(self.timeline):
            self.timeline.set_current_frame(frame)
        self._update_navigation()
        if self.frame != frame:
            self._show_frame(frame)
        self._update_timeline_value()
        self._update_check_controls()

    def _show_frame(self, frame):
        pixmap = self._frame_image(frame)
        if pixmap.isNull():
            self._show_empty_frame(f"Frame {frame + 1:,} could not be read. Select another frame.")
            self._show_error(self.review.label_error)
            return
        fit = self.frame is None
        self.frame = frame
        self._refresh_points()
        self.preview.setCurrentWidget(self.canvas)
        self.canvas.set_frame(
            pixmap, self.points, self.columns, self.offset, manual_markers=self.manual_markers, fit=fit
        )
        self._update_trails()
        knee = self.knee_errors[frame]
        details = f"Frame {frame + 1:,} / {len(self.table):,}"
        if self.fps > 0:
            details += f"  ·  {frame / self.fps:,.2f} s"
        if self.frame_confidence.mean is not None:
            details += f"  ·  Lowest confidence {self.frame_confidence.minimum[frame]:.0%}"
        if np.isfinite(knee):
            details += f"  ·  Knee distance error {knee:.0%}"
        self.frame_status.setText(details)
        self._update_marker_actions()
        self._show_error(self.review.label_error)

    def _timeline_scores(self):
        if self.frame_confidence is None or self.frame_confidence.mean is None:
            return None
        return self.frame_confidence.minimum if self.confidence_mode.currentIndex() else self.frame_confidence.mean

    def _update_confidence_plot(self):
        self.timeline.set_scores(self._timeline_scores())
        self._update_timeline_value()

    def _update_timeline_value(self):
        scores = self._timeline_scores()
        self.timeline_value.setText(f"{scores[self.frame]:.0%}" if scores is not None and self.frame is not None else "")

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
        selected = self._selected()
        visible_selected = selected & self.points.keys()
        showing_frame = self.frame is not None
        for button in self.mode_group.buttons():
            button.setEnabled(showing_frame)
        self.fit_button.setEnabled(showing_frame)
        self.copy_button.setEnabled(bool(visible_selected))
        self.remove_button.setEnabled(bool(visible_selected))
        self.paste_button.setEnabled(showing_frame and self.source == self.clipboard_source and bool(self.clipboard))
        self.copy_previous_button.setEnabled(showing_frame and self.frame > 0 and bool(selected))
        self.undo_button.setEnabled(bool(self.undo_stack))
        self.keep_button.setEnabled(bool(self.points))
        status = f"{len(selected)} selected" if selected else "Select a marker"
        self.marker_status.setText(message or (status if showing_frame else ""))
        self._update_tool_hint()

    def _positions_at(self, frame):
        points = frame_positions(self.table, self.columns, frame)
        for marker in self.columns:
            edit = self.edits.get((*self.recording_key, frame, marker))
            if edit is not None:
                if edit.point is None:
                    points.pop(marker, None)
                else:
                    points[marker] = edit.point
        return points

    def _refresh_points(self):
        self.points = self._positions_at(self.frame)
        self.manual_markers = {
            marker for marker in self.points
            if (key := (*self.recording_key, self.frame, marker)) in self.edits or key in self.saved_edit_keys
        }

    def _update_trails(self):
        if self.frame is None or not self.trails_toggle.isChecked():
            self.canvas.set_trails({})
            return
        start = max(0, self.frame - self.TRAIL_FRAMES)
        stop = min(len(self.table), self.frame + self.TRAIL_FRAMES + 1)
        middle = self.frame - start
        window = self.table.iloc[start:stop]
        trails = {}
        for marker, columns in self.columns.items():
            positions = window.loc[:, [columns["x"], columns["y"]]].to_numpy(dtype=float)
            points = []
            for frame, point in enumerate(positions, start):
                edit = self.edits.get((*self.recording_key, frame, marker))
                points.append(edit.point if edit is not None else tuple(point) if np.isfinite(point).all() else None)
            trails[marker] = points[:middle + 1], points[middle:]
        self.canvas.set_trails(trails)

    def _edits_changed(self, key, frame):
        self.checked_frames[key].discard(frame)
        previous = self._edited_frames_for_recording()
        self.edited_frames = self._index_edited_frames(self.edits)
        edited = self._edited_frames_for_recording()
        if self.filter.currentIndex() == self.EDITED_FRAMES and previous != edited:
            self._filter_frames(preferred_frame=self.frame)
        self.frame_model.set_edit_status(edited, self.checked_frames[self.recording_key])
        self._update_save()

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
        self.canvas.set_points(self.points, self.columns, self.manual_markers)
        self._update_trails()
        self._edits_changed(self.recording_key, self.frame)
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
            self.canvas.set_points(self.points, self.columns, self.manual_markers)
            self._update_trails()
        region, video, frame, _ = next(iter(previous))
        self._edits_changed((region, video), frame)
        location = f"frame {frame + 1:,}"
        if self.recording_key != (region, video):
            location += f" of {region} · {video.name}"
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

    def _copy_previous(self):
        if self.frame is None or self.frame == 0:
            return
        previous = self._positions_at(self.frame - 1)
        updates = {marker: previous[marker] for marker in self._selected() & previous.keys()}
        if updates:
            self._edit(updates)
            self._update_marker_actions(f"{len(updates)} copied from frame {self.frame:,}")
        else:
            self._update_marker_actions("No selected labels on the previous frame")

    def _delete(self):
        self._edit(dict.fromkeys(self._selected() & self.points.keys()))

    def _confirm_visible(self):
        self._edit(self.points)

    def _update_save(self):
        count = sum(map(len, self.edited_frames.values()))
        self.saved_status.setText(
            f"{count} frame{'s' if count != 1 else ''} ready to save"
            if count
            else "Edit a marker or keep the visible labels."
        )
        self.frame_save.setEnabled(count > 0)
        self.can_fine_tune = any(
            edit.point is not None
            and (edit.key[:2] not in self.model_markers or edit.marker in self.model_markers[edit.key[:2]])
            for edit in self.edits.values()
        )
        self._update_check_controls()

    def _update_check_controls(self):
        if not self.checking:
            self.tune_save.setEnabled(self.can_fine_tune)
            return
        total = sum(map(len, self.edited_frames.values()))
        checked = sum(map(len, self.checked_frames.values()))
        message = "Inspect each frame before training." if checked < total else "Review complete."
        self.check_status.setText(f"{checked:,} of {total:,} edited frames checked. {message}")
        unchecked = self.frame in self.edited_frames.get(self.recording_key, ()) and (
            self.frame not in self.checked_frames[self.recording_key]
        )
        self.check_frame.setEnabled(unchecked)
        self.go_unchecked.setEnabled(checked < total and not unchecked)
        self.tune_save.setEnabled(self.can_fine_tune and checked == total)

    def _review_or_fine_tune(self):
        if self.checking:
            self._save(True)
            return
        self.checking = True
        self.check_panel.show()
        self.tune_save.setText("Start fine-tuning")
        if self.filter.currentIndex() == self.EDITED_FRAMES:
            self._filter_frames()
        self._go_to_unchecked()
        self._update_check_controls()

    def _go_to_unchecked(self):
        self.filter.setCurrentIndex(self.EDITED_FRAMES)
        for index, source in enumerate(self.review.label_sources):
            key = source.region, source.video
            if key not in self.edited_frames:
                continue
            frame = min(self.edited_frames[key] - self.checked_frames[key], default=None)
            if frame is not None:
                self.recording.setCurrentIndex(index)
                self._seek_frame(frame)
                return

    def _check_current_frame(self):
        self.checked_frames[self.recording_key].add(self.frame)
        self.frame_model.set_edit_status(self.edited_frames[self.recording_key], self.checked_frames[self.recording_key])
        self._go_to_unchecked()
        self._update_check_controls()

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
            editor_focus = on_canvas or watched in (self.frame_list, self.marker_list)
            navigation_focus = editor_focus or watched is self or isinstance(watched, (QPushButton, QCheckBox))
            modifiers = event.modifiers() & ~Qt.KeypadModifier
            if (
                navigation_focus and kind != QEvent.KeyRelease
                and event.key() in (Qt.Key_Left, Qt.Key_Right) and modifiers in (Qt.NoModifier, Qt.AltModifier)
            ):
                if kind == QEvent.KeyPress:
                    self._navigate(-1 if event.key() == Qt.Key_Left else 1)
                event.accept()
                return True
            if editor_focus or watched is self.timeline:
                if event.key() == Qt.Key_Space:
                    if kind != QEvent.ShortcutOverride and not event.isAutoRepeat():
                        self.canvas.hold_pan(kind == QEvent.KeyPress)
                    event.accept()
                    return True
                if kind != QEvent.KeyRelease:
                    action = self._editor_key_action(event)
                    if action is not None:
                        if kind == QEvent.KeyPress:
                            action()
                        event.accept()
                        return True
        return super().eventFilter(watched, event)

    def _editor_key_action(self, event):
        for shortcut, action in (
            (QKeySequence.StandardKey.Copy, self._copy),
            (QKeySequence.StandardKey.Paste, self._paste),
            (QKeySequence.StandardKey.Undo, self._undo),
        ):
            if event.matches(shortcut):
                return action
        key, modifiers = event.key(), event.modifiers()
        if modifiers not in (Qt.NoModifier, Qt.KeypadModifier):
            return None
        if key in self.mode_buttons:
            return self.mode_buttons[key].click
        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            return self._delete
        if key == Qt.Key_A:
            return self._select_all_visible
        if key == Qt.Key_P:
            return self._copy_previous
        return None

    def showEvent(self, event):
        super().showEvent(event)
        self.canvas.fit_frame()

    def done(self, result):
        self._close_capture()
        super().done(result)
