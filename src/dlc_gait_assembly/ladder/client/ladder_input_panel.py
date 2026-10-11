"""Select left/right coordinate datasets and populate available paw-marker controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
)

from dlc_gait_assembly.ladder.business.ladder_marker_selection import suggested_ladder_bodyparts
from dlc_gait_assembly.shared.business.media_access_contracts import VIDEO_EXTENSIONS


class LadderInputPanel:
    """LadderInputPanel operates on its explicitly supplied LadderAnalysisWidget view."""

    def __init__(self, view):
        self.view = view

    def _choose_csv(self) -> None:
        self._choose_csv_for_view("left" if self.view.controller._is_dual_mode() else "single")

    def _choose_right_csv(self) -> None:
        self._choose_csv_for_view("right")

    def _choose_csv_for_view(self, view: str) -> None:
        (filename, _) = QFileDialog.getOpenFileName(
            self.view,
            f"Choose {view} ladder coordinate CSV",
            str(self.view._project_root),
            "CSV files (*.csv);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename).expanduser().resolve()
        try:
            bodyparts = self.view.use_cases.bodyparts(path)
        except Exception as exc:
            QMessageBox.critical(self.view, "Could not read DLC coordinates", str(exc))
            return
        if view == "right":
            self.view.state.right_csv_path = path
            self.view.right_csv_edit.setText(str(path))
            bodyparts_list = self.view.right_bodyparts_list
        else:
            self.view.state.csv_path = path
            self.view.csv_edit.setText(str(path))
            bodyparts_list = self.view.bodyparts_list
        bodyparts_list.clear()
        suggested = set(suggested_ladder_bodyparts(bodyparts))
        for bodypart in bodyparts:
            item = QListWidgetItem(bodypart)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if bodypart in suggested else Qt.CheckState.Unchecked)
            bodyparts_list.addItem(item)
        self.view.status_label.setText(
            f"Loaded {len(bodyparts)} {view}-view labels. "
            + (
                "Select exactly two paw markers for this camera."
                if self.view.controller._is_dual_mode()
                else "Select the paw markers to analyze."
            )
        )
        self.view.state.events = []
        self.view.events_table.setRowCount(0)
        self.view.save_button.setEnabled(False)
        self.view.controller._update_run_state()

    def _choose_video(self) -> None:
        self._choose_video_for_view("left" if self.view.controller._is_dual_mode() else "single")

    def _choose_right_video(self) -> None:
        self._choose_video_for_view("right")

    def _choose_video_for_view(self, view: str) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        (filename, _) = QFileDialog.getOpenFileName(
            self.view,
            f"Choose {view} ladder video",
            str(self.view._project_root),
            f"Video files ({extensions});;All files (*)",
        )
        if not filename:
            return
        path = Path(filename).expanduser().resolve()
        self.view.video_review._release_video(view)
        try:
            capture = self.view.media_access.open_video(path)
            frame_count = max(1, int(capture.info.frame_count))
            fps = float(capture.info.fps)
            if view == "right":
                self.view._right_video_capture = capture
                self.view.state.right_video_path = path
                self.view.right_video_edit.setText(str(path))
                self.view.right_frame_rate_spin.setValue(fps if fps > 0 else self.view.right_frame_rate_spin.value())
            else:
                self.view._video_capture = capture
                self.view.state.video_path = path
                self.view.video_edit.setText(str(path))
                self.view.frame_rate_spin.setValue(fps if fps > 0 else self.view.frame_rate_spin.value())
            self.view.state.video_frame_counts[view] = frame_count
            self.view.state.active_preview_view = view
            self.view.frame_slider.setRange(0, frame_count - 1)
            self.view.video_review._show_video_frame(0)
        except Exception as exc:
            self.view.video_review._release_video(view)
            QMessageBox.critical(self.view, "Could not load video", str(exc))


def build_ladder_inputs(self, controls_layout):
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
