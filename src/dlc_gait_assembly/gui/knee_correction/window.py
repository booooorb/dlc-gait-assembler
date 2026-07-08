from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.services.knee_correction import (
    CoordinateFilePair,
    KneeCorrectionResult,
    KneeCorrectionSettings,
    PAIR_EXTENSIONS,
    VIDEO_EXTENSIONS,
    correct_knee_dataframe,
    correct_knee_pair,
    pair_coordinate_files,
    read_dlc_bodyparts,
    read_dlc_csv,
)
from dlc_gait_assembly.services.pipeline.alma import pixels_per_cm_from_calibration_map
from dlc_gait_assembly.services.project_paths import find_project_root

try:
    import cv2
except ImportError:  # pragma: no cover - depends on optional local video support
    cv2 = None


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff"}


class KneeCorrectionWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("KneeCorrectionWidget")
        self._project_root = find_project_root(__file__)
        self._selected_paths: list[Path] = []
        self._pairs: list[CoordinateFilePair] = []
        self._calibration_map_path: Path | None = None
        self._pixels_per_cm: float | None = None
        self._worker: KneeCorrectionThread | None = None
        self._preview_original = None
        self._preview_corrected = None
        self._preview_report = None
        self._preview_cache = {}
        self._active_preview_pair_key: tuple[str, str, str] | None = None
        self._preview_frame_positions: tuple[int, ...] = ()
        self._preview_media_path: Path | None = None
        self._preview_static_image: QImage | None = None
        self._preview_capture = None
        self._preview_video_frame_count = 0
        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._refresh_pairs()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        title = QLabel("Knee correction")
        title.setObjectName("TitleLabel")
        root.addWidget(title)

        files_box = QGroupBox("Paired DeepLabCut labels + video")
        files_layout = QVBoxLayout(files_box)
        toolbar = QHBoxLayout()
        self.add_files_button = QPushButton("Add CSV + H5 + video")
        self.add_folder_button = QPushButton("Add folder")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("RemoveButton")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("ClearButton")
        toolbar.addWidget(self.add_files_button)
        toolbar.addWidget(self.add_folder_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.remove_button)
        toolbar.addWidget(self.clear_button)
        files_layout.addLayout(toolbar)
        self.pair_table = QTreeWidget()
        self.pair_table.setObjectName("KneePairTable")
        self.pair_table.setHeaderLabels(["Dataset", "CSV", "H5", "Video", "Status"])
        self.pair_table.setRootIsDecorated(False)
        self.pair_table.setAlternatingRowColors(False)
        self.pair_table.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.pair_table.header().setStretchLastSection(False)
        self.pair_table.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.pair_table.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.pair_table.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.pair_table.header().setSectionResizeMode(3, QHeaderView.Stretch)
        self.pair_table.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        files_layout.addWidget(self.pair_table, 1)

        preview_box = QGroupBox("Knee correction preview")
        preview_layout = QVBoxLayout(preview_box)
        preview_toolbar = QHBoxLayout()
        self.preview_status_label = QLabel("Choose a paired dataset and calibration map.")
        self.preview_status_label.setObjectName("MutedLabel")
        preview_toolbar.addWidget(self.preview_status_label, 1)
        preview_layout.addLayout(preview_toolbar)
        self.knee_preview = KneeStickplotPreview()
        self.knee_preview.setObjectName("KneeStickplotPreview")
        self.knee_preview.setFocusPolicy(Qt.StrongFocus)
        self.knee_preview.setMinimumSize(300, 150)
        preview_layout.addWidget(self.knee_preview, 1)
        slider_row = QHBoxLayout()
        self.previous_frame_button = QPushButton("◀")
        self.previous_frame_button.setFixedWidth(32)
        self.previous_frame_button.setToolTip("Previous frame (Left arrow)")
        self.previous_frame_button.setEnabled(False)
        self.preview_slider = QSlider(Qt.Horizontal)
        self.preview_slider.setEnabled(False)
        self.next_frame_button = QPushButton("▶")
        self.next_frame_button.setFixedWidth(32)
        self.next_frame_button.setToolTip("Next frame (Right arrow)")
        self.next_frame_button.setEnabled(False)
        self.preview_frame_label = QLabel("Frame —")
        self.preview_frame_label.setFixedWidth(260)
        slider_row.addWidget(self.previous_frame_button)
        slider_row.addWidget(self.preview_slider, 1)
        slider_row.addWidget(self.next_frame_button)
        slider_row.addWidget(self.preview_frame_label)
        preview_layout.addLayout(slider_row)

        workspace_row = QHBoxLayout()
        workspace_row.setSpacing(8)
        left_column = QVBoxLayout()
        left_column.setSpacing(6)
        right_column = QVBoxLayout()
        right_column.setSpacing(6)
        left_column.addWidget(files_box, 1)
        right_column.addWidget(preview_box, 1)

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("KneeCorrectionSettingsTabs")
        self.settings_tabs.setDocumentMode(True)
        self.settings_tabs.tabBar().setExpanding(True)
        self.settings_tabs.setMaximumHeight(215)

        calibration_page = QWidget()
        calibration_layout = QGridLayout(calibration_page)
        calibration_layout.setContentsMargins(8, 8, 8, 8)
        self.calibration_map_button = QPushButton("Import calibration map")
        self.calibration_map_label = QLabel("No calibration map selected")
        self.calibration_map_label.setObjectName("MutedLabel")
        calibration_layout.addWidget(self.calibration_map_button, 0, 0)
        calibration_layout.addWidget(self.calibration_map_label, 0, 1)
        self.hip_knee_length = _length_spin()
        self.knee_ankle_length = _length_spin()
        calibration_layout.addWidget(QLabel("Hip–knee length (femur)"), 1, 0)
        calibration_layout.addWidget(self.hip_knee_length, 1, 1)
        calibration_layout.addWidget(QLabel("Knee–ankle length (tibia/fibula)"), 2, 0)
        calibration_layout.addWidget(self.knee_ankle_length, 2, 1)
        self.settings_tabs.addTab(calibration_page, "Calibration")

        labels_page = QWidget()
        labels_layout = QGridLayout(labels_page)
        labels_layout.setContentsMargins(8, 8, 8, 8)
        self.knee_label_combo = QComboBox()
        self.knee_label_combo.addItem("Auto-detect labels containing 'knee'", None)
        self.knee_label_combo.setEnabled(False)
        labels_layout.addWidget(QLabel("Existing knee label"), 0, 0)
        labels_layout.addWidget(self.knee_label_combo, 0, 1)
        self.generated_knee_label_edit = QLineEdit("knee")
        labels_layout.addWidget(QLabel("Generated knee label"), 1, 0)
        labels_layout.addWidget(self.generated_knee_label_edit, 1, 1)
        self.hip_label_combo = QComboBox()
        self.hip_label_combo.addItem("Auto-detect matching hip", None)
        self.hip_label_combo.setEnabled(False)
        labels_layout.addWidget(QLabel("Hip label"), 2, 0)
        labels_layout.addWidget(self.hip_label_combo, 2, 1)
        self.ankle_label_combo = QComboBox()
        self.ankle_label_combo.addItem("Auto-detect matching ankle", None)
        self.ankle_label_combo.setEnabled(False)
        labels_layout.addWidget(QLabel("Ankle label"), 3, 0)
        labels_layout.addWidget(self.ankle_label_combo, 3, 1)
        self.knee_direction_combo = QComboBox()
        self.knee_direction_combo.addItem("Auto from old knee / continuity", "auto")
        self.knee_direction_combo.addItem("Manual side A", "positive")
        self.knee_direction_combo.addItem("Manual side B", "negative")
        labels_layout.addWidget(QLabel("Knee direction"), 4, 0)
        labels_layout.addWidget(self.knee_direction_combo, 4, 1)
        self.likelihood_threshold = QDoubleSpinBox()
        self.likelihood_threshold.setRange(0.0, 1.0)
        self.likelihood_threshold.setDecimals(2)
        self.likelihood_threshold.setSingleStep(0.05)
        self.likelihood_threshold.setValue(0.0)
        labels_layout.addWidget(QLabel("Hip/ankle likelihood minimum"), 5, 0)
        labels_layout.addWidget(self.likelihood_threshold, 5, 1)
        self.settings_tabs.addTab(labels_page, "Label selection")
        left_column.addWidget(self.settings_tabs)

        output_box = QGroupBox("Output")
        output_layout = QVBoxLayout(output_box)
        output_line = QHBoxLayout()
        self.output_folder_edit = QLineEdit(str(self._default_output_folder()))
        self.output_folder_edit.setCursorPosition(0)
        self.output_folder_button = QPushButton("Choose folder")
        output_line.addWidget(self.output_folder_edit, 1)
        output_line.addWidget(self.output_folder_button)
        output_layout.addLayout(output_line)
        output_note = QLabel(
            "Each pair produces *_knee_corrected.csv and *_knee_corrected.h5. "
            "Original files are not modified."
        )
        output_note.setObjectName("MutedLabel")
        output_note.setWordWrap(True)
        output_layout.addWidget(output_note)
        output_layout.addStretch(1)
        right_column.addWidget(output_box)
        workspace_row.addLayout(left_column, 3)
        workspace_row.addLayout(right_column, 2)
        root.addLayout(workspace_row, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        root.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(58)
        self.log.setFont(theme.fixed_width_font())
        root.addWidget(self.log)
        action_row = QHBoxLayout()
        self.status_label = QLabel("Add matching CSV, H5, and video files.")
        self.status_label.setObjectName("PreviewTitle")
        action_row.addWidget(self.status_label, 1)
        self.run_button = QPushButton("Correct knee labels")
        self.run_button.setObjectName("PrimaryButton")
        action_row.addWidget(self.run_button)
        root.addLayout(action_row)

    def _connect_signals(self) -> None:
        self.add_files_button.clicked.connect(self._choose_files)
        self.add_folder_button.clicked.connect(self._choose_folder)
        self.pair_table.itemSelectionChanged.connect(self._show_selected_preview)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self._clear)
        self.output_folder_button.clicked.connect(self._choose_output_folder)
        self.output_folder_edit.textChanged.connect(self._update_run_state)
        self.calibration_map_button.clicked.connect(self._choose_calibration_map)
        self.previous_frame_button.clicked.connect(lambda: self._step_preview_frame(-1))
        self.next_frame_button.clicked.connect(lambda: self._step_preview_frame(1))
        self.preview_slider.valueChanged.connect(self._show_preview_frame)
        self.knee_label_combo.currentIndexChanged.connect(self._preview_inputs_changed)
        self.generated_knee_label_edit.textChanged.connect(self._preview_inputs_changed)
        self.hip_label_combo.currentIndexChanged.connect(self._preview_inputs_changed)
        self.ankle_label_combo.currentIndexChanged.connect(self._preview_inputs_changed)
        self.knee_direction_combo.currentIndexChanged.connect(self._preview_inputs_changed)
        self.hip_knee_length.valueChanged.connect(self._preview_inputs_changed)
        self.knee_ankle_length.valueChanged.connect(self._preview_inputs_changed)
        self.likelihood_threshold.valueChanged.connect(self._preview_inputs_changed)
        self.run_button.clicked.connect(self._run)
        self.previous_frame_shortcut = QShortcut(QKeySequence(Qt.Key_Left), self.knee_preview)
        self.previous_frame_shortcut.setContext(Qt.WidgetShortcut)
        self.previous_frame_shortcut.activated.connect(lambda: self._step_preview_frame(-1))
        self.next_frame_shortcut = QShortcut(QKeySequence(Qt.Key_Right), self.knee_preview)
        self.next_frame_shortcut.setContext(Qt.WidgetShortcut)
        self.next_frame_shortcut.activated.connect(lambda: self._step_preview_frame(1))

    def _choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose paired DeepLabCut labels and video",
            str(self._project_root),
            "Knee correction inputs (*.avi *.csv *.h5 *.m4v *.mkv *.mov *.mp4 *.mpeg *.mpg *.webm);;All files (*)",
        )
        self._add_paths([Path(path) for path in paths])

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose folder containing paired labels and videos",
            str(self._project_root),
        )
        if folder:
            directory = Path(folder)
            self._add_paths([path for path in directory.rglob("*") if path.is_file()])

    def _add_paths(self, paths: list[Path]) -> None:
        known = {str(path) for path in self._selected_paths}
        for path in paths:
            resolved = path.expanduser().resolve()
            if resolved.is_file() and resolved.suffix.lower() in PAIR_EXTENSIONS:
                if str(resolved) not in known:
                    self._selected_paths.append(resolved)
                    known.add(str(resolved))
        self._refresh_pairs()

    def _refresh_pairs(self) -> None:
        self._pairs = pair_coordinate_files(self._selected_paths)
        self.pair_table.clear()
        error_brush = QBrush(QColor(theme.STATUS_ERROR))
        for pair in self._pairs:
            csv_text = pair.csv_path.name if pair.csv_path is not None else "Missing"
            h5_text = pair.h5_path.name if pair.h5_path is not None else "Missing"
            video_text = pair.video_path.name if pair.video_path is not None else "Missing"
            item = QTreeWidgetItem([pair.stem, csv_text, h5_text, video_text, pair.status])
            item.setData(
                0,
                Qt.UserRole,
                [
                    str(path)
                    for path in (*pair.csv_paths, *pair.h5_paths, *pair.video_paths)
                ],
            )
            if not pair.is_paired:
                for column in range(5):
                    item.setForeground(column, error_brush)
            self.pair_table.addTopLevelItem(item)
        self._refresh_label_choices()
        self._invalidate_preview()
        self._update_run_state()
        self._maybe_generate_previews()

    def _refresh_label_choices(self) -> None:
        previous_knee = self.knee_label_combo.currentData()
        previous_hip = self.hip_label_combo.currentData()
        previous_ankle = self.ankle_label_combo.currentData()
        labels: list[str] = []
        for pair in self._pairs:
            if pair.csv_path is None:
                continue
            try:
                for label in read_dlc_bodyparts(pair.csv_path):
                    if label not in labels:
                        labels.append(label)
            except ValueError:
                continue
        combo_settings = (
            (self.knee_label_combo, "Auto-detect labels containing 'knee'", previous_knee),
            (self.hip_label_combo, "Auto-detect matching hip", previous_hip),
            (self.ankle_label_combo, "Auto-detect matching ankle", previous_ankle),
        )
        for combo, automatic_text, previous in combo_settings:
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(automatic_text, None)
            for label in labels:
                combo.addItem(label, label)
            if previous in labels:
                combo.setCurrentIndex(labels.index(previous) + 1)
            combo.setEnabled(bool(labels))
            combo.blockSignals(False)

    def _remove_selected(self) -> None:
        removed = {
            path
            for item in self.pair_table.selectedItems()
            for path in (item.data(0, Qt.UserRole) or [])
        }
        self._selected_paths = [path for path in self._selected_paths if str(path) not in removed]
        self._refresh_pairs()

    def _clear(self) -> None:
        self._selected_paths.clear()
        self._release_preview_capture()
        self._preview_media_path = None
        self._preview_static_image = None
        self._preview_video_frame_count = 0
        self._refresh_pairs()
        self.log.clear()

    def _choose_output_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self,
            "Choose corrected-label output folder",
            self.output_folder_edit.text(),
        )
        if folder:
            self.output_folder_edit.setText(folder)

    def _choose_calibration_map(self) -> None:
        default_folder = self._project_root / "outputs" / "calibration"
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Import calibration conversion map",
            str(default_folder if default_folder.exists() else self._project_root),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if filename:
            self._set_calibration_map(Path(filename))

    def _set_calibration_map(self, path: Path) -> bool:
        resolved = path.expanduser().resolve()
        try:
            pixels_per_cm, source = pixels_per_cm_from_calibration_map(resolved)
        except Exception as exc:
            QMessageBox.critical(self, "Could not import calibration map", str(exc))
            return False
        self._calibration_map_path = resolved
        self._pixels_per_cm = pixels_per_cm
        self.calibration_map_label.setText(
            f"{resolved.name} • {source}: {pixels_per_cm:.3f} px/cm"
        )
        self.calibration_map_label.setToolTip(str(resolved))
        self._invalidate_preview()
        self._update_run_state()
        self._maybe_generate_previews()
        return True

    def _set_preview_media(self, path: Path, notify: bool = True) -> bool:
        resolved = path.expanduser().resolve()
        extension = resolved.suffix.casefold()
        self._release_preview_capture()
        self._preview_media_path = None
        self._preview_static_image = None
        self._preview_video_frame_count = 0
        if extension in IMAGE_EXTENSIONS:
            image = QImage(str(resolved))
            if image.isNull():
                if notify:
                    QMessageBox.critical(
                        self,
                        "Could not load preview frame",
                        f"{resolved.name} is not a readable image.",
                    )
                return False
            self._preview_static_image = image
        elif extension in VIDEO_EXTENSIONS:
            if cv2 is None:
                if notify:
                    QMessageBox.critical(
                        self,
                        "Video preview unavailable",
                        "OpenCV is not available in this environment.",
                    )
                return False
            capture = cv2.VideoCapture(str(resolved))
            if not capture.isOpened():
                capture.release()
                if notify:
                    QMessageBox.critical(
                        self,
                        "Could not load preview video",
                        f"{resolved.name} is not a readable video.",
                    )
                return False
            self._preview_capture = capture
            self._preview_video_frame_count = int(
                capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            )
        else:
            if notify:
                QMessageBox.critical(
                    self,
                    "Unsupported preview media",
                    "The paired preview background must be an image or video file.",
                )
            return False
        self._preview_media_path = resolved
        if self._preview_original is not None:
            self._show_preview_frame(self.preview_slider.value())
        return True

    def _release_preview_capture(self) -> None:
        if self._preview_capture is not None:
            self._preview_capture.release()
            self._preview_capture = None

    def _preview_inputs_changed(self, *_args) -> None:
        self._invalidate_preview()
        self._maybe_generate_previews()

    def _invalidate_preview(self, *_args) -> None:
        self._preview_original = None
        self._preview_corrected = None
        self._preview_report = None
        self._preview_cache.clear()
        self._active_preview_pair_key = None
        self._preview_frame_positions = ()
        self.preview_slider.setEnabled(False)
        self.preview_slider.setRange(0, 0)
        self.preview_frame_label.setText("Frame —")
        self.preview_frame_label.setToolTip("")
        if self._pixels_per_cm is None:
            empty_message = "Import a calibration map to generate previews"
            status_message = "Preview unavailable until a calibration map is imported."
        elif not any(pair.is_paired for pair in self._pairs):
            empty_message = "Add a paired CSV, H5, and video to generate previews"
            status_message = "Preview unavailable until every dataset is paired."
        else:
            empty_message = "Generating previews…"
            status_message = "Generating previews after changing inputs."
        self.knee_preview.set_empty_message(empty_message)
        self.knee_preview.clear_points()
        self._update_preview_navigation()
        if hasattr(self, "preview_status_label"):
            self.preview_status_label.setText(status_message)

    def _preview_media_name(self) -> str:
        return self._preview_media_path.name if self._preview_media_path is not None else ""

    def _pair_key(self, pair: CoordinateFilePair) -> tuple[str, str, str] | None:
        if pair.csv_path is None or pair.h5_path is None or pair.video_path is None:
            return None
        return (str(pair.csv_path), str(pair.h5_path), str(pair.video_path))

    def _selected_preview_pair(self) -> CoordinateFilePair | None:
        selected = self.pair_table.selectedItems()
        if selected:
            index = self.pair_table.indexOfTopLevelItem(selected[0])
            if 0 <= index < len(self._pairs) and self._pairs[index].is_paired:
                return self._pairs[index]
        return next((pair for pair in self._pairs if pair.is_paired), None)

    def _generate_preview(self) -> None:
        self._generate_all_previews(show_errors=True)

    def _maybe_generate_previews(self) -> None:
        if self._pixels_per_cm is None:
            return
        if not any(pair.is_paired for pair in self._pairs):
            return
        self._generate_all_previews(show_errors=False)

    def _generate_all_previews(self, show_errors: bool) -> None:
        if self._pixels_per_cm is None:
            self._invalidate_preview()
            if show_errors:
                QMessageBox.information(
                    self,
                    "Calibration required",
                    "Import a calibration map first.",
                )
            return
        paired = [pair for pair in self._pairs if pair.is_paired]
        if not paired:
            self._invalidate_preview()
            if show_errors:
                QMessageBox.information(
                    self,
                    "No paired dataset",
                    "Add or select a paired CSV, H5, and video dataset.",
                )
            return
        self._preview_cache.clear()
        errors: list[str] = []
        for pair in paired:
            key = self._pair_key(pair)
            if key is None or pair.csv_path is None:
                continue
            try:
                original = read_dlc_csv(pair.csv_path)
                corrected, reports = correct_knee_dataframe(original, self._settings())
            except Exception as exc:
                errors.append(f"{pair.stem}: {exc}")
                continue
            report = reports[0]
            self._preview_cache[key] = (
                original,
                corrected,
                report,
                _previewable_frame_positions(report.frame_statuses),
            )
        if errors:
            for message in errors:
                self.log.appendPlainText(f"[Preview] {message}")
            if show_errors:
                QMessageBox.warning(
                    self,
                    "Some previews could not be generated",
                    "\n".join(errors[:5]),
                )
        if not self._preview_cache:
            self._active_preview_pair_key = None
            self.knee_preview.set_empty_message("Could not generate a preview")
            self.knee_preview.clear_points()
            self.preview_status_label.setText("Could not generate previews.")
            return
        self._show_selected_preview()
        self.log.appendPlainText(
            f"[Preview] Generated {len(self._preview_cache)} preview(s)."
        )

    def _show_selected_preview(self) -> None:
        pair = self._selected_preview_pair()
        if pair is None or pair.csv_path is None or pair.video_path is None:
            if self._pixels_per_cm is None:
                self.knee_preview.set_empty_message("Import a calibration map to generate previews")
            else:
                self.knee_preview.set_empty_message("Add a paired CSV, H5, and video")
            self.knee_preview.clear_points()
            return
        key = self._pair_key(pair)
        if key is None:
            return
        if key not in self._preview_cache:
            if self._pixels_per_cm is None:
                self._invalidate_preview()
            else:
                self._maybe_generate_previews()
            if key not in self._preview_cache:
                self.knee_preview.set_empty_message("Preview could not be generated")
                self.knee_preview.clear_points()
                self.preview_status_label.setText(f"{pair.stem} • preview unavailable")
                return
        if self._preview_static_image is None and self._preview_media_path != pair.video_path:
            self._set_preview_media(pair.video_path, notify=False)
        original, corrected, report, frame_positions = self._preview_cache[key]
        self._active_preview_pair_key = key
        previous_value = self.preview_slider.value()
        self._preview_original = original
        self._preview_corrected = corrected
        self._preview_report = report
        self._preview_frame_positions = frame_positions
        self.preview_slider.blockSignals(True)
        self.preview_slider.setRange(0, max(0, len(frame_positions) - 1))
        self.preview_slider.setEnabled(len(frame_positions) > 0)
        self.preview_slider.setValue(min(previous_value, self.preview_slider.maximum()))
        self.preview_slider.blockSignals(False)
        if len(original) == 0:
            self.knee_preview.set_empty_message("Preview has no frames")
            self.knee_preview.clear_points()
            self.preview_status_label.setText(f"{pair.stem} • preview has no frames")
            self._update_preview_navigation()
            return
        if not frame_positions:
            self.knee_preview.set_empty_message("No frames meet the confidence cutoff")
            self.knee_preview.clear_points()
            self.preview_status_label.setText(
                f"{pair.stem} • no frames meet confidence cutoff"
            )
            self.preview_frame_label.setText("Frame —")
            self.preview_frame_label.setToolTip("")
            self._update_preview_navigation()
            return
        media_name = self._preview_media_name()
        media_suffix = f" • frame: {media_name}" if media_name else ""
        self.preview_status_label.setText(f"{pair.stem} • {report.knee}{media_suffix}")
        self._show_preview_frame(self.preview_slider.value())
        self.knee_preview.setFocus()

    def _show_preview_frame(self, frame_position: int) -> None:
        if (
            self._preview_original is None
            or self._preview_corrected is None
            or self._preview_report is None
            or len(self._preview_original) == 0
            or not self._preview_frame_positions
        ):
            return
        preview_position = max(
            0, min(int(frame_position), len(self._preview_frame_positions) - 1)
        )
        position = self._preview_frame_positions[preview_position]
        report = self._preview_report
        hip = _bodypart_point(self._preview_original, report.hip, position)
        ankle = _bodypart_point(self._preview_original, report.ankle, position)
        old_knee = _bodypart_point(self._preview_original, report.knee, position)
        correction_status = report.frame_statuses[position]
        new_knee = (
            _bodypart_point(self._preview_corrected, report.knee, position)
            if correction_status == "Corrected"
            else None
        )
        background_frame, media_status = self._preview_frame_image(position)
        self.knee_preview.set_points(
            hip,
            ankle,
            old_knee,
            new_knee,
            correction_status,
            background_frame=background_frame,
        )
        frame_name = self._preview_original.index[position]
        unavailable = []
        if hip is None:
            unavailable.append("hip")
        if ankle is None:
            unavailable.append("ankle")
        if old_knee is None:
            unavailable.append("old knee")
        frame_status = (
            "corrected"
            if correction_status == "Corrected"
            else f"retained: {correction_status}"
        )
        if unavailable:
            frame_status += " • unavailable: " + ", ".join(unavailable)
        if media_status:
            frame_status += f" • {media_status}"
        frame_label = (
            f"Frame {frame_name} • preview {preview_position + 1}/"
            f"{len(self._preview_frame_positions)} • {frame_status}"
        )
        self.preview_frame_label.setText(frame_label)
        self.preview_frame_label.setToolTip(frame_label)
        self._update_preview_navigation()

    def _step_preview_frame(self, delta: int) -> None:
        if not self.preview_slider.isEnabled():
            return
        current = self.preview_slider.value()
        target = max(
            self.preview_slider.minimum(),
            min(self.preview_slider.maximum(), current + int(delta)),
        )
        if target != current:
            self.preview_slider.setValue(target)
        else:
            self._update_preview_navigation()
        self.knee_preview.setFocus()

    def _update_preview_navigation(self) -> None:
        has_frames = (
            self.preview_slider.isEnabled()
            and self.preview_slider.maximum() > self.preview_slider.minimum()
        )
        value = self.preview_slider.value()
        self.previous_frame_button.setEnabled(has_frames and value > self.preview_slider.minimum())
        self.next_frame_button.setEnabled(has_frames and value < self.preview_slider.maximum())

    def _preview_frame_image(self, position: int) -> tuple[QImage | None, str | None]:
        if self._preview_static_image is not None:
            return self._preview_static_image, None
        if self._preview_capture is None or cv2 is None:
            return None, None
        frame_index = max(0, int(position))
        if self._preview_video_frame_count > 0:
            frame_index = min(frame_index, self._preview_video_frame_count - 1)
        self._preview_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = self._preview_capture.read()
        if not ok or frame is None:
            return None, "video frame unavailable"
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        return (
            QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy(),
            None,
        )

    def _update_run_state(self) -> None:
        running = self._worker is not None and self._worker.isRunning()
        complete_pairs = bool(self._pairs) and all(pair.is_paired for pair in self._pairs)
        has_output = bool(self.output_folder_edit.text().strip())
        has_calibration = self._pixels_per_cm is not None
        self.run_button.setEnabled(
            complete_pairs and has_output and has_calibration and not running
        )
        if not self._pairs:
            self.status_label.setText("Add matching CSV, H5, and video files.")
        elif not complete_pairs:
            self.status_label.setText("Red datasets are missing a matching CSV, H5, or video.")
        elif not has_calibration:
            self.status_label.setText("Import a calibration map to convert centimeters to pixels.")
        else:
            self.status_label.setText(
                f"{len(self._pairs)} paired dataset(s) ready • {self._pixels_per_cm:.3f} px/cm."
            )

    def _settings(self) -> KneeCorrectionSettings:
        selected_label = self.knee_label_combo.currentData()
        selected_hip = self.hip_label_combo.currentData()
        selected_ankle = self.ankle_label_combo.currentData()
        return KneeCorrectionSettings(
            hip_knee_length_cm=self.hip_knee_length.value(),
            knee_ankle_length_cm=self.knee_ankle_length.value(),
            pixels_per_cm=float(self._pixels_per_cm or 0),
            likelihood_threshold=self.likelihood_threshold.value(),
            knee_bodyparts=(str(selected_label),) if selected_label else None,
            hip_bodypart=str(selected_hip) if selected_hip else None,
            ankle_bodypart=str(selected_ankle) if selected_ankle else None,
            output_knee_bodypart=self.generated_knee_label_edit.text().strip() or "knee",
            knee_direction=str(self.knee_direction_combo.currentData() or "auto"),
        )

    def _run(self) -> None:
        if not self._pairs or not all(pair.is_paired for pair in self._pairs):
            QMessageBox.warning(
                self,
                "Pairs required",
                "Pair every CSV with one matching H5 and video file.",
            )
            return
        if self._pixels_per_cm is None:
            QMessageBox.warning(
                self,
                "Calibration required",
                "Import a calibration map before correcting knee labels.",
            )
            return
        output_folder = Path(self.output_folder_edit.text()).expanduser().resolve()
        existing = [
            output_folder / f"{pair.stem}_knee_corrected{extension}"
            for pair in self._pairs
            for extension in (".csv", ".h5")
            if (output_folder / f"{pair.stem}_knee_corrected{extension}").exists()
        ]
        if existing and QMessageBox.question(
            self,
            "Replace corrected outputs?",
            "Corrected output files already exist and will be replaced. Keep a backup. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.progress.setValue(0)
        self.log.clear()
        self._worker = KneeCorrectionThread(
            tuple(self._pairs), output_folder, self._settings()
        )
        self._worker.progress_updated.connect(self._progress_updated)
        self._worker.completed.connect(self._completed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()
        self._update_run_state()

    def _progress_updated(self, value: int, message: str) -> None:
        self.progress.setValue(value)
        self.status_label.setText(message)
        self.log.appendPlainText(message)

    def _completed(self, success: bool, message: str) -> None:
        self.status_label.setText(message)
        if success:
            self.progress.setValue(100)
            QMessageBox.information(self, "Knee correction complete", message)
        else:
            QMessageBox.critical(self, "Knee correction failed", message)

    def _worker_finished(self) -> None:
        self._worker = None
        self._update_run_state()

    def can_close(self, parent=None) -> bool:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(
                parent or self,
                "Knee correction is running",
                "Wait for the paired label files to finish before leaving this tool.",
            )
            return False
        return True

    def release_resources(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait()
        self._release_preview_capture()

    def _default_output_folder(self) -> Path:
        path = self._project_root / "outputs" / "knee_correction"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _apply_style(self) -> None:
        settings_tab_style = """
            QTabWidget#KneeCorrectionSettingsTabs {
                background: {theme.PANEL};
            }
            QTabWidget#KneeCorrectionSettingsTabs::pane {
                background: {theme.BACKGROUND};
                border: 0;
                border-top: 1px solid {theme.BORDER};
            }
            QTabWidget#KneeCorrectionSettingsTabs QTabBar::tab {
                background: {theme.PANEL};
            }
            QTabWidget#KneeCorrectionSettingsTabs QTabBar::tab:selected {
                background: {theme.SURFACE};
            }
        """
        self.setStyleSheet(
            theme.workspace_stylesheet(
                "KneeCorrectionWidget",
                settings_tab_style
                + """
                QTreeWidget#KneePairTable {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                }
                QWidget#KneeStickplotPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                }
                """,
            )
        )


class KneeStickplotPreview(QWidget):
    def __init__(self):
        super().__init__()
        self._hip: tuple[float, float] | None = None
        self._ankle: tuple[float, float] | None = None
        self._old_knee: tuple[float, float] | None = None
        self._new_knee: tuple[float, float] | None = None
        self._background_frame: QImage | None = None
        self._correction_status = ""
        self._has_frame = False
        self._empty_message = "Generate a frame preview"

    def set_empty_message(self, message: str) -> None:
        self._empty_message = message
        if not self._has_frame:
            self.update()

    def set_points(
        self,
        hip: tuple[float, float] | None,
        ankle: tuple[float, float] | None,
        old_knee: tuple[float, float] | None,
        new_knee: tuple[float, float] | None,
        correction_status: str = "Corrected",
        background_frame: QImage | None = None,
    ) -> None:
        self._hip = hip
        self._ankle = ankle
        self._old_knee = old_knee
        self._new_knee = new_knee
        self._background_frame = background_frame
        self._correction_status = correction_status
        self._has_frame = True
        self.update()

    def clear_points(self) -> None:
        self._hip = None
        self._ankle = None
        self._old_knee = None
        self._new_knee = None
        self._background_frame = None
        self._correction_status = ""
        self._has_frame = False
        self.update()

    def _draw_background_frame(
        self,
        painter: QPainter,
        points: list[tuple[float, float]],
    ) -> tuple[QRectF, QRectF] | None:
        if self._background_frame is None or self._background_frame.isNull():
            return None
        image = self._background_frame
        source = self._frame_crop_rect(points, image.width(), image.height())
        scale = min(self.width() / source.width(), self.height() / source.height())
        width = max(1.0, source.width() * scale)
        height = max(1.0, source.height() * scale)
        left = (self.width() - width) / 2
        top = (self.height() - height) / 2
        target = QRectF(left, top, width, height)
        painter.drawImage(target, image, source)
        painter.fillRect(target, QColor(0, 0, 0, 30))
        return target, source

    def _frame_crop_rect(
        self,
        points: list[tuple[float, float]],
        image_width: int,
        image_height: int,
    ) -> QRectF:
        finite_points = [
            (float(x), float(y))
            for x, y in points
            if x == x and y == y
        ]
        if not finite_points:
            return QRectF(0.0, 0.0, float(image_width), float(image_height))

        xs = [point[0] for point in finite_points]
        ys = [point[1] for point in finite_points]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        limb_span = max(span_x, span_y)
        padding = max(40.0, limb_span * 0.75)
        crop_width = max(span_x + padding * 2, 160.0)
        crop_height = max(span_y + padding * 2, 140.0)
        crop_width = min(float(image_width), crop_width)
        crop_height = min(float(image_height), crop_height)
        center_x = min(max((min_x + max_x) / 2, crop_width / 2), image_width - crop_width / 2)
        center_y = min(max((min_y + max_y) / 2, crop_height / 2), image_height - crop_height / 2)
        left = min(max(0.0, center_x - crop_width / 2), image_width - crop_width)
        top = min(max(0.0, center_y - crop_height / 2), image_height - crop_height)
        return QRectF(left, top, crop_width, crop_height)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(theme.CANVAS))
        available_points = [
            point
            for point in (self._hip, self._ankle, self._old_knee, self._new_knee)
            if point is not None
        ]
        image_mapping = self._draw_background_frame(painter, available_points)
        if not self._has_frame:
            painter.setPen(QColor(theme.CONNECTOR))
            painter.drawText(self.rect(), Qt.AlignCenter | Qt.TextWordWrap, self._empty_message)
            return
        missing = []
        if self._hip is None:
            missing.append("Hip unavailable (NaN coordinates)")
        if self._ankle is None:
            missing.append("Ankle unavailable (NaN coordinates)")
        if self._old_knee is None:
            missing.append("Old knee unavailable (missing/NaN coordinates)")
        if missing:
            painter.setPen(QColor("#aaa6a0"))
            for index, message in enumerate(missing):
                painter.drawText(
                    self.rect().adjusted(10, 8 + index * 16, -10, -8),
                    Qt.AlignTop | Qt.AlignRight,
                    message,
                )
        if self._correction_status and self._correction_status != "Corrected":
            painter.setPen(QColor(theme.STATUS_ERROR))
            painter.drawText(
                self.rect().adjusted(10, 8, -10, -8),
                Qt.AlignTop | Qt.AlignLeft,
                f"Retained: {self._correction_status}",
            )
        if self._hip is None or self._ankle is None:
            painter.setPen(QColor(theme.CONNECTOR))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Stickplot unavailable without both hip and ankle coordinates",
            )
            return

        margin = 42
        if image_mapping is not None:
            image_rect, source_rect = image_mapping

            def mapped(point: tuple[float, float]) -> tuple[int, int]:
                return (
                    int(
                        image_rect.left()
                        + (point[0] - source_rect.left())
                        * image_rect.width()
                        / max(1.0, source_rect.width())
                    ),
                    int(
                        image_rect.top()
                        + (point[1] - source_rect.top())
                        * image_rect.height()
                        / max(1.0, source_rect.height())
                    ),
                )

        else:
            xs = [point[0] for point in available_points]
            ys = [point[1] for point in available_points]
            x_span = max(max(xs) - min(xs), 1.0)
            y_span = max(max(ys) - min(ys), 1.0)
            draw_width = max(1, self.width() - margin * 2)
            draw_height = max(1, self.height() - margin * 2 - 24)
            scale = min(draw_width / x_span, draw_height / y_span)
            x_offset = margin + (draw_width - x_span * scale) / 2
            y_offset = margin + (draw_height - y_span * scale) / 2

            def mapped(point: tuple[float, float]) -> tuple[int, int]:
                return (
                    int(x_offset + (point[0] - min(xs)) * scale),
                    int(y_offset + (point[1] - min(ys)) * scale),
                )

        hip = mapped(self._hip)
        ankle = mapped(self._ankle)
        old_knee = mapped(self._old_knee) if self._old_knee is not None else None
        new_knee = mapped(self._new_knee) if self._new_knee is not None else None

        if old_knee is not None:
            old_pen = QPen(QColor("#aaa6a0"), 2, Qt.DashLine)
            painter.setPen(old_pen)
            painter.drawLine(*hip, *old_knee)
            painter.drawLine(*old_knee, *ankle)
            painter.setBrush(QColor("#aaa6a0"))
            painter.drawEllipse(old_knee[0] - 4, old_knee[1] - 4, 8, 8)

        chain_color = QColor(theme.CANVAS_TEXT)
        if new_knee is not None:
            painter.setPen(QPen(chain_color, 4))
            painter.drawLine(*hip, *new_knee)
            painter.drawLine(*new_knee, *ankle)
        painter.setPen(QPen(chain_color, 2))
        painter.setBrush(chain_color)
        for point in (hip, ankle):
            painter.drawEllipse(point[0] - 6, point[1] - 6, 12, 12)
        if new_knee is not None:
            corrected_color = QColor(theme.STATUS_READY)
            painter.setPen(QPen(corrected_color, 2))
            painter.setBrush(corrected_color)
            painter.drawEllipse(new_knee[0] - 8, new_knee[1] - 8, 16, 16)

        painter.setPen(QColor(theme.CANVAS_TEXT))
        painter.drawText(hip[0] + 8, hip[1] - 8, "Hip")
        painter.drawText(ankle[0] + 8, ankle[1] - 8, "Ankle")
        if old_knee is not None:
            painter.setPen(QColor("#8e8a84"))
            painter.drawText(old_knee[0] + 7, old_knee[1] + 14, "Old knee")
        if new_knee is not None:
            painter.setPen(QColor(theme.STATUS_READY))
            painter.drawText(new_knee[0] + 9, new_knee[1] - 9, "Corrected knee")

        legend_y = self.height() - 12
        painter.setPen(QPen(QColor("#aaa6a0"), 2, Qt.DashLine))
        painter.drawLine(margin, legend_y, margin + 22, legend_y)
        painter.setPen(QColor(theme.CONNECTOR))
        painter.drawText(margin + 28, legend_y + 4, "Original")
        painter.setPen(QPen(chain_color, 4))
        painter.drawLine(margin + 105, legend_y, margin + 127, legend_y)
        painter.setPen(QColor(theme.CANVAS_TEXT))
        painter.drawText(margin + 133, legend_y + 4, "Corrected")


class KneeCorrectionThread(QThread):
    progress_updated = Signal(int, str)
    completed = Signal(bool, str)

    def __init__(
        self,
        pairs: tuple[CoordinateFilePair, ...],
        output_folder: Path,
        settings: KneeCorrectionSettings,
    ):
        super().__init__()
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
                    round((index - 1) / len(self._pairs) * 100),
                    f"Correcting {pair.stem} ({index}/{len(self._pairs)})…",
                )
                result = correct_knee_pair(pair, self._output_folder, self._settings)
                self.results.append(result)
                for marker in result.markers:
                    self.progress_updated.emit(
                        round(index / len(self._pairs) * 100),
                        f"{pair.stem}: {marker.knee} corrected in "
                        f"{marker.corrected_frames} frame(s).",
                    )
                    retained_reasons = Counter(
                        status for status in marker.frame_statuses if status != "Corrected"
                    )
                    for reason, count in sorted(retained_reasons.items()):
                        self.progress_updated.emit(
                            round(index / len(self._pairs) * 100),
                            f"{pair.stem}: retained {count} frame(s) — {reason}.",
                        )
            self.completed.emit(
                True,
                f"Created corrected CSV and H5 files for {len(self.results)} dataset(s).",
            )
        except Exception as exc:
            self.completed.emit(False, str(exc))


def _length_spin() -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.001, 1000.0)
    spin.setDecimals(3)
    spin.setValue(1.5)
    spin.setSuffix(" cm")
    return spin


def _bodypart_point(dataframe, bodypart: str, position: int) -> tuple[float, float] | None:
    x_column = next(
        (
            column
            for column in dataframe.columns
            if str(column[-2]) == bodypart and str(column[-1]).casefold() == "x"
        ),
        None,
    )
    y_column = next(
        (
            column
            for column in dataframe.columns
            if str(column[-2]) == bodypart and str(column[-1]).casefold() == "y"
        ),
        None,
    )
    if x_column is None or y_column is None:
        return None
    x = float(dataframe.iloc[position][x_column])
    y = float(dataframe.iloc[position][y_column])
    if not (x == x and y == y):
        return None
    return x, y


def _previewable_frame_positions(frame_statuses: tuple[str, ...]) -> tuple[int, ...]:
    return tuple(
        index
        for index, status in enumerate(frame_statuses)
        if not status.startswith("Low-confidence")
    )
