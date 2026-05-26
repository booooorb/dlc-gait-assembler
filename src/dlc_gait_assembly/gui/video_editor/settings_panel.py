from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QGroupBox, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget

from dlc_gait_assembly.gui.video_editor.preview import RegionPreviewView


class OperationSettingsPanel(QGroupBox):
    def __init__(self, preview: RegionPreviewView, parent=None):
        super().__init__("Operations Settings", parent)
        self._preview = preview
        self._building = False
        self._controls: dict[tuple[str, int | None], dict] = {}
        self._keys: list[tuple[str, int | None]] = []
        self._image_size = (0, 0)
        self._active_tool = "crop"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll, 1)

        self._preview.regions_changed.connect(lambda *_: self.refresh())
        self.refresh()

    def set_active_tool(self, tool: str) -> None:
        if tool not in {"crop", "invert"} or tool == self._active_tool:
            return

        self._active_tool = tool
        self._keys = []
        self.refresh()

    def refresh(self) -> None:
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

        self._content_layout.addStretch(1)
        self._building = False

    def _settings_regions(self, snapshot: dict) -> list[dict]:
        regions = []
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
        layout.setContentsMargins(8, 7, 8, 8)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("RegionTitle")
        title_label.setStyleSheet("color: #c026d3;" if kind == "invert" else "color: #334155;")
        dimension_label = QLabel(f'{edges["width"]} x {edges["height"]} px')
        dimension_label.setObjectName("DimensionLabel")
        layout.addWidget(title_label, 0, 0, 1, 2)
        layout.addWidget(dimension_label, 0, 2, 1, 2, Qt.AlignRight)

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
            spin.setMinimumWidth(72)
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
