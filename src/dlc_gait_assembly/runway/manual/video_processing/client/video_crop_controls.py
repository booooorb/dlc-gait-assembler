"""Build crop name, pixel-boundary, dimension, deletion, and flip-assignment controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class VideoCropControls:
    def __init__(self, panel):
        self.panel = panel

    def _settings_regions(self, snapshot: dict) -> list[dict]:
        regions = []
        if self.panel._active_tool in {"enhancements", "trim"}:
            return regions
        if self.panel._active_tool == "crop":
            for index, region in enumerate(snapshot.get("crops", []), start=1):
                regions.append(
                    {
                        "kind": "crop",
                        "id": region["id"],
                        "title": f"Region {index}",
                        "name": region["name"],
                        "edges": region,
                    }
                )
            return regions
        return regions

    def _empty_state_text(self) -> str:
        return "No regions."

    def _can_create_region(self, snapshot: dict) -> bool:
        if snapshot["width"] <= 0 or snapshot["height"] <= 0:
            return False
        if self.panel._active_tool in {"enhancements", "trim"}:
            return False
        return self.panel._active_tool == "crop"

    def _update_controls(self, regions: list[dict]) -> None:
        self.panel._building = True
        for region in regions:
            controls = self.panel._controls.get((region["kind"], region["id"]))
            if controls is None:
                continue
            edges = region["edges"]
            controls["dimension"].setText(f"{edges['width']} x {edges['height']} px")
            name_edit = controls.get("name")
            if name_edit is not None and (not name_edit.hasFocus()):
                name_edit.blockSignals(True)
                name_edit.setText(region.get("name", region["title"]))
                name_edit.blockSignals(False)
            horizontal_check = controls.get("flip_horizontal")
            if horizontal_check is not None:
                horizontal_check.blockSignals(True)
                horizontal_check.setChecked(edges.get("flip_horizontal", False))
                horizontal_check.blockSignals(False)
            vertical_check = controls.get("flip_vertical")
            if vertical_check is not None:
                vertical_check.blockSignals(True)
                vertical_check.setChecked(edges.get("flip_vertical", False))
                vertical_check.blockSignals(False)
            video_status = controls.get("flip_horizontal_status")
            if video_status is not None:
                video_status.setText(self.panel.flips._format_horizontal_video_status(edges))
            for field, spin in controls["spins"].items():
                spin.blockSignals(True)
                spin.setValue(edges[field])
                spin.blockSignals(False)
        self.panel._building = False

    def _add_create_region_button(self) -> None:
        text = "New region"
        object_name = "CreateCropRegionButton"
        button = QPushButton(text)
        button.setObjectName(object_name)
        set_tooltip(button, f"Create a default {text.lower()}.")
        button.clicked.connect(lambda: self.panel._preview.create_default_region(self.panel._active_tool))
        self.panel._content_layout.addWidget(button)

    def _add_region_settings(
        self, kind: str, region_id: int | None, title: str, edges: dict, image_width: int, image_height: int
    ) -> None:
        frame = QFrame()
        frame.setObjectName("RegionSettings")
        layout = QGridLayout(frame)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("RegionTitle")
        title_label.setStyleSheet(f"color: {theme.TEXT};")
        dimension_label = QLabel(f"{edges['width']} x {edges['height']} px")
        dimension_label.setObjectName("DimensionLabel")
        delete_button = QPushButton("x")
        delete_button.setObjectName("InlineDeleteButton")
        set_tooltip(delete_button, f"Delete {title}.")
        delete_button.clicked.connect(lambda _checked=False, k=kind, rid=region_id: self._delete_region(k, rid))
        layout.addWidget(title_label, 0, 0, 1, 2)
        layout.addWidget(dimension_label, 0, 2, Qt.AlignRight)
        layout.addWidget(delete_button, 0, 3, Qt.AlignRight)
        row_offset = 1
        name_edit = None
        flip_horizontal_check = None
        flip_horizontal_status = None
        flip_vertical_check = None
        if kind == "crop":
            layout.addWidget(QLabel("Name"), 1, 0)
            name_edit = QLineEdit(edges.get("name", title))
            set_tooltip(name_edit, "Cropped region name used in output filenames when multiple crop regions exist.")
            name_edit.textChanged.connect(lambda text, rid=region_id: self._apply_crop_name(rid, text))
            layout.addWidget(name_edit, 1, 1, 1, 3)
            flip_horizontal_row = QWidget()
            flip_horizontal_layout = QHBoxLayout(flip_horizontal_row)
            flip_horizontal_layout.setContentsMargins(0, 0, 0, 0)
            flip_horizontal_layout.setSpacing(4)
            flip_horizontal_check = QCheckBox("Flip horizontal")
            flip_horizontal_check.setChecked(edges.get("flip_horizontal", False))
            set_tooltip(flip_horizontal_check, "Flip this region horizontally during export.")
            flip_horizontal_check.toggled.connect(
                lambda checked, rid=region_id: self.panel.flips._apply_crop_flip_horizontal(rid, checked)
            )
            choose_button = QPushButton("Videos")
            choose_button.setObjectName("ChooseVideosButton")
            choose_button.setEnabled(bool(self.panel._video_paths))
            choose_button.setMinimumWidth(62)
            choose_button.setMaximumWidth(76)
            set_tooltip(choose_button, "Choose uploaded videos that should use horizontal flip for this region.")
            choose_button.clicked.connect(
                lambda _checked=False, rid=region_id: self.panel.flips._open_horizontal_video_selector(rid)
            )
            flip_horizontal_status = QLabel(self.panel.flips._format_horizontal_video_status(edges))
            flip_horizontal_status.setObjectName("DimensionLabel")
            flip_horizontal_layout.addWidget(flip_horizontal_check)
            flip_horizontal_layout.addSpacing(10)
            flip_horizontal_layout.addWidget(choose_button)
            flip_horizontal_layout.addSpacing(6)
            flip_horizontal_layout.addWidget(flip_horizontal_status)
            flip_horizontal_layout.addStretch(1)
            layout.addWidget(flip_horizontal_row, 2, 0, 1, 4)
            flip_vertical_check = QCheckBox("Flip vertical")
            flip_vertical_check.setChecked(edges.get("flip_vertical", False))
            set_tooltip(flip_vertical_check, "Flip this region vertically during export.")
            flip_vertical_check.toggled.connect(
                lambda checked, rid=region_id: self.panel.flips._apply_crop_flip_vertical(rid, checked)
            )
            layout.addWidget(flip_vertical_check, 3, 0, 1, 4)
            row_offset = 4
        spins: dict[str, QSpinBox] = {}
        fields = [
            ("left", "Left", image_width),
            ("top", "Top", image_height),
            ("right", "Right", image_width),
            ("bottom", "Bottom", image_height),
        ]
        positions = [(row_offset, 0), (row_offset, 2), (row_offset + 1, 0), (row_offset + 1, 2)]
        for (field, label, maximum), (row, column) in zip(fields, positions, strict=True):
            layout.addWidget(QLabel(label), row, column)
            spin = QSpinBox()
            spin.setRange(0, maximum)
            spin.setKeyboardTracking(False)
            spin.setValue(edges[field])
            spin.setMinimumWidth(48)
            set_tooltip(spin, f"{label} edge of this {kind} region, in pixels.")
            spins[field] = spin
            layout.addWidget(spin, row, column + 1)
        for spin in spins.values():
            spin.valueChanged.connect(
                lambda _value, k=kind, rid=region_id, controls=spins: self._apply_region_edges(k, rid, controls)
            )
        self.panel._controls[kind, region_id] = {
            "spins": spins,
            "dimension": dimension_label,
            "name": name_edit,
            "flip_horizontal": flip_horizontal_check,
            "flip_horizontal_status": flip_horizontal_status,
            "flip_vertical": flip_vertical_check,
        }
        self.panel._content_layout.addWidget(frame)

    def _apply_region_edges(self, kind: str, region_id: int | None, controls: dict[str, QSpinBox]) -> None:
        if self.panel._building:
            return
        snapshot = self.panel._preview.region_snapshots()
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
            self.panel._preview.set_crop_pixel_edges(left, top, right, bottom, region_id)
        elif region_id is not None:
            self.panel._preview.set_invert_pixel_edges(region_id, left, top, right, bottom)

    def _delete_region(self, kind: str, region_id: int | None) -> None:
        if kind == "crop" and region_id is not None:
            self.panel._preview.delete_region(f"crop:{region_id}")
        elif region_id is not None:
            self.panel._preview.delete_region(f"invert:{region_id}")

    def _apply_crop_name(self, region_id: int | None, name: str) -> None:
        if self.panel._building or region_id is None:
            return
        self.panel._preview.set_crop_region_name(region_id, name)
