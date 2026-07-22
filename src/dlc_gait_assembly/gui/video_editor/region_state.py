from __future__ import annotations

from dataclasses import dataclass, field

from dlc_gait_assembly.services.domain.regions import NormalizedRect


@dataclass
class RegionEditorState:
    """Mutable, Qt-independent region configuration for the video preview."""

    crop_norms: dict[int, NormalizedRect] = field(default_factory=dict)
    crop_names: dict[int, str] = field(default_factory=dict)
    crop_flip_horizontal: dict[int, bool] = field(default_factory=dict)
    crop_flip_vertical: dict[int, bool] = field(default_factory=dict)
    crop_flip_horizontal_video_paths: dict[int, frozenset[str] | None] = field(default_factory=dict)
    default_crop_flip_horizontal: bool = False
    default_crop_flip_horizontal_video_paths: frozenset[str] | None = None
    next_crop_id: int = 1
    invert_norms: dict[int, NormalizedRect] = field(default_factory=dict)
    next_invert_id: int = 1
    current_video_path: str | None = None

    def allocate_crop_id(self) -> int:
        region_id = self.next_crop_id
        self.next_crop_id += 1
        return region_id

    def allocate_invert_id(self) -> int:
        region_id = self.next_invert_id
        self.next_invert_id += 1
        return region_id

    def clear_crops(self) -> None:
        self.crop_norms.clear()
        self.crop_names.clear()
        self.crop_flip_horizontal.clear()
        self.crop_flip_vertical.clear()
        self.crop_flip_horizontal_video_paths.clear()
        self.next_crop_id = 1

    def clear_invert_regions(self) -> None:
        self.invert_norms.clear()
        self.next_invert_id = 1
