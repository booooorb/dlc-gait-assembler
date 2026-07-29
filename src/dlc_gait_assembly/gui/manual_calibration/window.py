from __future__ import annotations

from collections.abc import Iterable
from math import hypot, isfinite
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.manual_calibration.preview import CalibrationPreviewView
from dlc_gait_assembly.gui.shared.formatting import format_milliseconds
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.interaction import (
    add_shortcut,
    animate_button_emphasis,
    set_tooltip,
)
from dlc_gait_assembly.gui.video_editor.timeline import TrimTimelineSlider
from dlc_gait_assembly.services.domain.calibration import (
    CalibrationReport,
    CalibrationStick,
    calculate_calibration_report,
)
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.output_documents import write_calibration_conversion_export
from dlc_gait_assembly.services.project_paths import find_project_root, make_session_output_dir

try:
    import cv2
except ImportError:
    cv2 = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class ManualCalibrationWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ManualCalibrationWidget")
        self._project_root = find_project_root(__file__)
        self._capture = None
        self._current_media: Path | None = None
        self._calibration_sticks_by_media: dict[str, tuple[CalibrationStick, ...]] = {}
        self._timeline_ms_by_media: dict[str, int] = {}
        self._duration_ms = 0
        self._fps = 0.0
        self._frame_count = 0
        self._loading_slider = False
        self._loading_media = False
        self._pending_frame_ms: int | None = None
        self._frame_load_timer = QTimer(self)
        self._frame_load_timer.setSingleShot(True)
        self._frame_load_timer.setInterval(35)
        self._frame_load_timer.timeout.connect(self._load_pending_frame)

        self._build_ui()
        self._install_shortcuts()
        self._connect_signals()
        self._apply_style()
        self._emphasize_calibration_tool("x")
        self._update_calibration_results()

    def can_close(self, parent=None) -> bool:
        return True

    def release_resources(self) -> None:
        self._save_media_state()
        self._release_capture()
        self._duration_ms = 0
        self._fps = 0.0
        self._frame_count = 0
        if hasattr(self, "preview"):
            self._loading_media = True
            try:
                self.preview.set_frame(None)
            finally:
                self._loading_media = False

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter)

        left_panel = QWidget()
        left_panel.setObjectName("WorkspaceSidebar")
        left_panel.setMinimumWidth(320)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        media_box = QGroupBox("Calibration frame")
        media_box.setMaximumHeight(245)
        media_layout = QVBoxLayout(media_box)
        media_layout.setSpacing(8)
        media_buttons = QHBoxLayout()
        media_buttons.setSpacing(8)
        self.open_media_button = QPushButton("Add")
        self.open_media_button.setObjectName("OpenMediaButton")
        set_tooltip(self.open_media_button, "Add calibration images or videos.", "Ctrl+O")
        self.remove_media_button = QPushButton("Remove")
        self.remove_media_button.setObjectName("RemoveButton")
        set_tooltip(self.remove_media_button, "Remove selected calibration files.", "Ctrl+Backspace")
        self.clear_calibration_button = QPushButton("Clear")
        self.clear_calibration_button.setObjectName("ClearButton")
        set_tooltip(self.clear_calibration_button, "Clear calibration markers for the current file.", "Ctrl+L")
        media_buttons.addWidget(self.open_media_button, 1)
        media_buttons.addWidget(self.remove_media_button, 1)
        media_buttons.addWidget(self.clear_calibration_button, 1)
        media_layout.addLayout(media_buttons)
        self.media_list = QListWidget()
        self.media_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.media_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.media_list.setTextElideMode(Qt.ElideNone)
        self.media_list.setUniformItemSizes(True)
        self.media_list.setAlternatingRowColors(False)
        list_font = self.media_list.font()
        list_font.setPointSize(9)
        self.media_list.setFont(list_font)
        media_layout.addWidget(self.media_list, 1)
        self.media_label = QLabel("No calibration images or videos loaded.")
        self.media_label.setWordWrap(True)
        self.media_label.setObjectName("MutedLabel")
        media_layout.addWidget(self.media_label)
        left_layout.addWidget(media_box)

        results_box = QGroupBox("SOP checks")
        results_layout = QVBoxLayout(results_box)
        self.results_label = QLabel()
        self.results_label.setObjectName("ResultsLabel")
        self.results_label.setWordWrap(True)
        self.results_label.setTextFormat(Qt.RichText)
        self.results_label.setOpenExternalLinks(False)
        results_scroll = QScrollArea()
        results_scroll.setObjectName("ResultsScroll")
        results_scroll.setWidgetResizable(True)
        results_scroll.setFrameShape(QFrame.NoFrame)
        results_scroll.setWidget(self.results_label)
        results_layout.addWidget(results_scroll)
        self.export_conversion_button = QPushButton("Export conversion map")
        self.export_conversion_button.setObjectName("ExportButton")
        results_layout.addWidget(self.export_conversion_button)
        left_layout.addWidget(results_box, 1)

        right_panel = QWidget()
        right_panel.setObjectName("WorkspaceCanvas")
        right_panel.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        self.preview_title = QLabel("Open a calibration image or video.")
        self.preview_title.setObjectName("PreviewTitle")
        right_layout.addWidget(self.preview_title)

        tools_bar = QFrame()
        tools_bar.setObjectName("OperationsBar")
        tools_layout = QHBoxLayout(tools_bar)
        tools_layout.setContentsMargins(12, 8, 12, 8)
        tools_layout.setSpacing(12)
        tool_buttons_row = QHBoxLayout()
        tool_buttons_row.setContentsMargins(0, 0, 0, 0)
        tool_buttons_row.setSpacing(8)
        self.x_tool_button = _make_tool_button("X-calibration stick", theme.TOOL_3)
        set_tooltip(self.x_tool_button, "Draw an x-axis calibration stick.", "Ctrl+1")
        self.y_tool_button = _make_tool_button("Y-calibration stick", theme.TOOL_2)
        set_tooltip(self.y_tool_button, "Draw a y-axis calibration stick.", "Ctrl+2")
        self.cm_tool_button = _make_tool_button("Marker", theme.TOOL_1)
        set_tooltip(self.cm_tool_button, "Add calibration markers to a stick.", "Ctrl+3")
        self.x_tool_button.setChecked(True)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.x_tool_button)
        self.tool_group.addButton(self.y_tool_button)
        self.tool_group.addButton(self.cm_tool_button)
        tool_buttons_row.addWidget(self.x_tool_button)
        tool_buttons_row.addWidget(self.y_tool_button)
        tool_buttons_row.addWidget(self.cm_tool_button)
        self.marker_gap_frame = QFrame()
        self.marker_gap_frame.setObjectName("MarkerGapInline")
        marker_row = QHBoxLayout(self.marker_gap_frame)
        marker_row.setContentsMargins(8, 4, 8, 4)
        marker_row.setSpacing(8)
        marker_row.addWidget(QLabel("Marker gap"))
        self.marker_interval_spin = QDoubleSpinBox()
        self.marker_interval_spin.setRange(0.000001, 100000.0)
        self.marker_interval_spin.setDecimals(4)
        self.marker_interval_spin.setSingleStep(1.0)
        self.marker_interval_spin.setValue(1.0)
        self.marker_interval_spin.setMaximumWidth(92)
        set_tooltip(self.marker_interval_spin, "Measurement represented by the distance between two adjacent markers.")
        marker_row.addWidget(self.marker_interval_spin)
        self.marker_unit_combo = QComboBox()
        self.marker_unit_combo.addItems(["cm", "inches"])
        self.marker_unit_combo.setMaximumWidth(82)
        set_tooltip(self.marker_unit_combo, "Measurement unit for the marker gap.")
        marker_row.addWidget(self.marker_unit_combo)
        tool_buttons_row.addWidget(self.marker_gap_frame)
        tool_buttons_row.addStretch(1)
        tools_layout.addLayout(tool_buttons_row, 1)
        self.settings_frame = QFrame()
        self.settings_frame.setObjectName("InlineSettings")
        self.settings_frame.setMaximumWidth(230)
        settings_layout = QVBoxLayout(self.settings_frame)
        settings_layout.setContentsMargins(8, 4, 8, 4)
        settings_layout.setSpacing(4)
        margin_row = QHBoxLayout()
        margin_row.setContentsMargins(0, 0, 0, 0)
        margin_row.setSpacing(8)
        margin_row.addWidget(QLabel("Margin of error"))
        self.tau_spin = QDoubleSpinBox()
        self.tau_spin.setRange(0.1, 20.0)
        self.tau_spin.setDecimals(2)
        self.tau_spin.setSingleStep(0.25)
        self.tau_spin.setSuffix("%")
        self.tau_spin.setValue(2.0)
        self.tau_spin.setMaximumWidth(82)
        set_tooltip(self.tau_spin, "Margin of calibration error.")
        margin_row.addWidget(self.tau_spin)
        settings_layout.addLayout(margin_row)
        self.euclidean_lengths_checkbox = QCheckBox("Euclidean distance")
        self.euclidean_lengths_checkbox.setChecked(True)
        set_tooltip(self.euclidean_lengths_checkbox, "Measure each marker segment as the full distance between two points instead of only x/y axis distance.", "Ctrl+E")
        settings_layout.addWidget(self.euclidean_lengths_checkbox)
        tools_layout.addWidget(self.settings_frame, 0, Qt.AlignTop)
        right_layout.addWidget(tools_bar)

        self.preview = CalibrationPreviewView()
        right_layout.addWidget(self.preview, 1)

        timeline_row = QHBoxLayout()
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(180)
        self.timeline = TrimTimelineSlider()
        self.timeline.setRange(0, 0)
        self.timeline.setEnabled(False)
        timeline_row.addWidget(self.time_label)
        timeline_row.addWidget(self.timeline, 1)
        right_layout.addLayout(timeline_row)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([390, 890])

    def _install_shortcuts(self) -> None:
        self._shortcuts = [
            add_shortcut(self, "Ctrl+O", self._open_media),
            add_shortcut(self, "Ctrl+Backspace", self._remove_selected_media),
            add_shortcut(self, "Ctrl+L", self._clear_calibration),
            add_shortcut(self, "Ctrl+1", lambda: self._activate_tool_button(self.x_tool_button, "x")),
            add_shortcut(self, "Ctrl+2", lambda: self._activate_tool_button(self.y_tool_button, "y")),
            add_shortcut(self, "Ctrl+3", lambda: self._activate_tool_button(self.cm_tool_button, "cm")),
            add_shortcut(self, "Ctrl+E", self.euclidean_lengths_checkbox.toggle),
        ]

    def _connect_signals(self) -> None:
        self.open_media_button.clicked.connect(self._open_media)
        self.remove_media_button.clicked.connect(self._remove_selected_media)
        self.clear_calibration_button.clicked.connect(self._clear_calibration)
        self.media_list.currentItemChanged.connect(self._media_selection_changed)
        self.x_tool_button.clicked.connect(lambda: self._set_active_tool("x"))
        self.y_tool_button.clicked.connect(lambda: self._set_active_tool("y"))
        self.cm_tool_button.clicked.connect(lambda: self._set_active_tool("cm"))
        self.tau_spin.valueChanged.connect(self._update_calibration_results)
        self.euclidean_lengths_checkbox.toggled.connect(self._update_calibration_results)
        self.marker_interval_spin.valueChanged.connect(self._update_calibration_results)
        self.marker_unit_combo.currentTextChanged.connect(self._update_calibration_results)
        self.preview.sticks_changed.connect(self._on_preview_sticks_changed)
        self.preview.stick_delete_requested.connect(self._confirm_delete_calibration_stick)
        self.timeline.valueChanged.connect(self._timeline_changed)
        self.timeline.sliderReleased.connect(self._flush_pending_frame)
        self.export_conversion_button.clicked.connect(self._export_conversion_map)

    def _apply_style(self) -> None:
        if hasattr(self, "x_tool_button"):
            self.x_tool_button.setStyleSheet(_tool_button_style(theme.TOOL_3))
            self.y_tool_button.setStyleSheet(_tool_button_style(theme.TOOL_2))
            self.cm_tool_button.setStyleSheet(_tool_button_style(theme.TOOL_1))
        self.setStyleSheet(
            theme.workspace_stylesheet(
                "ManualCalibrationWidget",
                """
            QLabel#ResultsLabel {
                background: {theme.SURFACE};
            }
            QScrollArea#ResultsScroll,
            QScrollArea#ResultsScroll > QWidget,
            QScrollArea#ResultsScroll > QWidget > QWidget {
                background: {theme.SURFACE};
                border: 0;
            }
            QPushButton#ResetButton {
                padding: 2px 5px;
                font-size: 10px;
            }
            QPushButton#PreviewResetZoomButton {
                background: {theme.BACKGROUND};
                border: 1px solid {theme.TEXT};
                border-radius: 3px;
                color: {theme.TEXT};
                font-size: 10px;
                font-weight: 700;
                padding: 2px 5px;
            }
            QPushButton#PreviewResetZoomButton:hover {
                background: {theme.PANEL};
                color: {theme.TEXT};
            }
            QGraphicsView {
                border: 1px solid {theme.BORDER};
                border-radius: 2px;
                background: {theme.CANVAS};
            }
                """
            )
        )
        icon_specs = (
            (self.open_media_button, "plus", theme.TEXT),
            (self.remove_media_button, "trash", theme.STATUS_ERROR),
            (self.clear_calibration_button, "clear", theme.STATUS_ERROR),
            (self.export_conversion_button, "download", theme.TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))
        if hasattr(self, "results_label"):
            self._update_calibration_results()

    def _open_media(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))
        filenames, _ = QFileDialog.getOpenFileNames(
            self,
            "Add calibration images or videos",
            str(self._project_root),
            f"Image and video files ({extensions});;All files (*)",
        )
        if not filenames:
            return

        self._add_media_paths(Path(filename) for filename in filenames)

    def _add_media_paths(self, paths: Iterable[str | Path]) -> None:
        unsupported: list[str] = []
        first_added_row: int | None = None
        for candidate in paths:
            path = Path(candidate).expanduser().resolve()
            if path.suffix.lower() not in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS:
                unsupported.append(path.name)
                continue
            if self._media_item_for_path(path) is not None:
                continue

            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(Qt.UserRole, str(path))
            self.media_list.addItem(item)
            if first_added_row is None:
                first_added_row = self.media_list.count() - 1

        if unsupported:
            QMessageBox.warning(self, "Unsupported files", "Skipped unsupported files:\n" + "\n".join(unsupported))

        if first_added_row is not None and self.media_list.currentItem() is None:
            self.media_list.setCurrentRow(first_added_row)
        self._update_media_summary()

    def _media_selection_changed(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        self._save_media_state(previous)
        if current is None:
            self._release_capture()
            self._current_media = None
            self._duration_ms = 0
            self.timeline.setRange(0, 0)
            self.timeline.setEnabled(False)
            self.time_label.setText("00:00.000 / 00:00.000")
            self.preview_title.setText("Open a calibration image or video.")
            self.preview.set_frame(None)
            self._update_media_summary()
            return

        self._load_media(Path(current.data(Qt.UserRole)))

    def _load_media(self, path: Path) -> None:
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            self._load_image(path)
        elif suffix in VIDEO_EXTENSIONS:
            self._load_video(path)
        else:
            QMessageBox.warning(self, "Unsupported file", "Choose a supported image or video file.")

    def _remove_selected_media(self) -> None:
        selected_items = self.media_list.selectedItems()
        if not selected_items:
            return

        current = self.media_list.currentItem()
        current_path_key = current.data(Qt.UserRole) if current is not None else None
        self._save_media_state(current)
        selected_path_keys = {item.data(Qt.UserRole) for item in selected_items}
        first_removed_row = min(self.media_list.row(item) for item in selected_items)
        blocker = QSignalBlocker(self.media_list)
        for item in sorted(selected_items, key=self.media_list.row, reverse=True):
            path_key = item.data(Qt.UserRole)
            self._calibration_sticks_by_media.pop(path_key, None)
            self._timeline_ms_by_media.pop(path_key, None)
            self.media_list.takeItem(self.media_list.row(item))

        if self.media_list.count() == 0:
            del blocker
            self._release_capture()
            self._current_media = None
            self._duration_ms = 0
            self.timeline.setRange(0, 0)
            self.timeline.setEnabled(False)
            self.time_label.setText("00:00.000 / 00:00.000")
            self.preview_title.setText("Open a calibration image or video.")
            self.preview.set_frame(None)
        else:
            target_item = None
            if current_path_key is not None and current_path_key not in selected_path_keys:
                target_item = self._media_item_for_path(Path(current_path_key))
            if target_item is not None:
                self.media_list.setCurrentItem(target_item)
            else:
                self.media_list.setCurrentRow(min(first_removed_row, self.media_list.count() - 1))
            new_current = self.media_list.currentItem()
            del blocker
            if new_current is not None and new_current.data(Qt.UserRole) != current_path_key:
                self._load_media(Path(new_current.data(Qt.UserRole)))
        self._update_calibration_results()
        self._update_media_summary()

    def _load_image(self, path: Path) -> None:
        self._release_capture()
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.warning(self, "Could not open image", str(path))
            return

        self._loading_media = True
        try:
            self._current_media = path
            self._duration_ms = 0
            self.timeline.setRange(0, 0)
            self.timeline.setEnabled(False)
            self.time_label.setText("Image")
            self.preview_title.setText(path.name)
            self.preview.set_frame(image)
            self.preview.set_calibration_sticks(self._calibration_sticks_by_media.get(str(path), ()))
        finally:
            self._loading_media = False

        self._save_media_state()
        self._update_calibration_results()
        self._update_media_summary()

    def _load_video(self, path: Path) -> None:
        if cv2 is None:
            QMessageBox.critical(self, "OpenCV is missing", "Install the conda environment first: conda env create -f GAIT_ASSEMBLER.yaml")
            return

        self._release_capture()
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            QMessageBox.warning(self, "Could not open video", str(path))
            return

        self._loading_media = True
        try:
            self._capture = capture
            self._current_media = path
            self._fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            self._frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            self._duration_ms = int((self._frame_count / self._fps) * 1000) if self._fps > 0 and self._frame_count > 0 else 0
            self.timeline.setRange(0, max(0, self._duration_ms))
            self.timeline.setSingleStep(100)
            self.timeline.setPageStep(1000)
            self.timeline.setEnabled(self._duration_ms > 0)
            self.preview_title.setText(path.name)
            saved_ms = min(self._timeline_ms_by_media.get(str(path), 0), max(0, self._duration_ms))
            self._set_timeline_value(saved_ms)
            self._load_frame_at(saved_ms)
            self.preview.set_calibration_sticks(self._calibration_sticks_by_media.get(str(path), ()))
        finally:
            self._loading_media = False

        self._save_media_state()
        self._update_calibration_results()
        self._update_media_summary()

    def _timeline_changed(self, value: int) -> None:
        if self._loading_slider:
            return
        if self._current_media is not None:
            self._timeline_ms_by_media[str(self._current_media)] = value
        self._queue_frame_at(value)

    def _queue_frame_at(self, ms: int) -> None:
        self._pending_frame_ms = int(ms)
        if self.timeline.isSliderDown():
            if not self._frame_load_timer.isActive():
                self._frame_load_timer.start()
            return

        self._flush_pending_frame()

    def _flush_pending_frame(self) -> None:
        self._frame_load_timer.stop()
        self._load_pending_frame()

    def _load_pending_frame(self) -> None:
        if self._pending_frame_ms is None:
            return

        ms = self._pending_frame_ms
        self._pending_frame_ms = None
        self._load_frame_at(ms)

    def _load_frame_at(self, ms: int) -> None:
        if self._capture is None or cv2 is None:
            return

        if self._fps > 0 and self._frame_count > 0:
            frame_index = max(0, min(self._frame_count - 1, int(round((ms / 1000.0) * self._fps))))
            self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        else:
            self._capture.set(cv2.CAP_PROP_POS_MSEC, float(ms))
        ok, frame = self._capture.read()
        if not ok:
            frame_count = int(self._capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frame_count > 0:
                self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_count - 1)
                ok, frame = self._capture.read()
        if not ok:
            QMessageBox.warning(self, "Could not read frame", "Try a different timestamp or file.")
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        self.preview.set_frame(image)
        self.time_label.setText(
            f"{format_milliseconds(ms)} / {format_milliseconds(self._duration_ms)}"
        )

    def _set_timeline_value(self, value: int) -> None:
        self._loading_slider = True
        self.timeline.setValue(value)
        self._loading_slider = False

    def _clear_calibration(self) -> None:
        if not self.preview.calibration_sticks():
            return

        if QMessageBox.question(
            self,
            "Clear calibration?",
            "Remove all calibration sticks and markers from this frame?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self.preview.clear_calibration()
        if self._current_media is not None:
            self._calibration_sticks_by_media[str(self._current_media)] = ()

    def _confirm_delete_calibration_stick(self, key: str, label: str) -> None:
        if QMessageBox.question(
            self,
            "Delete calibration stick?",
            f"Delete {label} and all of its markers?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self.preview.delete_stick(key)

    def _set_active_tool(self, name: str) -> None:
        self.preview.set_mode(name)
        self._emphasize_calibration_tool(name)

    def _emphasize_calibration_tool(self, active_name: str) -> None:
        for name, button in (
            ("x", self.x_tool_button),
            ("y", self.y_tool_button),
            ("cm", self.cm_tool_button),
        ):
            animate_button_emphasis(
                button,
                name == active_name,
                resting_height=30,
                emphasized_height=40,
            )

    def _activate_tool_button(self, button: QToolButton, name: str) -> None:
        button.setChecked(True)
        self._set_active_tool(name)

    def _on_preview_sticks_changed(self) -> None:
        if self._loading_media:
            return

        self._save_media_state()
        self._update_calibration_results()
        self._update_media_summary()

    def _update_calibration_results(self) -> None:
        sticks = self._all_calibration_sticks() if hasattr(self, "preview") else []
        report = calculate_calibration_report(
            sticks,
            self.tau_spin.value() if hasattr(self, "tau_spin") else 2.0,
            self.euclidean_lengths_checkbox.isChecked() if hasattr(self, "euclidean_lengths_checkbox") else False,
            self.marker_interval_spin.value() if hasattr(self, "marker_interval_spin") else 1.0,
            self.marker_unit_combo.currentText() if hasattr(self, "marker_unit_combo") else "cm",
        )
        if hasattr(self, "preview") and not self._loading_media:
            self._update_location_failure_highlights(report)
        self.results_label.setText(_report_to_html(report))
        if hasattr(self, "export_conversion_button"):
            self.export_conversion_button.setEnabled(bool(report.view_axis))

    def _export_conversion_map(self) -> None:
        sticks = self._all_calibration_sticks()
        report = calculate_calibration_report(
            sticks,
            self.tau_spin.value(),
            self.euclidean_lengths_checkbox.isChecked(),
            self.marker_interval_spin.value(),
            self.marker_unit_combo.currentText(),
        )
        if not report.view_axis:
            QMessageBox.information(self, "No calibration data", "Create calibration sticks before exporting a conversion map.")
            return

        output_root = self._default_output_root()
        directory = QFileDialog.getExistingDirectory(self, "Choose calibration output folder", str(output_root))
        if not directory:
            return

        try:
            session_dir = make_session_output_dir(directory)
            paths = write_calibration_conversion_export(session_dir, sticks, report)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return

        QMessageBox.information(
            self,
            "Conversion map exported",
            f"Output folder:\n{session_dir}\n\nMap:\n{paths['map'].name}\nReport:\n{paths['report'].name}",
        )

    def _default_output_root(self) -> Path:
        output_root = self._project_root / "outputs" / "calibration"
        output_root.mkdir(parents=True, exist_ok=True)
        return output_root

    def _release_capture(self) -> None:
        if hasattr(self, "_frame_load_timer"):
            self._frame_load_timer.stop()
        self._pending_frame_ms = None
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._fps = 0.0
        self._frame_count = 0

    def _save_media_state(self, item: QListWidgetItem | None = None) -> None:
        if self._loading_media or not hasattr(self, "preview"):
            return

        path_key = item.data(Qt.UserRole) if item is not None else str(self._current_media) if self._current_media is not None else None
        if not path_key:
            return

        self._calibration_sticks_by_media[path_key] = tuple(self.preview.calibration_sticks())
        if self._capture is not None:
            self._timeline_ms_by_media[path_key] = int(self.timeline.value())

    def _all_calibration_sticks(self) -> list[CalibrationStick]:
        if not self._loading_media:
            self._save_media_state()
        sticks = []
        for index in range(self.media_list.count()):
            item = self.media_list.item(index)
            sticks.extend(self._calibration_sticks_by_media.get(item.data(Qt.UserRole), ()))
        return sticks

    def _update_location_failure_highlights(self, report: CalibrationReport) -> None:
        if self._current_media is None:
            self.preview.set_location_failure_markers({})
            return

        stats_by_stick = {(stat.view_index, stat.axis): stat for stat in report.view_axis}
        markers_by_stick: dict[str, set[int]] = {}
        tau_percent = self.tau_spin.value()
        use_euclidean = self.euclidean_lengths_checkbox.isChecked()
        centimeters_per_marker_interval = self.marker_interval_spin.value() * (2.54 if self.marker_unit_combo.currentText().lower().startswith("inch") else 1.0)

        for stick in self.preview.calibration_sticks():
            stat = stats_by_stick.get((stick.view_index, stick.axis))
            if stat is None or stat.location_passed is not False or stat.mean_conversion_factor is None:
                continue

            failed_markers = _failed_location_marker_indices(
                stick,
                stat.mean_conversion_factor,
                tau_percent,
                use_euclidean,
                centimeters_per_marker_interval,
            )
            if failed_markers:
                markers_by_stick[_stick_key(stick.axis, stick.view_index)] = failed_markers

        self.preview.set_location_failure_markers(markers_by_stick)

    def _media_item_for_path(self, path: Path) -> QListWidgetItem | None:
        path_key = str(path)
        for index in range(self.media_list.count()):
            item = self.media_list.item(index)
            if item.data(Qt.UserRole) == path_key:
                return item
        return None

    def _update_media_summary(self) -> None:
        count = self.media_list.count()
        if count == 0:
            self.media_label.setText("No calibration images or videos loaded.")
            return

        selected = self.media_list.currentItem()
        current = f"\nCurrent: {selected.toolTip()}" if selected is not None else ""
        stick_count = len(self._all_calibration_sticks())
        self.media_label.setText(f"{count} calibration file(s) loaded. {stick_count} calibration stick(s) saved.{current}")


def _report_to_html(report: CalibrationReport) -> str:
    if not report.view_axis:
        return (
            f"<p style='color:{theme.TEXT};'>Create an x calibration stick, a y calibration stick, "
            "and add markers. Stick endpoints already count as markers.</p>"
            f"<p><b>Tau:</b> {report.tau_percent:.2f}%</p>"
        )

    interval_label = _marker_interval_label(report)
    parts = [
        f"<p><b>Overall:</b> {_status_text(report.overall_passed)}<br>"
        f"<span style='color:{theme.TEXT};'>{report.recommendation}</span></p>",
        f"<p><b>Tau:</b> {report.tau_percent:.2f}% &nbsp; "
        f"<b>Axis threshold:</b> {2.0 * report.tau_percent:.2f}%<br>"
        f"<b>Marker gap:</b> {interval_label}</p>",
        f"<p><b>Measured {interval_label} intervals</b></p>",
        "<table cellspacing='0' cellpadding='3'>",
        "<tr><th align='left'>Stick</th><th align='right'>Segments</th><th align='right'>Mean px/cm</th><th align='right'>s cm/px</th></tr>",
    ]

    for stat in report.view_axis:
        mean_px = "--" if stat.mean_conversion_factor in {None, 0} else f"{1.0 / stat.mean_conversion_factor:.2f}"
        mean_s = "--" if stat.mean_conversion_factor is None else f"{stat.mean_conversion_factor:.6f}"
        parts.append(
            "<tr>"
            f"<td>{stat.axis}line_view{stat.view_index}</td>"
            f"<td align='right'>{stat.segment_count}</td>"
            f"<td align='right'>{mean_px}</td>"
            f"<td align='right'>{mean_s}</td>"
            "</tr>"
        )
    parts.append("</table>")

    parts.append("<p><b>Check 1: location distortion</b></p><ul>")
    for stat in report.view_axis:
        parts.append(
            "<li>"
            f"{stat.axis}line_view{stat.view_index}: "
            f"{_percent(stat.location_delta_percent)} "
            f"({_status_text(stat.location_passed)})"
            "</li>"
        )
    parts.append("</ul>")

    parts.append("<p><b>Check 2: x/y axis difference</b></p><ul>")
    for view in report.views:
        parts.append(
            "<li>"
            f"view{view.view_index}: {_percent(view.axis_delta_percent)} "
            f"({_status_text(view.axis_passed)})"
            "</li>"
        )
    parts.append("</ul>")

    parts.append("<p><b>Check 3: view difference</b></p><ul>")
    for view in report.views:
        parts.append(
            "<li>"
            f"view{view.view_index}: {_percent(view.view_delta_percent)} "
            f"({_status_text(view.view_passed)})"
            "</li>"
        )
    parts.append("</ul>")

    return "".join(parts)


def _status_text(value: bool | None) -> str:
    if value is True:
        return f"<span style='color:{theme.STATUS_READY}; font-weight:700;'>PASS</span>"
    if value is False:
        return f"<span style='color:{theme.STATUS_ERROR}; font-weight:700;'>FAIL</span>"
    return f"<span style='color:{theme.CONNECTOR}; font-weight:700;'>NEEDS DATA</span>"


def _percent(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}%"


def _marker_interval_label(report: CalibrationReport) -> str:
    unit = "inches" if report.measurement_unit == "in" else "cm"
    if report.measurement_unit == "in":
        return f"{report.units_per_marker_interval:g} {unit} ({report.centimeters_per_marker_interval:g} cm)"
    return f"{report.units_per_marker_interval:g} {unit}"


def _failed_location_marker_indices(
    stick: CalibrationStick,
    mean_conversion_factor: float,
    tau_percent: float,
    use_euclidean_lengths: bool,
    centimeters_per_marker_interval: float,
) -> set[int]:
    if mean_conversion_factor <= 0 or not isfinite(mean_conversion_factor):
        return set()

    worst_delta = 0.0
    worst_segment_index: int | None = None
    points = stick.marker_points()
    for segment_index, (first, second) in enumerate(zip(points, points[1:], strict=False)):
        pixel_length = _segment_pixel_length(stick.axis, first, second, use_euclidean_lengths)
        if pixel_length <= 0 or not isfinite(pixel_length):
            continue

        conversion_factor = centimeters_per_marker_interval / pixel_length
        delta_percent = abs((conversion_factor - mean_conversion_factor) / mean_conversion_factor) * 100.0
        if delta_percent > worst_delta:
            worst_delta = delta_percent
            worst_segment_index = segment_index

    if worst_segment_index is None or worst_delta <= tau_percent:
        return set()
    return {worst_segment_index, worst_segment_index + 1}


def _segment_pixel_length(axis: str, first, second, use_euclidean_lengths: bool) -> float:
    if use_euclidean_lengths:
        return hypot(second.x - first.x, second.y - first.y)
    if axis == "x":
        return abs(second.x - first.x)
    if axis == "y":
        return abs(second.y - first.y)
    return 0.0


def _stick_key(axis: str, view_index: int) -> str:
    return f"{axis}:{view_index}"


def _make_tool_button(text: str, color: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setCheckable(True)
    button.setStyleSheet(_tool_button_style(color))
    return button


def _tool_button_style(color: str) -> str:
    return f"""
        QToolButton {{
            background: {theme.SURFACE};
            border: 1px solid {theme.BORDER};
            border-bottom: 3px solid {color};
            color: {theme.TEXT};
            border-radius: 3px;
            padding: 6px 10px;
            font-weight: 600;
        }}
        QToolButton:hover {{
            background: {theme.PANEL};
            border-color: {theme.CONNECTOR};
            border-bottom-color: {color};
        }}
        QToolButton:checked {{
            background: {theme.PANEL};
            border: 1px solid {theme.TEXT};
            border-bottom: 3px solid {color};
            color: {theme.TEXT};
        }}
        QToolButton:disabled {{
            background: {theme.BACKGROUND};
            border-color: {theme.ACCENT};
            color: {theme.CONNECTOR};
        }}
    """
