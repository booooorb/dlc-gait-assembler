"""Build enhancement sliders, numeric controls, and reset actions for the selected operation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class VideoEnhancementControls:
    """VideoEnhancementControls operates on its explicitly supplied VideoOperationSettingsPanel view."""

    def __init__(self, view):
        self.view = view

    def _rebuild_enhancement_settings(self) -> None:
        self.view._building = True
        self.view._keys = [("enhancements", None)]
        self.view._controls = {}
        self.view._enhancement_controls = {}
        self.view._clear_layout()
        settings = self.view._preview.enhancement_settings()
        for field, title, minimum, maximum, scale in ENHANCEMENT_SLIDERS:
            self._add_enhancement_slider(field, title, minimum, maximum, scale, getattr(settings, field))
        reset_button = QPushButton("Reset enhancements")
        reset_button.setObjectName("ResetButton")
        set_tooltip(reset_button, "Restore all enhancement settings to their defaults.")
        reset_button.clicked.connect(self._reset_enhancements)
        self.view._content_layout.addWidget(reset_button)
        zoom_reset_button = QPushButton("Reset preview zoom")
        zoom_reset_button.setObjectName("ResetButton")
        set_tooltip(zoom_reset_button, "Return the enhancement preview to fit-to-window zoom.")
        zoom_reset_button.clicked.connect(lambda _checked=False: self.view._preview.reset_enhancement_zoom())
        self.view._content_layout.addWidget(zoom_reset_button)
        self.view._content_layout.addStretch(1)
        self.view._building = False

    def _add_enhancement_slider(
        self, field: str, title: str, minimum: int, maximum: int, scale: float, current_value: float
    ) -> None:
        frame = QFrame()
        frame.setObjectName("EnhancementSettings")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)
        label_row = QHBoxLayout()
        label_row.setSpacing(8)
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
        set_tooltip(spin, f"Set {title.lower()} numerically.")
        spin.valueChanged.connect(lambda _value: self._apply_enhancement_settings(source="spin"))
        label_row.addWidget(spin)
        reset_button = QPushButton("R")
        reset_button.setObjectName("TinyResetButton")
        set_tooltip(reset_button, f"Reset {title}.")
        reset_button.clicked.connect(lambda _checked=False, name=field: self._reset_enhancement_field(name))
        label_row.addWidget(reset_button)
        layout.addLayout(label_row)
        slider = QSlider(Qt.Horizontal)
        slider.setObjectName("EnhancementSlider")
        slider.setRange(minimum, maximum)
        slider.setValue(round(current_value * scale))
        set_tooltip(slider, f"Adjust {title.lower()}.")
        slider.valueChanged.connect(lambda _value: self._apply_enhancement_settings(source="slider"))
        layout.addWidget(slider)
        self.view._enhancement_controls[field] = {"slider": slider, "spin": spin, "scale": scale}
        self.view._content_layout.addWidget(frame)

    def _apply_enhancement_settings(self, source: str = "slider") -> None:
        if self.view._building:
            return
        self.view._building = True
        values = {}
        for field, controls in self.view._enhancement_controls.items():
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
        self.view._building = False
        self.view._preview.set_enhancements(EnhancementSettings(**values))

    def _reset_enhancements(self) -> None:
        self.view._preview.reset_enhancements()
        self._rebuild_enhancement_settings()

    def _reset_enhancement_field(self, field: str) -> None:
        controls = self.view._enhancement_controls.get(field)
        if controls is None:
            return
        default_value = getattr(EnhancementSettings(), field)
        controls["slider"].setValue(round(default_value * controls["scale"]))
        controls["spin"].setValue(default_value)


ENHANCEMENT_SLIDERS = [
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
