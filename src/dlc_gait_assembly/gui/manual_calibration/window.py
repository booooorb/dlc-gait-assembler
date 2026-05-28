from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.domain.calibration import CalibrationReport, calculate_calibration_report
from dlc_gait_assembly.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.gui.manual_calibration.preview import CalibrationPreviewView
from dlc_gait_assembly.services.project_paths import find_project_root

try:
    import cv2
except ImportError:
    cv2 = None


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


class ManualCalibrationWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._project_root = find_project_root(__file__)
        self._capture = None
        self._current_media: Path | None = None
        self._duration_ms = 0
        self._loading_slider = False

        self._build_ui()
        self._connect_signals()
        self._apply_style()
        self._update_calibration_results()

    def can_close(self, parent=None) -> bool:
        return True

    def release_resources(self) -> None:
        self._release_capture()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root_layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(12)

        title = QLabel("Manual Calibration")
        title.setObjectName("TitleLabel")
        left_layout.addWidget(title)

        media_box = QGroupBox("Calibration frame")
        media_layout = QVBoxLayout(media_box)
        media_layout.setSpacing(8)
        media_buttons = QHBoxLayout()
        self.open_media_button = QPushButton("Open Image/Video")
        self.open_media_button.setObjectName("OpenMediaButton")
        self.clear_calibration_button = QPushButton("Clear Calibration")
        self.clear_calibration_button.setObjectName("ClearButton")
        media_buttons.addWidget(self.open_media_button)
        media_buttons.addWidget(self.clear_calibration_button)
        media_layout.addLayout(media_buttons)
        self.media_label = QLabel("No calibration image or video loaded.")
        self.media_label.setWordWrap(True)
        self.media_label.setObjectName("MutedLabel")
        media_layout.addWidget(self.media_label)
        left_layout.addWidget(media_box)

        settings_box = QGroupBox("Calibration settings")
        settings_layout = QFormLayout(settings_box)
        settings_layout.setLabelAlignment(Qt.AlignLeft)
        self.tau_spin = QDoubleSpinBox()
        self.tau_spin.setRange(0.1, 20.0)
        self.tau_spin.setDecimals(2)
        self.tau_spin.setSingleStep(0.25)
        self.tau_spin.setSuffix("%")
        self.tau_spin.setValue(2.0)
        settings_layout.addRow("Margin of Calibration Error", self.tau_spin)
        left_layout.addWidget(settings_box)

        results_box = QGroupBox("SOP checks")
        results_layout = QVBoxLayout(results_box)
        self.results_label = QLabel()
        self.results_label.setWordWrap(True)
        self.results_label.setTextFormat(Qt.RichText)
        self.results_label.setOpenExternalLinks(False)
        results_scroll = QScrollArea()
        results_scroll.setWidgetResizable(True)
        results_scroll.setFrameShape(QFrame.NoFrame)
        results_scroll.setWidget(self.results_label)
        results_layout.addWidget(results_scroll)
        left_layout.addWidget(results_box, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(10)

        self.preview_title = QLabel("Open a calibration image or video.")
        self.preview_title.setObjectName("PreviewTitle")
        right_layout.addWidget(self.preview_title)

        tools_bar = QFrame()
        tools_bar.setObjectName("OperationsBar")
        tools_layout = QHBoxLayout(tools_bar)
        tools_layout.setContentsMargins(10, 8, 10, 8)
        tools_layout.setSpacing(8)
        tools_layout.addWidget(QLabel("Tools"))
        self.x_tool_button = _make_tool_button("X Calibration Stick", "#0ea5e9")
        self.y_tool_button = _make_tool_button("Y Calibration Stick", "#f97316")
        self.cm_tool_button = _make_tool_button("Centimeter Marker", "#22c55e")
        self.x_tool_button.setChecked(True)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_group.addButton(self.x_tool_button)
        self.tool_group.addButton(self.y_tool_button)
        self.tool_group.addButton(self.cm_tool_button)
        tools_layout.addWidget(self.x_tool_button)
        tools_layout.addWidget(self.y_tool_button)
        tools_layout.addWidget(self.cm_tool_button)
        tools_layout.addStretch(1)
        self.reset_zoom_button = QPushButton("Reset Zoom")
        self.reset_zoom_button.setObjectName("ResetButton")
        tools_layout.addWidget(self.reset_zoom_button)
        right_layout.addWidget(tools_bar)

        self.preview = CalibrationPreviewView()
        right_layout.addWidget(self.preview, 1)

        timeline_row = QHBoxLayout()
        self.time_label = QLabel("00:00.000 / 00:00.000")
        self.time_label.setMinimumWidth(180)
        self.timeline = QSlider(Qt.Horizontal)
        self.timeline.setRange(0, 0)
        self.timeline.setEnabled(False)
        timeline_row.addWidget(self.time_label)
        timeline_row.addWidget(self.timeline, 1)
        right_layout.addLayout(timeline_row)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([390, 890])

    def _connect_signals(self) -> None:
        self.open_media_button.clicked.connect(self._open_media)
        self.clear_calibration_button.clicked.connect(self._clear_calibration)
        self.x_tool_button.clicked.connect(lambda: self._set_active_tool("x"))
        self.y_tool_button.clicked.connect(lambda: self._set_active_tool("y"))
        self.cm_tool_button.clicked.connect(lambda: self._set_active_tool("cm"))
        self.reset_zoom_button.clicked.connect(self.preview.reset_zoom)
        self.tau_spin.valueChanged.connect(self._update_calibration_results)
        self.preview.sticks_changed.connect(self._update_calibration_results)
        self.preview.stick_delete_requested.connect(self._confirm_delete_calibration_stick)
        self.timeline.valueChanged.connect(self._timeline_changed)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #f7f8fa;
                color: #111827;
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QGroupBox {
                border: 1px solid #d8dee8;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px 8px 8px 8px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #374151;
                font-weight: 600;
                background: transparent;
            }
            QLabel#TitleLabel {
                font-size: 19px;
                font-weight: 800;
            }
            QLabel#PreviewTitle {
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#MutedLabel {
                color: #64748b;
                font-size: 12px;
            }
            QPushButton {
                border: 1px solid #c9d2df;
                border-radius: 5px;
                padding: 7px 10px;
                background: #ffffff;
            }
            QPushButton:hover {
                background: #edf7f7;
                border-color: #8ccfcf;
            }
            QPushButton#OpenMediaButton {
                background: #e5f3ff;
                border-color: #93c5fd;
                color: #1e3a8a;
                font-weight: 700;
            }
            QPushButton#OpenMediaButton:hover {
                background: #d7ecff;
                border-color: #3b82f6;
            }
            QPushButton#ClearButton {
                background: #fde8e8;
                border-color: #f3a5a5;
                color: #991b1b;
                font-weight: 700;
            }
            QPushButton#ClearButton:hover {
                background: #fbd5d5;
                border-color: #ef4444;
            }
            QPushButton#ResetButton {
                background: #e8f6f8;
                border-color: #8bd6df;
                color: #155e75;
                font-weight: 650;
            }
            QPushButton#ResetButton:hover {
                background: #d8f0f4;
                border-color: #0891b2;
            }
            QFrame#OperationsBar {
                border: 1px solid #cfd7e3;
                border-radius: 6px;
                background: #ffffff;
            }
            QGraphicsView {
                border: 1px solid #cfd7e3;
                border-radius: 6px;
                background: #111827;
            }
            QDoubleSpinBox {
                border: 1px solid #cfd7e3;
                border-radius: 4px;
                background: #ffffff;
                padding: 4px 6px;
            }
            QSlider::groove:horizontal {
                height: 5px;
                border-radius: 2px;
                background: #dbe3ee;
            }
            QSlider::handle:horizontal {
                width: 13px;
                margin: -5px 0;
                border-radius: 6px;
                background: #0891b2;
            }
            """
        )

    def _open_media(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Open calibration image or video",
            str(self._project_root),
            f"Image and video files ({extensions});;All files (*)",
        )
        if not filename:
            return

        path = Path(filename).expanduser().resolve()
        suffix = path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            self._load_image(path)
        elif suffix in VIDEO_EXTENSIONS:
            self._load_video(path)
        else:
            QMessageBox.warning(self, "Unsupported file", "Choose a supported image or video file.")

    def _load_image(self, path: Path) -> None:
        self._release_capture()
        image = QImage(str(path))
        if image.isNull():
            QMessageBox.warning(self, "Could not open image", str(path))
            return

        self.preview.clear_calibration()
        self._current_media = path
        self._duration_ms = 0
        self.timeline.setRange(0, 0)
        self.timeline.setEnabled(False)
        self.time_label.setText("Image")
        self.media_label.setText(str(path))
        self.preview_title.setText(path.name)
        self.preview.set_frame(image)

    def _load_video(self, path: Path) -> None:
        if cv2 is None:
            QMessageBox.critical(self, "OpenCV is missing", "Install the conda environment first: conda env create -f GAIT_ASSEMBLER.yaml")
            return

        self._release_capture()
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            QMessageBox.warning(self, "Could not open video", str(path))
            return

        self.preview.clear_calibration()
        self._capture = capture
        self._current_media = path
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self._duration_ms = int((frame_count / fps) * 1000) if fps > 0 and frame_count > 0 else 0
        self.timeline.setRange(0, max(0, self._duration_ms))
        self.timeline.setSingleStep(100)
        self.timeline.setPageStep(1000)
        self.timeline.setEnabled(self._duration_ms > 0)
        self.media_label.setText(str(path))
        self.preview_title.setText(path.name)
        self._set_timeline_value(0)
        self._load_frame_at(0)

    def _timeline_changed(self, value: int) -> None:
        if self._loading_slider:
            return
        self._load_frame_at(value)

    def _load_frame_at(self, ms: int) -> None:
        if self._capture is None or cv2 is None:
            return

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
        self.time_label.setText(f"{_format_ms(ms)} / {_format_ms(self._duration_ms)}")

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
            "Remove all calibration sticks and centimeter markers from this frame?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self.preview.clear_calibration()

    def _confirm_delete_calibration_stick(self, key: str, label: str) -> None:
        if QMessageBox.question(
            self,
            "Delete calibration stick?",
            f"Delete {label} and all of its centimeter markers?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        self.preview.delete_stick(key)

    def _set_active_tool(self, name: str) -> None:
        self.preview.set_mode(name)

    def _update_calibration_results(self) -> None:
        sticks = self.preview.calibration_sticks() if hasattr(self, "preview") else []
        report = calculate_calibration_report(sticks, self.tau_spin.value() if hasattr(self, "tau_spin") else 2.0)
        self.results_label.setText(_report_to_html(report))

    def _release_capture(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


def _report_to_html(report: CalibrationReport) -> str:
    if not report.view_axis:
        return (
            "<p style='color:#64748b;'>Create an x calibration stick, a y calibration stick, "
            "and add centimeter markers. Stick endpoints already count as CM markers.</p>"
            f"<p><b>Tau:</b> {report.tau_percent:.2f}%</p>"
        )

    parts = [
        f"<p><b>Overall:</b> {_status_text(report.overall_passed)}<br>"
        f"<span style='color:#475569;'>{report.recommendation}</span></p>",
        f"<p><b>Tau:</b> {report.tau_percent:.2f}% &nbsp; "
        f"<b>Axis threshold:</b> {2.0 * report.tau_percent:.2f}%</p>",
        "<p><b>Measured 1 cm segments</b></p>",
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
        return "<span style='color:#15803d; font-weight:700;'>PASS</span>"
    if value is False:
        return "<span style='color:#b91c1c; font-weight:700;'>FAIL</span>"
    return "<span style='color:#64748b; font-weight:700;'>NEEDS DATA</span>"


def _percent(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value:.2f}%"


def _make_tool_button(text: str, color: str) -> QToolButton:
    button = QToolButton()
    button.setText(text)
    button.setIcon(_dot_icon(color))
    button.setIconSize(QSize(12, 12))
    button.setCheckable(True)
    button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    button.setStyleSheet(_tool_button_style(color))
    return button


def _tool_button_style(color: str) -> str:
    return f"""
        QToolButton {{
            background: {_mix_hex(color, "#ffffff", 0.88)};
            border: 1px solid {_mix_hex(color, "#ffffff", 0.50)};
            color: #111827;
            border-radius: 5px;
            padding: 7px 10px;
            font-weight: 700;
        }}
        QToolButton:hover {{
            background: {_mix_hex(color, "#ffffff", 0.78)};
            border-color: {color};
        }}
        QToolButton:checked {{
            background: {_mix_hex(color, "#ffffff", 0.70)};
            border: 2px solid {color};
        }}
        QToolButton:disabled {{
            background: #eef1f5;
            border-color: #d8dee8;
            color: #94a3b8;
        }}
    """


def _mix_hex(color: str, base: str, base_weight: float) -> str:
    foreground = QColor(color)
    background = QColor(base)
    weight = max(0.0, min(1.0, base_weight))
    red = round(foreground.red() * (1.0 - weight) + background.red() * weight)
    green = round(foreground.green() * (1.0 - weight) + background.green() * weight)
    blue = round(foreground.blue() * (1.0 - weight) + background.blue() * weight)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _dot_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(2, 2, 12, 12)
    painter.end()
    return QIcon(pixmap)


def _format_ms(ms: int) -> str:
    total_seconds, milliseconds = divmod(max(0, int(ms)), 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
