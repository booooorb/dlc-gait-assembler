from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import build_view_csv_sets


from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import csv_view_from_name


def test_multiview_pairing_is_filename_driven_and_qt_free(tmp_path):
    paths = [tmp_path / "mouse_01_left.csv", tmp_path / "mouse_01_right.csv", tmp_path / "mouse_01_bottom.csv"]
    assert [csv_view_from_name(path) for path in paths] == ["left", "right", "bottom"]
    (view_sets, errors) = build_view_csv_sets(paths)
    assert errors == []
    assert len(view_sets) == 1
    assert view_sets[0].name == "mouse_01"
