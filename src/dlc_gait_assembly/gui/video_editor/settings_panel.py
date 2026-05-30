from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QDoubleSpinBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.domain.enhancements import EnhancementSettings
from dlc_gait_assembly.domain.trimming import TrimRange
from dlc_gait_assembly.gui.video_editor.preview import RegionPreviewView


_ENHANCEMENT_SLIDERS = [
    ("sharpening", "Sharpening", 0, 250, 100.0),
    ("cas", "CAS", 0, 100, 100.0),
    ("brightness", "Brightness", -100, 100, 100.0),
    ("contrast", "Contrast", 25, 300, 100.0),
    ("exposure", "Exposure", -300, 300, 100.0),
    ("black_level", "Black Level", -100, 100, 100.0),
    ("tone_scale", "Scaling/Tone", 50, 150, 100.0),
    ("input_black", "Levels Input Black", 0, 100, 100.0),
    ("input_white", "Levels Input White", 0, 100, 100.0),
    ("output_black", "Levels Output Black", 0, 100, 100.0),
    ("output_white", "Levels Output White", 0, 100, 100.0),
]


class OperationSettingsPanel(QGroupBox):
    trim_active_range_changed = Signal(int)
    trim_range_changed = Signal(int, int, int)
    trim_range_added = Signal()
    trim_range_deleted = Signal(int)
    trim_ranges_reset = Signal()

    def __init__(self, preview: RegionPreviewView, parent=None):
        super().__init__("Operations Settings", parent)
        self._preview = preview
        self._building = False
        self._controls: dict[tuple[str, int | None], dict] = {}
        self._enhancement_controls: dict[str, dict] = {}
        self._keys: list[tuple[str, int | None]] = []
        self._image_size = (0, 0)
        self._active_tool = "crop"
        self._trim_video_name: str | None = None
        self._trim_duration_ms = 0
        self._trim_ranges: list[TrimRange] = []
        self._active_trim_index = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 7, 6, 6)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("OperationSettingsScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._content.setObjectName("OperationSettingsContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        self._preview.regions_changed.connect(lambda *_: self.refresh())
        self.refresh()

    def set_active_tool(self, tool: str) -> None:
        if tool not in {"crop", "invert", "enhancements", "trim"} or tool == self._active_tool:
            return

        self._active_tool = tool
        self._keys = []
        self.refresh()

    def set_trim_context(
        self,
        video_name: str | None,
        duration_ms: int,
        ranges: list[TrimRange],
        active_index: int = 0,
    ) -> None:
        self._trim_video_name = video_name
        self._trim_duration_ms = max(0, int(duration_ms))
        self._trim_ranges = list(ranges)
        self._active_trim_index = active_index
        if self._active_tool == "trim":
            self._rebuild_trim_settings()

    def refresh(self) -> None:
        if self._active_tool == "enhancements":
            self._rebuild_enhancement_settings()
            return
        if self._active_tool == "trim":
            self._rebuild_trim_settings()
            return

        snapshot = self._preview.region_snapshots()
        image_size = (snapshot["width"], snapshot["height"])
        regions = self._settings_regions(snapshot)
        keys = [(region["kind"], region["id"]) for region in regions]

        if keys == self._keys and image_size == self._image_size and keys:
            self._update_controls(regions)
            return

        self._building = True
        self._keys = keys
        self._image_size = image_size
        self._controls = {}
        self._enhancement_controls = {}
        self._clear_layout()

        if snapshot["width"] <= 0 or snapshot["height"] <= 0:
            self._add_placeholder("No preview loaded.")
        elif not regions:
            self._add_placeholder(self._empty_state_text())
        else:
            for region in regions:
                self._add_region_settings(
                    region["kind"],
                    region["id"],
                    region["title"],
                    region["edges"],
                    snapshot["width"],
                    snapshot["height"],
                )

        if self._can_create_region(snapshot):
            self._add_create_region_button()

        self._content_layout.addStretch(1)
        self._building = False

    def _settings_regions(self, snapshot: dict) -> list[dict]:
        regions = []
        if self._active_tool in {"enhancements", "trim"}:
            return regions

        if self._active_tool == "crop":
            if snapshot["crop"] is not None:
                regions.append({"kind": "crop", "id": None, "title": "Crop", "edges": snapshot["crop"]})
            return regions

        for index, region in enumerate(snapshot["inverts"], start=1):
            regions.append(
                {
                    "kind": "invert",
                    "id": region["id"],
                    "title": f"Upside-Down {index}",
                    "edges": region,
                }
            )

        return regions

    def _empty_state_text(self) -> str:
        if self._active_tool == "crop":
            return "No crop region."
        return "No upside-down regions."

    def _rebuild_enhancement_settings(self) -> None:
        self._building = True
        self._keys = [("enhancements", None)]
        self._controls = {}
        self._enhancement_controls = {}
        self._clear_layout()

        settings = self._preview.enhancement_settings()
        for field, title, minimum, maximum, scale in _ENHANCEMENT_SLIDERS:
            self._add_enhancement_slider(field, title, minimum, maximum, scale, getattr(settings, field))

        reset_button = QPushButton("Reset Enhancements")
        reset_button.setObjectName("ResetButton")
        reset_button.clicked.connect(self._reset_enhancements)
        self._content_layout.addWidget(reset_button)
        zoom_reset_button = QPushButton("Reset Preview Zoom")
        zoom_reset_button.setObjectName("ResetButton")
        zoom_reset_button.clicked.connect(lambda _checked=False: self._preview.reset_enhancement_zoom())
        self._content_layout.addWidget(zoom_reset_button)
        self._content_layout.addStretch(1)
        self._building = False

    def _add_enhancement_slider(
        self,
        field: str,
        title: str,
        minimum: int,
        maximum: int,
        scale: float,
        current_value: float,
    ) -> None:
        frame = QFrame()
        frame.setObjectName("EnhancementSettings")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 3, 5, 4)
        layout.setSpacing(2)

        label_row = QHBoxLayout()
        label_row.setSpacing(4)
        label = QLabel(title)
        label.setObjectName("RegionTitle")
        label_row.addWidget(label)
        label_row.addStretch(1)
        spin = QDoubleSpinBox()
        spin.setRange(minimum / scale, maximum / scale)
        spin.setDecimals(2)
        spin.setSingleStep(1.0 / scale)
        spin.setKeyboardTracking(False)
        spin.setValue(current_value)
        spin.setMaximumWidth(62)
        spin.valueChanged.connect(lambda _value: self._apply_enhancement_settings(source="spin"))
        label_row.addWidget(spin)
        reset_button = QPushButton("R")
        reset_button.setObjectName("TinyResetButton")
        reset_button.setToolTip(f"Reset {title}")
        reset_button.clicked.connect(lambda _checked=False, name=field: self._reset_enhancement_field(name))
        label_row.addWidget(reset_button)
        layout.addLayout(label_row)

        slider = QSlider(Qt.Horizontal)
        slider.setObjectName("EnhancementSlider")
        slider.setRange(minimum, maximum)
        slider.setValue(round(current_value * scale))
        slider.valueChanged.connect(lambda _value: self._apply_enhancement_settings(source="slider"))
        layout.addWidget(slider)

        self._enhancement_controls[field] = {"slider": slider, "spin": spin, "scale": scale}
        self._content_layout.addWidget(frame)

    def _apply_enhancement_settings(self, source: str = "slider") -> None:
        if self._building:
            return

        self._building = True
        values = {}
        for field, controls in self._enhancement_controls.items():
            slider = controls["slider"]
            spin = controls["spin"]
            scale = controls["scale"]
            if source == "spin":
                value = spin.value()
                slider.blockSignals(True)
                slider.setValue(round(value * scale))
                slider.blockSignals(False)
            else:
                value = slider.value() / scale
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
            values[field] = value
        self._building = False

        self._preview.set_enhancements(EnhancementSettings(**values))

    def _reset_enhancements(self) -> None:
        self._preview.reset_enhancements()
        self._rebuild_enhancement_settings()

    def _reset_enhancement_field(self, field: str) -> None:
        controls = self._enhancement_controls.get(field)
        if controls is None:
            return

        default_value = getattr(EnhancementSettings(), field)
        controls["slider"].setValue(round(default_value * controls["scale"]))
        controls["spin"].setValue(default_value)

    def _rebuild_trim_settings(self) -> None:
        self._building = True
        self._keys = [("trim", None)]
        self._controls = {}
        self._enhancement_controls = {}
        self._clear_layout()

        if self._trim_video_name is None or self._trim_duration_ms <= 0:
            self._add_placeholder("No video selected.")
            self._content_layout.addStretch(1)
            self._building = False
            return

        header = QLabel(self._trim_video_name)
        header.setObjectName("RegionTitle")
        self._content_layout.addWidget(header)

        ranges = self._trim_ranges or [TrimRange(0, self._trim_duration_ms)]
        for index, trim_range in enumerate(ranges):
            self._add_trim_range_settings(index, trim_range, index == self._active_trim_index)

        add_button = QPushButton("Add Trim Range")
        add_button.setObjectName("CreateTrimRangeButton")
        add_button.clicked.connect(lambda _checked=False: self.trim_range_added.emit())
        self._content_layout.addWidget(add_button)

        reset_button = QPushButton("Reset Video Trim")
        reset_button.setObjectName("ResetButton")
        reset_button.clicked.connect(lambda _checked=False: self.trim_ranges_reset.emit())
        self._content_layout.addWidget(reset_button)

        self._content_layout.addStretch(1)
        self._building = False

    def _add_trim_range_settings(self, index: int, trim_range: TrimRange, active: bool) -> None:
        frame = QFrame()
        frame.setObjectName("RegionSettings")
        layout = QGridLayout(frame)
        layout.setContentsMargins(5, 4, 5, 5)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(2)
        layout.setColumnStretch(1, 1)

        title = QLabel(f"Range {index + 1}")
        title.setObjectName("RegionTitle")
        title.setStyleSheet("color: #f97316;" if active else "")
        duration = QLabel(f"{_format_ms(trim_range.start_ms)} - {_format_ms(trim_range.end_ms)}")
        duration.setObjectName("DimensionLabel")
        duration.setWordWrap(True)
        layout.addWidget(title, 0, 0)
        layout.addWidget(duration, 0, 1, Qt.AlignRight)

        start_spin = self._make_trim_spinbox(trim_range.start_ms)
        end_spin = self._make_trim_spinbox(trim_range.end_ms)
        start_spin.valueChanged.connect(lambda _value, idx=index: self._apply_trim_spins(idx, start_spin, end_spin))
        end_spin.valueChanged.connect(lambda _value, idx=index: self._apply_trim_spins(idx, start_spin, end_spin))
        start_spin.editingFinished.connect(lambda idx=index: self.trim_active_range_changed.emit(idx))
        end_spin.editingFinished.connect(lambda idx=index: self.trim_active_range_changed.emit(idx))

        layout.addWidget(QLabel("Start"), 1, 0)
        layout.addWidget(start_spin, 1, 1)
        layout.addWidget(QLabel("End"), 2, 0)
        layout.addWidget(end_spin, 2, 1)

        delete_button = QPushButton("Delete")
        delete_button.setObjectName("DeleteButton")
        delete_button.clicked.connect(lambda _checked=False, idx=index: self.trim_range_deleted.emit(idx))
        layout.addWidget(delete_button, 3, 0, 1, 2)

        self._content_layout.addWidget(frame)

    def _make_trim_spinbox(self, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, self._trim_duration_ms)
        spin.setKeyboardTracking(False)
        spin.setValue(value)
        spin.setMaximumWidth(78)
        return spin

    def _apply_trim_spins(self, index: int, start_spin: QSpinBox, end_spin: QSpinBox) -> None:
        if self._building:
            return

        start = min(start_spin.value(), max(0, end_spin.value() - 1))
        end = max(end_spin.value(), start + 1)
        end = min(end, self._trim_duration_ms)
        self.trim_range_changed.emit(index, start, end)

    def _can_create_region(self, snapshot: dict) -> bool:
        if snapshot["width"] <= 0 or snapshot["height"] <= 0:
            return False
        if self._active_tool == "enhancements":
            return False
        if self._active_tool == "crop":
            return snapshot["crop"] is None
        return True

    def _update_controls(self, regions: list[dict]) -> None:
        self._building = True
        for region in regions:
            controls = self._controls.get((region["kind"], region["id"]))
            if controls is None:
                continue

            edges = region["edges"]
            controls["dimension"].setText(f'{edges["width"]} x {edges["height"]} px')
            for field, spin in controls["spins"].items():
                spin.blockSignals(True)
                spin.setValue(edges[field])
                spin.blockSignals(False)
        self._building = False

    def _clear_layout(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_placeholder(self, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("SettingsPlaceholder")
        label.setWordWrap(True)
        self._content_layout.addWidget(label)

    def _add_create_region_button(self) -> None:
        if self._active_tool == "crop":
            text = "New Crop Region"
            object_name = "CreateCropRegionButton"
        else:
            text = "New Upside-Down Region"
            object_name = "CreateInvertRegionButton"

        button = QPushButton(text)
        button.setObjectName(object_name)
        button.clicked.connect(lambda: self._preview.create_default_region(self._active_tool))
        self._content_layout.addWidget(button)

    def _add_region_settings(
        self,
        kind: str,
        region_id: int | None,
        title: str,
        edges: dict,
        image_width: int,
        image_height: int,
    ) -> None:
        frame = QFrame()
        frame.setObjectName("RegionSettings")
        layout = QGridLayout(frame)
        layout.setContentsMargins(5, 4, 5, 5)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("RegionTitle")
        title_label.setStyleSheet("color: #c026d3;" if kind == "invert" else "color: #334155;")
        dimension_label = QLabel(f'{edges["width"]} x {edges["height"]} px')
        dimension_label.setObjectName("DimensionLabel")
        delete_button = QPushButton("x")
        delete_button.setObjectName("InlineDeleteButton")
        delete_button.setToolTip(f"Delete {title}")
        delete_button.clicked.connect(lambda _checked=False, k=kind, rid=region_id: self._delete_region(k, rid))
        layout.addWidget(title_label, 0, 0, 1, 2)
        layout.addWidget(dimension_label, 0, 2, Qt.AlignRight)
        layout.addWidget(delete_button, 0, 3, Qt.AlignRight)

        spins: dict[str, QSpinBox] = {}
        fields = [
            ("left", "Left", image_width),
            ("top", "Top", image_height),
            ("right", "Right", image_width),
            ("bottom", "Bottom", image_height),
        ]
        positions = [(1, 0), (1, 2), (2, 0), (2, 2)]

        for (field, label, maximum), (row, column) in zip(fields, positions):
            layout.addWidget(QLabel(label), row, column)
            spin = QSpinBox()
            spin.setRange(0, maximum)
            spin.setKeyboardTracking(False)
            spin.setValue(edges[field])
            spin.setMinimumWidth(48)
            spins[field] = spin
            layout.addWidget(spin, row, column + 1)

        for spin in spins.values():
            spin.valueChanged.connect(
                lambda _value, k=kind, rid=region_id, controls=spins: self._apply_region_edges(k, rid, controls)
            )

        self._controls[(kind, region_id)] = {"spins": spins, "dimension": dimension_label}
        self._content_layout.addWidget(frame)

    def _apply_region_edges(self, kind: str, region_id: int | None, controls: dict[str, QSpinBox]) -> None:
        if self._building:
            return

        snapshot = self._preview.region_snapshots()
        image_width = snapshot["width"]
        image_height = snapshot["height"]
        if image_width <= 0 or image_height <= 0:
            return

        left = min(controls["left"].value(), image_width - 2)
        top = min(controls["top"].value(), image_height - 2)
        right = max(controls["right"].value(), left + 2)
        bottom = max(controls["bottom"].value(), top + 2)
        right = min(right, image_width)
        bottom = min(bottom, image_height)

        if kind == "crop":
            self._preview.set_crop_pixel_edges(left, top, right, bottom)
        elif region_id is not None:
            self._preview.set_invert_pixel_edges(region_id, left, top, right, bottom)

    def _delete_region(self, kind: str, region_id: int | None) -> None:
        if kind == "crop":
            self._preview.delete_region("crop")
        elif region_id is not None:
            self._preview.delete_region(f"invert:{region_id}")


def _format_ms(ms: int) -> str:
    total_seconds, milliseconds = divmod(max(0, int(ms)), 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
