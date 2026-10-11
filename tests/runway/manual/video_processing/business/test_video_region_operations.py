from dlc_gait_assembly.runway.manual.video_processing.business.video_region_operations import RegionEditorState


from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import NormalizedRect


def test_region_editor_state_allocates_and_resets_without_qt():
    state = RegionEditorState()
    crop_id = state.allocate_crop_id()
    invert_id = state.allocate_invert_id()
    state.crop_norms[crop_id] = NormalizedRect(0.1, 0.2, 0.3, 0.4)
    state.invert_norms[invert_id] = NormalizedRect(0.2, 0.3, 0.4, 0.5)
    state.clear_crops()
    state.clear_invert_regions()
    assert state.crop_norms == {}
    assert state.invert_norms == {}
    assert state.allocate_crop_id() == 1
    assert state.allocate_invert_id() == 1
