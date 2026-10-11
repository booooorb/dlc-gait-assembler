"""Edit regional inversion rectangles through the video canvas coordinate interface."""

from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import NormalizedRect


class VideoInversionControls:
    def __init__(self, canvas):
        self.canvas = canvas

    def invert_regions(self) -> list[NormalizedRect]:
        return list(self.canvas._invert_norms.values())

    def set_invert_regions(self, regions: tuple[NormalizedRect, ...]) -> None:
        self.canvas._region_state.clear_invert_regions()
        for region in regions:
            if not region.is_usable():
                continue
            region_id = self.canvas._next_invert_id
            self.canvas._next_invert_id += 1
            self.canvas._invert_norms[region_id] = region.clamped()
        self.canvas._render()
        self.canvas._emit_regions()

    def invert_region(self) -> NormalizedRect | None:
        regions = self.invert_regions()
        return regions[0] if regions else None

    def set_invert_pixel_edges(self, region_id: int, left: int, top: int, right: int, bottom: int) -> None:
        if self.canvas._image_bounds.isNull():
            return
        self.canvas._invert_norms[region_id] = self.canvas._pixel_edges_to_normalized(left, top, right, bottom)
        self.canvas._next_invert_id = max(self.canvas._next_invert_id, region_id + 1)
        self.canvas._render()
        self.canvas._emit_regions()
