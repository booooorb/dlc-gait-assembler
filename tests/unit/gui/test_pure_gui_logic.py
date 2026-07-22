from dlc_gait_assembly.gui.gait_analysis.pairing import (
    build_view_csv_sets,
    csv_view_from_name,
)
from dlc_gait_assembly.gui.shared.svg import qt_safe_svg_bytes
from dlc_gait_assembly.gui.video_editor.region_state import RegionEditorState
from dlc_gait_assembly.services.domain.regions import NormalizedRect


def test_multiview_pairing_is_filename_driven_and_qt_free(tmp_path):
    paths = [
        tmp_path / "mouse_01_left.csv",
        tmp_path / "mouse_01_right.csv",
        tmp_path / "mouse_01_bottom.csv",
    ]
    assert [csv_view_from_name(path) for path in paths] == ["left", "right", "bottom"]
    view_sets, errors = build_view_csv_sets(paths)
    assert errors == []
    assert len(view_sets) == 1
    assert view_sets[0].name == "mouse_01"


def test_svg_sanitizer_removes_nonfinite_paths_and_broken_uses():
    source = b"""<svg xmlns="http://www.w3.org/2000/svg"><defs><path id="bad"/></defs>
    <path d="M 0 0 L nan 2"/><use href="#bad"/><path d="M 0 0 L 2 2"/></svg>"""
    cleaned = qt_safe_svg_bytes(source)
    assert b"nan" not in cleaned
    assert b"<use" not in cleaned
    assert b"M 0 0 L 2 2" in cleaned


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
