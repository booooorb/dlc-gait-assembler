"""Edit reference/manual/imported calibration and per-camera spatial scale controls."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import reference_segment_label
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_analysis_settings_panel import double_spin
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_disclosure import GaitDisclosure
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip

CALIBRATION_METHOD_LABELS = {
    "reference": "Reference body segment",
    "manual": "Manual pixel-to-cm ratio",
    "map": "Shared calibration map",
    "per_view": "Calibration by view",
    "treadmill": "Treadmill speed",
}


class GaitCalibrationPanel:
    """GaitCalibrationPanel operates on its explicitly supplied AlmaKinematicsWidget view."""

    def __init__(self, view):
        self.view = view

    def _import_calibration_map(self) -> None:
        default_folder = self.view.workspace.manual / "calibration"
        (filename, _) = QFileDialog.getOpenFileName(
            self.view,
            "Import calibration conversion map",
            str(default_folder),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename).expanduser().resolve()
        try:
            (pixels_per_cm, source) = self.view.analysis.settings.calibration_scale(path)
        except Exception as exc:
            QMessageBox.critical(self.view, "Could not import calibration map", str(exc))
            return
        self.view.state.calibration_map_path = path
        self.view.state.calibration_map_source = source
        self.view.state.calibration_map_pixels_per_cm = pixels_per_cm
        self.view.calibration_method_combo.setCurrentText(CALIBRATION_METHOD_LABELS["map"])
        self.view.calibration_map_label.setText(f"{path.name} | {source}: {pixels_per_cm:.3f} px/cm")
        self.view.status_label.setText("Calibration map imported.")
        self.view.controller._append_log(f"Calibration map imported from {path}: {pixels_per_cm:.3f} px/cm ({source})")
        self._update_calibration_method()
        self.view.controller._invalidate_stickplot_preview()

    def _import_view_calibration(self, view_name):
        filename, _ = QFileDialog.getOpenFileName(
            self.view,
            f"Import {view_name} calibration map",
            str(self.view.workspace.manual / "calibration"),
            "JSON maps (*.json)",
        )
        if not filename:
            return
        try:
            nodes = self.view.analysis.settings.camera_map_views(filename)
            view_index = None
            if len(nodes) > 1:
                key, accepted = QInputDialog.getItem(
                    self.view,
                    f"{view_name.title()} camera",
                    "Choose the camera/view in this map",
                    list(nodes),
                    0,
                    False,
                )
                if not accepted:
                    return
                view_index = int(key)
            elif nodes:
                view_index = int(next(iter(nodes)))
            scales, source = self.view.analysis.settings.camera_map_scales(filename, view_index)
        except Exception as exc:
            QMessageBox.warning(self.view, "Calibration map", str(exc))
            return
        if view_name == "bottom":
            self.view.bottom_x_pixels_per_cm_spin.setValue(scales["x_pixels_per_cm"])
            self.view.bottom_y_pixels_per_cm_spin.setValue(scales["y_pixels_per_cm"])
        else:
            self.view.view_scale_spins[view_name].setValue(scales["pixels_per_cm"])
        self.view.view_calibration_sources[view_name] = {
            "map_path": str(Path(filename).resolve()),
            "source": source,
            "view_index": view_index,
        }
        self.view.view_map_labels[view_name].setText(f"{Path(filename).name} · {source}")
        self.view.calibration_method_combo.setCurrentText(CALIBRATION_METHOD_LABELS["per_view"])
        self.view.controller._invalidate_stickplot_preview()

    def _collect_view_calibration(self):
        if self.view.calibration_method_combo.currentData() != "per_view":
            return None
        values = {}
        for side, spin in self.view.view_scale_spins.items():
            if spin.value() > 0:
                values[side] = {**self.view.view_calibration_sources.get(side, {}), "pixels_per_cm": spin.value()}
        x, y = self.view.bottom_x_pixels_per_cm_spin.value(), self.view.bottom_y_pixels_per_cm_spin.value()
        if x > 0 or y > 0:
            values["bottom"] = {
                **self.view.view_calibration_sources.get("bottom", {}),
                **{key: value for key, value in (("x_pixels_per_cm", x), ("y_pixels_per_cm", y)) if value > 0},
            }
        return values or None

    def collect_settings(self):
        method = self.view.calibration_method_combo.currentData()
        return {
            "calibration_method": method,
            "reference_segment": self.view.reference_segment_combo.currentText().split(" ", 1)[0],
            "reference_length_cm": self.view.reference_length_spin.value(),
            "pixels_per_cm": self.view.pixels_per_cm_spin.value() if method == "manual"
            else self.view.state.calibration_map_pixels_per_cm if method == "map" else None,
            "calibration_map_path": self.view.state.calibration_map_path if method == "map" else None,
            "view_calibration": self._collect_view_calibration(),
        }

    def _update_calibration_method(self) -> None:
        combo = self.view.calibration_method_combo
        three_view = self.view.inputs._is_three_view_mode()
        treadmill = self.view.analysis_type_combo.currentText() == "Treadmill" and not self.view.setup._is_rustlab1_workflow()
        for method, available in (("per_view", three_view), ("treadmill", treadmill)):
            combo.model().item(combo.findData(method)).setEnabled(available)
        method = combo.currentData()
        if (method == "per_view" and not three_view) or (method == "treadmill" and not treadmill):
            combo.setCurrentText(CALIBRATION_METHOD_LABELS["reference"])
            return
        self.view.reference_settings_widget.setVisible(method == "reference")
        self.view.manual_settings_widget.setVisible(method == "manual")
        self.view.map_settings_widget.setVisible(method == "map")
        self.view.view_calibration_box.setVisible(method == "per_view")
        set_tooltip(combo, {
            "reference": "Estimate each side camera's scale from its own reference markers. Bottom distances need Calibration by view.",
            "manual": "Apply this one ratio to every camera. Imported maps are saved separately.",
            "map": "Apply the imported map's shared scale to every camera.",
            "per_view": "Use only the scale entered for each camera. Missing scales never use a shared ratio or another camera.",
            "treadmill": "Estimate each side camera's scale from paw motion and the configured belt speed. Bottom distances remain uncalibrated.",
        }[method])


def build_gait_calibration(self, calibration_tab_layout, setup_tab_layout):
    camera_link_box = QGroupBox("Left / Right / Bottom calibration")
    camera_link_layout = QVBoxLayout(camera_link_box)
    self.edit_view_calibration_button = QPushButton("Edit calibration by view…")
    set_tooltip(
        self.edit_view_calibration_button,
        "Set separate camera maps and scales in Calibration before comparing gait parameters.",
    )

    def show_camera_calibration():
        if self.inputs._is_three_view_mode():
            self.calibration_method_combo.setCurrentText(CALIBRATION_METHOD_LABELS["per_view"])
        self.settings_tabs.setCurrentWidget(self.calibration_tab)
        self.controls_scroll.ensureWidgetVisible(self.view_calibration_box)

    self.edit_view_calibration_button.clicked.connect(show_camera_calibration)
    camera_link_layout.addWidget(self.edit_view_calibration_button)
    setup_tab_layout.addWidget(camera_link_box)
    calibration_box = QGroupBox("Spatial calibration")
    self.calibration_box = calibration_box
    calibration_layout = QVBoxLayout(calibration_box)
    self.calibration_method_combo = QComboBox()
    for method, label in CALIBRATION_METHOD_LABELS.items():
        self.calibration_method_combo.addItem(label, method)
    self.calibration_method_combo.setCurrentText(CALIBRATION_METHOD_LABELS[self._defaults.calibration_method])
    if self._defaults.calibration_method == "map":
        self.state.calibration_map_path = self._defaults.calibration_map_path
        self.state.calibration_map_pixels_per_cm = self._defaults.pixels_per_cm
    set_tooltip(self.calibration_method_combo, "Select one spatial calibration mode for preview and analysis.")
    calibration_layout.addWidget(self.calibration_method_combo)
    self.reference_settings_widget = QWidget()
    reference_layout = QGridLayout(self.reference_settings_widget)
    reference_layout.setContentsMargins(16, 4, 0, 0)
    reference_layout.setHorizontalSpacing(12)
    reference_layout.setVerticalSpacing(4)
    self.reference_segment_combo = QComboBox()
    self.reference_segment_combo.addItems(
        ["ankle_toe", "hip_knee", "knee_ankle", "ankle_mtp"]
    )
    self.reference_segment_combo.setCurrentText(reference_segment_label(self._defaults.reference_segment))
    self.reference_length_spin = double_spin(0.0, 10.0, self._defaults.reference_length_cm, 2)
    self.reference_length_spin.setSpecialValueText("Enter measured length")
    set_tooltip(self.reference_segment_combo, "Body segment used as the reference calibration length.")
    set_tooltip(self.reference_length_spin, "Known length of the selected reference segment in centimeters.")
    reference_layout.addWidget(QLabel("Reference segment"), 0, 0)
    reference_layout.addWidget(self.reference_segment_combo, 0, 1)
    reference_layout.addWidget(QLabel("Segment length (cm)"), 1, 0)
    reference_layout.addWidget(self.reference_length_spin, 1, 1)
    calibration_layout.addWidget(self.reference_settings_widget)
    self.manual_settings_widget = QWidget()
    manual_layout = QGridLayout(self.manual_settings_widget)
    manual_layout.setContentsMargins(16, 4, 0, 0)
    manual_layout.setHorizontalSpacing(12)
    manual_layout.setVerticalSpacing(4)
    self.pixels_per_cm_spin = double_spin(0.0, 1000.0, self._defaults.pixels_per_cm or 0.0, 4)
    self.pixels_per_cm_spin.setSpecialValueText("Enter measured scale")
    manual_layout.addWidget(QLabel("Pixels per cm"), 0, 0)
    manual_layout.addWidget(self.pixels_per_cm_spin, 0, 1)
    calibration_layout.addWidget(self.manual_settings_widget)
    self.map_settings_widget = QWidget()
    map_layout = QVBoxLayout(self.map_settings_widget)
    map_layout.setContentsMargins(16, 4, 0, 0)
    self.import_calibration_map_button = QPushButton("Import calibration map")
    set_tooltip(self.pixels_per_cm_spin, "Manual pixel-to-centimeter ratio.")
    set_tooltip(self.import_calibration_map_button, "Import a calibration conversion map.", "Ctrl+M")
    self.calibration_map_label = QLabel("No calibration map imported.")
    if self.state.calibration_map_pixels_per_cm is not None:
        self.calibration_map_label.setText(f"Configured map scale: {self.state.calibration_map_pixels_per_cm:g} px/cm")
    self.calibration_map_label.setObjectName("MutedLabel")
    self.calibration_map_label.setWordWrap(True)
    map_layout.addWidget(self.import_calibration_map_button)
    map_layout.addWidget(self.calibration_map_label)
    calibration_layout.addWidget(self.map_settings_widget)
    stroke_calibration_widget = QWidget()
    self.stroke_calibration_widget = stroke_calibration_widget
    stroke_calibration_layout = QGridLayout(stroke_calibration_widget)
    stroke_calibration_layout.setContentsMargins(0, 0, 0, 0)
    configured_bottom = (self._defaults.view_calibration or {}).get("bottom", {})
    if isinstance(configured_bottom, (int, float)):
        bottom_x_default = bottom_y_default = float(configured_bottom)
    elif isinstance(configured_bottom, dict):
        bottom_x_default = float(configured_bottom.get("x_pixels_per_cm", configured_bottom.get("pixels_per_cm", 0.0)))
        bottom_y_default = float(configured_bottom.get("y_pixels_per_cm", configured_bottom.get("pixels_per_cm", 0.0)))
    else:
        bottom_x_default = bottom_y_default = 0.0
    self.bottom_x_pixels_per_cm_spin = double_spin(0.0, 2000.0, bottom_x_default, 4)
    self.bottom_y_pixels_per_cm_spin = double_spin(0.0, 2000.0, bottom_y_default, 4)
    self.bottom_x_pixels_per_cm_spin.setSpecialValueText("Not calibrated")
    self.bottom_y_pixels_per_cm_spin.setSpecialValueText("Not calibrated")
    set_tooltip(
        self.bottom_x_pixels_per_cm_spin,
        "Bottom-view horizontal calibration. Set both axes for bottom distances; unset axes remain uncalibrated.",
    )
    set_tooltip(
        self.bottom_y_pixels_per_cm_spin,
        "Bottom-view vertical calibration. Axis-specific values account for mirror distortion.",
    )
    self.bottom_x_pixels_per_cm_label = QLabel("Bottom X pixels per cm")
    self.bottom_y_pixels_per_cm_label = QLabel("Bottom Y pixels per cm")
    stroke_calibration_layout.addWidget(self.bottom_x_pixels_per_cm_label, 0, 0)
    stroke_calibration_layout.addWidget(self.bottom_x_pixels_per_cm_spin, 0, 1)
    stroke_calibration_layout.addWidget(self.bottom_y_pixels_per_cm_label, 1, 0)
    stroke_calibration_layout.addWidget(self.bottom_y_pixels_per_cm_spin, 1, 1)
    self.view_scale_spins, self.view_map_labels, self.view_calibration_sources = {}, {}, {}
    self.view_map_buttons = {}
    views_box = QGroupBox("Calibration by view")
    self.view_calibration_box = views_box
    views_layout = QGridLayout(views_box)
    views_layout.setHorizontalSpacing(8)
    views_layout.setVerticalSpacing(4)
    for index, side in enumerate(("left", "right", "bottom")):
        row = index * 2
        button = QPushButton("Import map…")
        button.setAccessibleName(f"Import {side} calibration map")
        self.view_map_buttons[side] = button
        button.clicked.connect(lambda checked=False, camera=side: self.calibration._import_view_calibration(camera))
        label = QLabel("No separate map imported")
        label.setWordWrap(True)
        label.setObjectName("MutedLabel")
        self.view_map_labels[side] = label
        configured = (self._defaults.view_calibration or {}).get(side, {})
        if isinstance(configured, dict):
            self.view_calibration_sources[side] = {
                k: v for k, v in configured.items() if k in ("map_path", "source", "view_index")
            }
            if configured.get("map_path"):
                label.setText(Path(configured["map_path"]).name)
        if side != "bottom":
            scale = configured.get("pixels_per_cm", 0) if isinstance(configured, dict) else configured
            spin = double_spin(0, 2000, scale, 4)
            set_tooltip(spin, f"Pixels representing one centimeter in the {side} camera. Zero leaves that view uncalibrated.")
            spin.setSpecialValueText("Not calibrated")
            spin.setSuffix(" px/cm")
            spin.setAccessibleName(f"{side.title()} view pixels per cm")
            self.view_scale_spins[side] = spin
            views_layout.addWidget(spin, row, 1)
        views_layout.addWidget(QLabel(f"{side.title()} view"), row, 0)
        views_layout.addWidget(button, row, 2)
        views_layout.addWidget(label, row + 1, 0, 1, 3)
    views_layout.addWidget(stroke_calibration_widget, 6, 0, 1, 3)
    calibration_tab_layout.addWidget(calibration_box)
    calibration_tab_layout.addWidget(views_box)
    calibration_tab_layout.addStretch(1)


def build_gait_timing(self, setup_tab_layout):
    speed_box = QGroupBox("Treadmill speed and calibration")
    self.speed_box = speed_box
    speed_layout = QGridLayout(speed_box)
    speed_layout.setHorizontalSpacing(12)
    speed_layout.setVerticalSpacing(4)
    self.treadmill_speed_label = QLabel("Treadmill speed (cm/s)")
    self.treadmill_speed_spin = double_spin(0.1, 100.0, self._defaults.treadmill_speed_cm_s, 1)
    self.frame_rate_spin = double_spin(1.0, 1000.0, self._defaults.frame_rate, 3)
    self.load_fps_button = QPushButton("From video…")
    set_tooltip(self.treadmill_speed_spin, "Treadmill belt speed in centimeters per second.")
    set_tooltip(self.frame_rate_spin, "Coordinate-video frame rate in frames per second.")
    set_tooltip(self.load_fps_button, "Load frame rate from a video file.", "Ctrl+F")
    speed_layout.addWidget(self.treadmill_speed_label, 0, 0)
    speed_layout.addWidget(self.treadmill_speed_spin, 0, 1, 1, 2)
    self.frame_rate_label = QLabel("Frame rate (fps)")
    speed_layout.addWidget(self.frame_rate_label, 1, 0)
    speed_layout.addWidget(self.frame_rate_spin, 1, 1)
    speed_layout.addWidget(self.load_fps_button, 1, 2)
    setup_tab_layout.addWidget(speed_box)
    self.view_timing_box = QGroupBox()
    timing_layout = QGridLayout(self.view_timing_box)
    timing_layout.addWidget(QLabel("View"), 0, 0)
    timing_layout.addWidget(QLabel("Frame rate (fps)"), 0, 1)
    timing_layout.addWidget(QLabel("Time offset (s)"), 0, 2)
    self.view_fps_spins, self.view_offset_spins = {}, {}
    for row, side in enumerate(("left", "right", "bottom"), 1):
        config = (self._defaults.view_timing or {}).get(side, {})
        fps = double_spin(0.0, 1000.0, config.get("frame_rate", 0.0), 3)
        fps.setSpecialValueText("Shared FPS")
        offset = double_spin(-3600.0, 3600.0, config.get("offset_s", 0.0), 6)
        self.view_fps_spins[side], self.view_offset_spins[side] = fps, offset
        timing_layout.addWidget(QLabel(side.title()), row, 0)
        timing_layout.addWidget(fps, row, 1)
        timing_layout.addWidget(offset, row, 2)
        set_tooltip(
            fps,
            "Zero uses CSV timestamps when present, otherwise the shared video frame rate above. Enter a value if this view has a different FPS.",
        )
        set_tooltip(
            offset,
            "Add this offset to this view’s video timestamps. Positive values move the view later. Leave zero for synchronized crops of the same video.",
        )
    self.view_timing_disclosure = GaitDisclosure("Camera timing (optional)", self.view_timing_box)
    setup_tab_layout.addWidget(self.view_timing_disclosure)

    def reveal_camera_overrides(*_):
        if any(spin.value() != 0 for spin in (*self.view_fps_spins.values(), *self.view_offset_spins.values())):
            self.view_timing_disclosure.set_expanded(True)

    for spin in (*self.view_fps_spins.values(), *self.view_offset_spins.values()):
        spin.valueChanged.connect(reveal_camera_overrides)
    reveal_camera_overrides()
    setup_tab_layout.addStretch(1)
