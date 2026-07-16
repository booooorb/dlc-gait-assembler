from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.interaction import install_wheel_value_guard, set_tooltip
from dlc_gait_assembly.gui.shared.progress import DynamicProgressBar
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.pipeline.ladder import (
    DualLadderRunResult,
    LadderEvent,
    LadderRunResult,
    LadderSettings,
    ladder_settings_from_alma_config,
    read_dlc_bodyparts,
    run_dual_view_ladder_analysis,
    run_ladder_analysis,
    suggested_ladder_bodyparts,
    write_ladder_events,
)
from dlc_gait_assembly.services.pipeline.alma import (
    default_alma_root,
    load_alma_config_defaults,
)
from dlc_gait_assembly.services.project_paths import (
    find_project_root,
    manual_pipeline_output_folders,
)


class LadderAnalysisWidget(QWidget):
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("LadderAnalysisWidget")
        self._project_root = find_project_root(__file__)
        self._defaults = ladder_settings_from_alma_config(
            load_alma_config_defaults(default_alma_root(self._project_root))
        )
        self._csv_path: Path | None = None
        self._right_csv_path: Path | None = None
        self._video_path: Path | None = None
        self._right_video_path: Path | None = None
        self._events: list[LadderEvent] = []
        self._worker: LadderAnalysisThread | DualLadderAnalysisThread | None = None
        self._video_capture = None
        self._right_video_capture = None
        self._video_frame_counts = {"single": 0, "left": 0, "right": 0}
        self._active_preview_view = "single"
        self._build_ui()
        self._connect_signals()
        self._wheel_guard = install_wheel_value_guard(self)
        self._apply_style()
        self._update_mode()
        self._update_method_controls()
        self._update_run_state()

    def can_close(self, parent=None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                parent or self,
                "Ladder analysis is running",
                "Wait for the current ALMA ladder analysis to finish before closing this window.",
            )
            return False
        return True

    def release_resources(self) -> None:
        for attribute in ("_video_capture", "_right_video_capture"):
            capture = getattr(self, attribute)
            if capture is not None:
                capture.release()
                setattr(self, attribute, None)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("ALMA ladder-rung analysis")
        title.setObjectName("TitleLabel")
        title_row = QHBoxLayout()
        self.back_to_gait_button = QPushButton("← Gait analysis")
        self.back_to_gait_button.clicked.connect(self.back_requested.emit)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.back_to_gait_button)
        subtitle = QLabel(
            "Detect paw placements from DeepLabCut coordinates, review them against the video, "
            "and classify slips or falls before export."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        root.addLayout(title_row)
        root.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        controls = QWidget()
        controls.setMinimumWidth(390)
        controls.setMaximumWidth(500)
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 12, 0)
        controls_layout.setSpacing(12)

        input_box = QGroupBox("Input")
        input_layout = QGridLayout(input_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Single camera", "Paired left + right cameras"])
        self.csv_edit = QLineEdit()
        self.csv_edit.setReadOnly(True)
        self.csv_button = QPushButton("Choose DLC CSV…")
        self.video_edit = QLineEdit()
        self.video_edit.setReadOnly(True)
        self.video_button = QPushButton("Choose video…")
        self.right_csv_label = QLabel("Right coordinates")
        self.right_csv_edit = QLineEdit()
        self.right_csv_edit.setReadOnly(True)
        self.right_csv_button = QPushButton("Choose right CSV…")
        self.right_video_label = QLabel("Right review video")
        self.right_video_edit = QLineEdit()
        self.right_video_edit.setReadOnly(True)
        self.right_video_button = QPushButton("Choose right video…")
        self.output_edit = QLineEdit(str(self._default_output_folder()))
        self.output_button = QPushButton("Output…")
        self.left_csv_label = QLabel("Coordinates")
        self.left_video_label = QLabel("Review video")
        input_layout.addWidget(QLabel("Mode"), 0, 0)
        input_layout.addWidget(self.mode_combo, 0, 1, 1, 2)
        input_layout.addWidget(self.left_csv_label, 1, 0)
        input_layout.addWidget(self.csv_edit, 1, 1)
        input_layout.addWidget(self.csv_button, 1, 2)
        input_layout.addWidget(self.left_video_label, 2, 0)
        input_layout.addWidget(self.video_edit, 2, 1)
        input_layout.addWidget(self.video_button, 2, 2)
        input_layout.addWidget(self.right_csv_label, 3, 0)
        input_layout.addWidget(self.right_csv_edit, 3, 1)
        input_layout.addWidget(self.right_csv_button, 3, 2)
        input_layout.addWidget(self.right_video_label, 4, 0)
        input_layout.addWidget(self.right_video_edit, 4, 1)
        input_layout.addWidget(self.right_video_button, 4, 2)
        input_layout.addWidget(QLabel("Output folder"), 5, 0)
        input_layout.addWidget(self.output_edit, 5, 1)
        input_layout.addWidget(self.output_button, 5, 2)
        controls_layout.addWidget(input_box)

        settings_box = QGroupBox("Detection settings")
        settings_box_layout = QVBoxLayout(settings_box)
        self.settings_tabs = QTabWidget()
        left_settings_tab = QWidget()
        settings_layout = QGridLayout(left_settings_tab)
        self.method_combo = QComboBox()
        self.method_combo.addItems(["Deviation", "Baseline", "Threshold"])
        self.likelihood_spin = _double_spin(0.0, 1.0, self._defaults.likelihood_threshold, 2, 0.05)
        self.depth_spin = _double_spin(0.0, 1.0, self._defaults.depth_threshold, 2, 0.05)
        self.threshold_spin = _double_spin(
            -100000.0, 100000.0, self._defaults.threshold or 0.0, 2, 1.0
        )
        self.auto_threshold_checkbox = QCheckBox("Automatic")
        self.auto_threshold_checkbox.setChecked(self._defaults.threshold is None)
        self.frame_rate_spin = _double_spin(1.0, 1000.0, self._defaults.frame_rate, 2, 1.0)
        settings_layout.addWidget(QLabel("Method"), 0, 0)
        settings_layout.addWidget(self.method_combo, 0, 1, 1, 2)
        settings_layout.addWidget(QLabel("Likelihood minimum"), 1, 0)
        settings_layout.addWidget(self.likelihood_spin, 1, 1, 1, 2)
        settings_layout.addWidget(QLabel("Recovery fraction"), 2, 0)
        settings_layout.addWidget(self.depth_spin, 2, 1, 1, 2)
        settings_layout.addWidget(QLabel("Y threshold"), 3, 0)
        settings_layout.addWidget(self.threshold_spin, 3, 1)
        settings_layout.addWidget(self.auto_threshold_checkbox, 3, 2)
        settings_layout.addWidget(QLabel("Frame rate (fps)"), 4, 0)
        settings_layout.addWidget(self.frame_rate_spin, 4, 1, 1, 2)
        set_tooltip(self.depth_spin, "Required recovery relative to the preceding footfall depth before ALMA starts a new event.")

        right_settings_tab = QWidget()
        right_settings_layout = QGridLayout(right_settings_tab)
        self.right_method_combo = QComboBox()
        self.right_method_combo.addItems(["Deviation", "Baseline", "Threshold"])
        self.right_likelihood_spin = _double_spin(
            0.0, 1.0, self._defaults.likelihood_threshold, 2, 0.05
        )
        self.right_depth_spin = _double_spin(
            0.0, 1.0, self._defaults.depth_threshold, 2, 0.05
        )
        self.right_threshold_spin = _double_spin(
            -100000.0, 100000.0, self._defaults.threshold or 0.0, 2, 1.0
        )
        self.right_auto_threshold_checkbox = QCheckBox("Automatic")
        self.right_auto_threshold_checkbox.setChecked(self._defaults.threshold is None)
        self.right_frame_rate_spin = _double_spin(
            1.0, 1000.0, self._defaults.frame_rate, 2, 1.0
        )
        right_settings_layout.addWidget(QLabel("Method"), 0, 0)
        right_settings_layout.addWidget(self.right_method_combo, 0, 1, 1, 2)
        right_settings_layout.addWidget(QLabel("Likelihood minimum"), 1, 0)
        right_settings_layout.addWidget(self.right_likelihood_spin, 1, 1, 1, 2)
        right_settings_layout.addWidget(QLabel("Recovery fraction"), 2, 0)
        right_settings_layout.addWidget(self.right_depth_spin, 2, 1, 1, 2)
        right_settings_layout.addWidget(QLabel("Y threshold"), 3, 0)
        right_settings_layout.addWidget(self.right_threshold_spin, 3, 1)
        right_settings_layout.addWidget(self.right_auto_threshold_checkbox, 3, 2)
        right_settings_layout.addWidget(QLabel("Frame rate (fps)"), 4, 0)
        right_settings_layout.addWidget(self.right_frame_rate_spin, 4, 1, 1, 2)
        set_tooltip(
            self.right_depth_spin,
            "Right-camera recovery fraction; it can differ from the left camera.",
        )
        self.settings_tabs.addTab(left_settings_tab, "Camera / left")
        self.settings_tabs.addTab(right_settings_tab, "Right camera")
        settings_box_layout.addWidget(self.settings_tabs)
        controls_layout.addWidget(settings_box)

        bodyparts_box = QGroupBox("Paw markers")
        bodyparts_layout = QVBoxLayout(bodyparts_box)
        self.bodyparts_tabs = QTabWidget()
        self.bodyparts_list = QListWidget()
        self.bodyparts_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.right_bodyparts_list = QListWidget()
        self.right_bodyparts_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.bodyparts_tabs.addTab(self.bodyparts_list, "Camera / left")
        self.bodyparts_tabs.addTab(self.right_bodyparts_list, "Right camera")
        bodyparts_layout.addWidget(self.bodyparts_tabs)
        controls_layout.addWidget(bodyparts_box, 1)

        self.run_button = QPushButton("Run ALMA ladder detection")
        self.run_button.setObjectName("PrimaryButton")
        self.progress = DynamicProgressBar(accent_role="tool_1")
        self.progress.setRange(0, 100)
        self.status_label = QLabel("Choose a DeepLabCut coordinate CSV to begin.")
        self.status_label.setWordWrap(True)
        controls_layout.addWidget(self.run_button)
        controls_layout.addWidget(self.progress)
        controls_layout.addWidget(self.status_label)

        review = QWidget()
        review_layout = QVBoxLayout(review)
        review_layout.setContentsMargins(12, 0, 0, 0)
        review_layout.setSpacing(12)
        preview_box = QGroupBox("Optional video review")
        preview_layout = QVBoxLayout(preview_box)
        self.video_preview = QLabel("Choose the corresponding video to review detected events.")
        self.video_preview.setObjectName("VideoPreview")
        self.video_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_preview.setMinimumHeight(260)
        self.video_preview.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        self.video_preview.setWordWrap(True)
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setRange(0, 0)
        self.frame_label = QLabel("Frame —")
        preview_layout.addWidget(self.video_preview, 1)
        preview_layout.addWidget(self.frame_slider)
        preview_layout.addWidget(self.frame_label)
        review_layout.addWidget(preview_box, 2)

        table_box = QGroupBox("Detected events — select a row to inspect its deepest frame")
        table_layout = QVBoxLayout(table_box)
        self.events_table = QTableWidget(0, 9)
        self.events_table.setHorizontalHeaderLabels(
            ["Use", "View", "Body part", "Peak", "Start", "End", "Depth (px)", "Duration (s)", "Classification"]
        )
        self.events_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.events_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.events_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.events_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table_layout.addWidget(self.events_table)
        review_layout.addWidget(table_box, 3)

        export_row = QHBoxLayout()
        export_note = QLabel("Uncheck false detections; classify accepted events as footfall, slip, or fall.")
        export_note.setObjectName("MutedLabel")
        export_note.setWordWrap(True)
        self.save_button = QPushButton("Save reviewed results…")
        self.save_button.setEnabled(False)
        export_row.addWidget(export_note, 1)
        export_row.addWidget(self.save_button)
        review_layout.addLayout(export_row)

        controls_scroll = QScrollArea()
        controls_scroll.setObjectName("LadderControlsScroll")
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_scroll.setMinimumWidth(410)
        controls_scroll.setMaximumWidth(520)
        controls_scroll.setWidget(controls)

        splitter.addWidget(controls_scroll)
        splitter.addWidget(review)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

    def _connect_signals(self) -> None:
        self.mode_combo.currentTextChanged.connect(self._update_mode)
        self.csv_button.clicked.connect(self._choose_csv)
        self.right_csv_button.clicked.connect(self._choose_right_csv)
        self.video_button.clicked.connect(self._choose_video)
        self.right_video_button.clicked.connect(self._choose_right_video)
        self.output_button.clicked.connect(self._choose_output)
        self.method_combo.currentTextChanged.connect(self._update_method_controls)
        self.auto_threshold_checkbox.toggled.connect(self._update_method_controls)
        self.right_method_combo.currentTextChanged.connect(self._update_method_controls)
        self.right_auto_threshold_checkbox.toggled.connect(self._update_method_controls)
        self.run_button.clicked.connect(self._run_detection)
        self.events_table.currentCellChanged.connect(self._event_selected)
        self.frame_slider.valueChanged.connect(self._show_video_frame)
        self.save_button.clicked.connect(self._save_reviewed_results)
        self.output_edit.textChanged.connect(self._update_run_state)

    def _choose_csv(self) -> None:
        self._choose_csv_for_view("left" if self._is_dual_mode() else "single")

    def _choose_right_csv(self) -> None:
        self._choose_csv_for_view("right")

    def _choose_csv_for_view(self, view: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose {view} ladder coordinate CSV",
            str(self._project_root),
            "CSV files (*.csv);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename).expanduser().resolve()
        try:
            bodyparts = read_dlc_bodyparts(path)
        except Exception as exc:
            QMessageBox.critical(self, "Could not read DLC coordinates", str(exc))
            return
        if view == "right":
            self._right_csv_path = path
            self.right_csv_edit.setText(str(path))
            bodyparts_list = self.right_bodyparts_list
        else:
            self._csv_path = path
            self.csv_edit.setText(str(path))
            bodyparts_list = self.bodyparts_list
        bodyparts_list.clear()
        suggested = set(suggested_ladder_bodyparts(bodyparts))
        for bodypart in bodyparts:
            item = QListWidgetItem(bodypart)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if bodypart in suggested else Qt.CheckState.Unchecked)
            bodyparts_list.addItem(item)
        self.status_label.setText(
            f"Loaded {len(bodyparts)} {view}-view labels. "
            + ("Select exactly two paw markers for this camera." if self._is_dual_mode() else "Select the paw markers to analyze.")
        )
        self._events = []
        self.events_table.setRowCount(0)
        self.save_button.setEnabled(False)
        self._update_run_state()

    def _choose_video(self) -> None:
        self._choose_video_for_view("left" if self._is_dual_mode() else "single")

    def _choose_right_video(self) -> None:
        self._choose_video_for_view("right")

    def _choose_video_for_view(self, view: str) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        filename, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose {view} ladder video",
            str(self._project_root),
            f"Video files ({extensions});;All files (*)",
        )
        if not filename:
            return
        path = Path(filename).expanduser().resolve()
        self._release_video(view)
        try:
            import cv2

            capture = cv2.VideoCapture(str(path))
            if not capture.isOpened():
                raise ValueError("OpenCV could not open this video.")
            frame_count = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            if view == "right":
                self._right_video_capture = capture
                self._right_video_path = path
                self.right_video_edit.setText(str(path))
                self.right_frame_rate_spin.setValue(fps if fps > 0 else self.right_frame_rate_spin.value())
            else:
                self._video_capture = capture
                self._video_path = path
                self.video_edit.setText(str(path))
                self.frame_rate_spin.setValue(fps if fps > 0 else self.frame_rate_spin.value())
            self._video_frame_counts[view] = frame_count
            self._active_preview_view = view
            self.frame_slider.setRange(0, frame_count - 1)
            self._show_video_frame(0)
        except Exception as exc:
            self._release_video(view)
            QMessageBox.critical(self, "Could not load video", str(exc))

    def _release_video(self, view: str) -> None:
        attribute = "_right_video_capture" if view == "right" else "_video_capture"
        capture = getattr(self, attribute)
        if capture is not None:
            capture.release()
            setattr(self, attribute, None)
        self._video_frame_counts[view] = 0

    def _choose_output(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose ladder output folder", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def _selected_bodyparts(self, view: str = "single") -> list[str]:
        bodyparts_list = self.right_bodyparts_list if view == "right" else self.bodyparts_list
        return [
            bodyparts_list.item(index).text()
            for index in range(bodyparts_list.count())
            if bodyparts_list.item(index).checkState() == Qt.CheckState.Checked
        ]

    def _settings(self, view: str = "single") -> LadderSettings:
        if view == "right":
            return LadderSettings(
                method=self.right_method_combo.currentText(),
                frame_rate=self.right_frame_rate_spin.value(),
                likelihood_threshold=self.right_likelihood_spin.value(),
                depth_threshold=self.right_depth_spin.value(),
                threshold=None
                if self.right_auto_threshold_checkbox.isChecked()
                else self.right_threshold_spin.value(),
            )
        return LadderSettings(
            method=self.method_combo.currentText(),
            frame_rate=self.frame_rate_spin.value(),
            likelihood_threshold=self.likelihood_spin.value(),
            depth_threshold=self.depth_spin.value(),
            threshold=None if self.auto_threshold_checkbox.isChecked() else self.threshold_spin.value(),
        )

    def _run_detection(self) -> None:
        if self._csv_path is None:
            return
        left_bodyparts = self._selected_bodyparts("left")
        if self._is_dual_mode():
            right_bodyparts = self._selected_bodyparts("right")
            if self._right_csv_path is None:
                QMessageBox.information(self, "Right CSV required", "Choose the right-camera coordinate CSV.")
                return
            if len(left_bodyparts) != 2 or len(right_bodyparts) != 2:
                QMessageBox.information(
                    self,
                    "Select two paws per camera",
                    "Paired mode requires exactly two markers from the left CSV and two from the right CSV (front and hind paw).",
                )
                return
        elif not left_bodyparts:
            QMessageBox.information(self, "No paw markers selected", "Select at least one body part to analyze.")
            return
        output_folder = Path(self.output_edit.text()).expanduser().resolve()
        self.progress.setRange(0, 0)
        self.progress.set_active(True)
        if self._is_dual_mode():
            self.status_label.setText("Running paired left/right ALMA ladder detection…")
            self._worker = DualLadderAnalysisThread(
                self._csv_path,
                self._right_csv_path,
                output_folder,
                self._settings("left"),
                self._settings("right"),
                left_bodyparts,
                right_bodyparts,
            )
        else:
            self.status_label.setText("Running ALMA ladder-rung detection…")
            self._worker = LadderAnalysisThread(
                self._csv_path, output_folder, self._settings(), left_bodyparts
            )
        self._worker.completed.connect(self._detection_completed)
        self._worker.failed.connect(self._detection_failed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()
        self._update_run_state()

    def _detection_completed(self, result: LadderRunResult | DualLadderRunResult) -> None:
        self._events = list(result.events)
        self._populate_event_table()
        self.progress.setRange(0, 100)
        self.progress.set_active(False)
        self.progress.setValue(100)
        self.status_label.setText(
            f"Detected {len(self._events)} event(s). "
            f"{'Combined' if isinstance(result, DualLadderRunResult) else 'Raw ALMA'} output: {result.output_file.name}"
        )
        self.save_button.setEnabled(bool(self._events))
        if self._events:
            self.events_table.selectRow(0)

    def _detection_failed(self, message: str) -> None:
        self.progress.setRange(0, 100)
        self.progress.set_active(False)
        self.status_label.setText("Ladder detection failed.")
        QMessageBox.critical(self, "ALMA ladder analysis failed", message)

    def _worker_finished(self) -> None:
        self._worker = None
        self.progress.set_active(False)
        self._update_run_state()

    def _populate_event_table(self) -> None:
        self.events_table.setRowCount(len(self._events))
        for row, event in enumerate(self._events):
            include = QCheckBox()
            include.setChecked(event.included)
            include.setToolTip("Include this event in the reviewed export.")
            include_cell = QWidget()
            include_layout = QHBoxLayout(include_cell)
            include_layout.setContentsMargins(0, 0, 0, 0)
            include_layout.addWidget(include, 0, Qt.AlignmentFlag.AlignCenter)
            self.events_table.setCellWidget(row, 0, include_cell)
            for column, value in enumerate(
                (
                    event.view.title(),
                    event.bodypart,
                    event.peak_frame,
                    event.start_frame,
                    event.end_frame,
                    f"{event.depth_px:.3f}",
                    f"{event.duration_s:.3f}",
                ),
                start=1,
            ):
                self.events_table.setItem(row, column, QTableWidgetItem(str(value)))
            classification = QComboBox()
            classification.addItems(["unreviewed", "footfall", "slip", "fall"])
            classification.setCurrentText(event.classification)
            self.events_table.setCellWidget(row, 8, classification)

    def _reviewed_events(self) -> list[LadderEvent]:
        reviewed: list[LadderEvent] = []
        for row, event in enumerate(self._events):
            include_cell = self.events_table.cellWidget(row, 0)
            include = include_cell.findChild(QCheckBox) if include_cell is not None else None
            classification = self.events_table.cellWidget(row, 8)
            reviewed.append(
                LadderEvent(
                    **{
                        **event.__dict__,
                        "included": bool(include and include.isChecked()),
                        "classification": classification.currentText(),
                    }
                )
            )
        return reviewed

    def _save_reviewed_results(self) -> None:
        if self._csv_path is None:
            return
        if self._is_dual_mode() and self._right_csv_path is not None:
            default_name = (
                f"{self._csv_path.stem}__{self._right_csv_path.stem}"
                "_ladder_combined_reviewed.csv"
            )
        else:
            default_name = f"{self._csv_path.stem}_ladder_reviewed.csv"
        default_path = Path(self.output_edit.text()).expanduser() / default_name
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save reviewed ladder events", str(default_path), "CSV files (*.csv)"
        )
        if not filename:
            return
        try:
            output = write_ladder_events(
                self._reviewed_events(), Path(filename), combined=self._is_dual_mode()
            )
        except Exception as exc:
            QMessageBox.critical(self, "Could not save reviewed events", str(exc))
            return
        self.status_label.setText(f"Reviewed ladder events saved to {output.name}.")
        QMessageBox.information(self, "Ladder results saved", str(output))

    def _event_selected(self, current_row: int, _current_column: int, _previous_row: int, _previous_column: int) -> None:
        if 0 <= current_row < len(self._events):
            event = self._events[current_row]
            self._active_preview_view = event.view
            frame_count = self._video_frame_counts.get(event.view, 0)
            self.frame_slider.setRange(0, max(0, frame_count - 1))
            self.frame_slider.setValue(event.peak_frame)
            self._show_video_frame(event.peak_frame)

    def _show_video_frame(self, frame_number: int) -> None:
        view = self._active_preview_view
        self.frame_label.setText(f"{view.title()} view · frame {frame_number}")
        capture = self._right_video_capture if view == "right" else self._video_capture
        if capture is None:
            self.video_preview.setText(
                f"No {view}-view video loaded. The event still remains available for CSV review."
            )
            return
        try:
            import cv2

            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            ok, frame = capture.read()
            if not ok:
                return
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy()
            preview_size = self.video_preview.contentsRect().size()
            pixmap = QPixmap.fromImage(image).scaled(
                preview_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.video_preview.setPixmap(pixmap)
        except Exception:
            return

    def _is_dual_mode(self) -> bool:
        return self.mode_combo.currentText() == "Paired left + right cameras"

    def _update_mode(self) -> None:
        dual = self._is_dual_mode()
        for widget in (
            self.right_csv_label,
            self.right_csv_edit,
            self.right_csv_button,
            self.right_video_label,
            self.right_video_edit,
            self.right_video_button,
        ):
            widget.setVisible(dual)
        self.settings_tabs.setTabVisible(1, dual)
        self.bodyparts_tabs.setTabVisible(1, dual)
        self.settings_tabs.setTabText(0, "Left camera" if dual else "Camera")
        self.bodyparts_tabs.setTabText(0, "Left camera" if dual else "Camera")
        self.left_csv_label.setText("Left coordinates" if dual else "Coordinates")
        self.left_video_label.setText("Left review video" if dual else "Review video")
        self.csv_button.setText("Choose left CSV…" if dual else "Choose DLC CSV…")
        self.video_button.setText("Choose left video…" if dual else "Choose video…")
        self.run_button.setText(
            "Run paired ALMA ladder detection" if dual else "Run ALMA ladder detection"
        )
        if dual:
            self.status_label.setText(
                "Choose left and right CSVs, then select exactly two paw markers in each tab."
            )
        elif self._csv_path is None:
            self.status_label.setText("Choose a DeepLabCut coordinate CSV to begin.")
        self._update_run_state()

    def _update_method_controls(self) -> None:
        threshold_method = self.method_combo.currentText() == "Threshold"
        self.auto_threshold_checkbox.setEnabled(threshold_method)
        self.threshold_spin.setEnabled(threshold_method and not self.auto_threshold_checkbox.isChecked())
        right_threshold_method = self.right_method_combo.currentText() == "Threshold"
        self.right_auto_threshold_checkbox.setEnabled(right_threshold_method)
        self.right_threshold_spin.setEnabled(
            right_threshold_method and not self.right_auto_threshold_checkbox.isChecked()
        )

    def _update_run_state(self) -> None:
        running = self._worker is not None and self._worker.isRunning()
        has_inputs = self._csv_path is not None and (
            not self._is_dual_mode() or self._right_csv_path is not None
        )
        self.run_button.setEnabled(
            has_inputs and bool(self.output_edit.text().strip()) and not running
        )

    def _default_output_folder(self) -> Path:
        path = manual_pipeline_output_folders(self._project_root).gait_analysis / "ladder"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.workspace_stylesheet(
                "LadderAnalysisWidget",
                """
                QLabel#VideoPreview {
                    background: {theme.CANVAS};
                    color: {theme.CANVAS_TEXT};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                """
            )
        )


class LadderAnalysisThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, csv_file: Path, output_folder: Path, settings: LadderSettings, bodyparts: list[str]):
        super().__init__()
        self._csv_file = csv_file
        self._output_folder = output_folder
        self._settings = settings
        self._bodyparts = bodyparts

    def run(self) -> None:
        try:
            result = run_ladder_analysis(
                self._csv_file, self._output_folder, self._settings, self._bodyparts
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)


class DualLadderAnalysisThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        left_csv_file: Path,
        right_csv_file: Path,
        output_folder: Path,
        left_settings: LadderSettings,
        right_settings: LadderSettings,
        left_bodyparts: list[str],
        right_bodyparts: list[str],
    ):
        super().__init__()
        self._left_csv_file = left_csv_file
        self._right_csv_file = right_csv_file
        self._output_folder = output_folder
        self._left_settings = left_settings
        self._right_settings = right_settings
        self._left_bodyparts = left_bodyparts
        self._right_bodyparts = right_bodyparts

    def run(self) -> None:
        try:
            result = run_dual_view_ladder_analysis(
                self._left_csv_file,
                self._right_csv_file,
                self._output_folder,
                self._left_settings,
                self._right_settings,
                self._left_bodyparts,
                self._right_bodyparts,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(result)


def _double_spin(minimum, maximum, value, decimals, step) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setValue(value)
    return spin
