"""Edit crop flip flags and their per-video horizontal/vertical assignments."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSizePolicy

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip


class VideoFlipAssignment:
    """VideoFlipAssignment operates on its explicitly supplied VideoOperationSettingsPanel view."""

    def __init__(self, view):
        self.view = view

    def _apply_crop_flip_horizontal(self, region_id: int | None, enabled: bool) -> None:
        if self.view._building or region_id is None:
            return
        self.view._preview.set_crop_region_flip_horizontal(region_id, enabled)

    def _apply_crop_flip_vertical(self, region_id: int | None, enabled: bool) -> None:
        if self.view._building or region_id is None:
            return
        self.view._preview.set_crop_region_flip_vertical(region_id, enabled)

    def _open_horizontal_video_selector(self, region_id: int | None) -> None:
        if region_id is None:
            return
        snapshot = self.view._preview.region_snapshots()
        region = self._crop_snapshot(snapshot, region_id)
        if region is None:
            return
        selected_paths = self.view._preview.crop_region_horizontal_flip_video_paths(region_id)
        if selected_paths is None:
            self.view._choice_selected_paths = (
                set(self.view._video_paths) if region.get("flip_horizontal", False) else set()
            )
        else:
            self.view._choice_selected_paths = set(selected_paths)
        self.view._choice_apply_to_all_regions = False
        self.view._choosing_horizontal_region_id = region_id
        self._rebuild_horizontal_video_selector()

    def _rebuild_horizontal_video_selector(self) -> None:
        region_id = self.view._choosing_horizontal_region_id
        if region_id is None:
            return
        snapshot = self.view._preview.region_snapshots()
        region = self._crop_snapshot(snapshot, region_id)
        if region is None:
            self.view._choosing_horizontal_region_id = None
            self.view.refresh()
            return
        self.view._building = True
        self.view._keys = [("flip-horizontal-videos", region_id)]
        self.view._controls = {}
        self.view._enhancement_controls = {}
        self.view._clear_layout()
        header = QLabel(f"{region.get('name', 'Region')} - Flip horizontal")
        header.setObjectName("RegionTitle")
        self.view._content_layout.addWidget(header)
        video_list = QListWidget()
        video_list.setObjectName("FlipVideoList")
        video_list.setAlternatingRowColors(True)
        video_list.setUniformItemSizes(True)
        video_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_list.blockSignals(True)
        for path in self.view._video_paths:
            item = QListWidgetItem(Path(path).name)
            item.setToolTip(path)
            item.setData(Qt.UserRole, path)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if path in self.view._choice_selected_paths else Qt.Unchecked)
            video_list.addItem(item)
        if video_list.count() > 0:
            video_list.setCurrentRow(0)
        else:
            self.view._add_placeholder("No uploaded videos.")
        video_list.blockSignals(False)
        video_list.itemChanged.connect(self._on_horizontal_choice_item_changed)
        video_list.currentItemChanged.connect(lambda current, _previous: self._preview_choice_video(current))
        self.view._content_layout.addWidget(video_list, 1)
        apply_to_all_check = QCheckBox("Apply to all regions and new regions")
        apply_to_all_check.setChecked(self.view._choice_apply_to_all_regions)
        set_tooltip(
            apply_to_all_check,
            "Use this horizontal-flip video selection for every existing region and as the default for new regions.",
        )
        apply_to_all_check.toggled.connect(lambda checked: self._set_apply_horizontal_choice_to_all(checked))
        self.view._content_layout.addWidget(apply_to_all_check)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        confirm_button = QPushButton("Confirm")
        confirm_button.setObjectName("PrimaryButton")
        confirm_button.clicked.connect(self._confirm_horizontal_video_choice)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("ResetButton")
        cancel_button.clicked.connect(self._cancel_horizontal_video_choice)
        button_row.addWidget(confirm_button)
        button_row.addWidget(cancel_button)
        self.view._content_layout.addLayout(button_row)
        self.view._building = False
        self._preview_choice_video(video_list.currentItem())

    def _on_horizontal_choice_item_changed(self, item: QListWidgetItem) -> None:
        if self.view._building:
            return
        path = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.view._choice_selected_paths.add(path)
        else:
            self.view._choice_selected_paths.discard(path)

    def _preview_choice_video(self, item: QListWidgetItem | None) -> None:
        if self.view._building or item is None:
            return
        self.view.video_preview_requested.emit(item.data(Qt.UserRole))

    def _confirm_horizontal_video_choice(self) -> None:
        region_id = self.view._choosing_horizontal_region_id
        if region_id is None:
            return
        selected_paths = set(self.view._choice_selected_paths)
        selection = self._selection_paths_for_preview(selected_paths)
        if self.view._choice_apply_to_all_regions:
            self.view._preview.apply_crop_horizontal_flip_selection_to_all_regions(selection, apply_to_new_regions=True)
        else:
            self.view._preview.set_crop_region_horizontal_flip_selection(region_id, selection)
        self._cancel_horizontal_video_choice()

    def _cancel_horizontal_video_choice(self) -> None:
        self.view._choosing_horizontal_region_id = None
        self.view._choice_selected_paths = set()
        self.view._choice_apply_to_all_regions = False
        self.view._keys = []
        self.view.refresh()

    def _set_apply_horizontal_choice_to_all(self, enabled: bool) -> None:
        if self.view._building:
            return
        self.view._choice_apply_to_all_regions = bool(enabled)

    def _selection_paths_for_preview(self, selected_paths: set[str]) -> frozenset[str] | None:
        if not selected_paths:
            return frozenset()
        if selected_paths == set(self.view._video_paths):
            return None
        return frozenset(selected_paths)

    def _crop_snapshot(self, snapshot: dict, region_id: int) -> dict | None:
        for region in snapshot.get("crops", []):
            if region.get("id") == region_id:
                return region
        return None

    def _format_horizontal_video_status(self, edges: dict) -> str:
        if not edges.get("flip_horizontal", False):
            return "Off"
        selected_paths = edges.get("flip_horizontal_video_paths")
        if selected_paths is None:
            return "All videos"
        count = len(selected_paths)
        return f"{count} video" if count == 1 else f"{count} videos"
