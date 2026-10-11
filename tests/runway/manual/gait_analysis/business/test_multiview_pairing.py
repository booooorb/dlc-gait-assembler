import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import detect_bodypart_mapping
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import (
    build_view_csv_sets,
    csv_view_from_name,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import auto_bodypart_label
from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_view_pairing_dialog import (
    CsvPairingDialog,
    combo_path,
)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def test_matches_different_dlc_models_and_processing_suffixes(tmp_path):
    paths = [
        tmp_path / "mouse_01_leftDLC_resnet50_sideA_filtered_knee_corrected.csv",
        tmp_path / "mouse_01_rightDLC_resnet101_sideB_filtered.csv",
        tmp_path / "mouse_01_bottomDLC_resnet50_paws.csv",
    ]
    groups, errors = build_view_csv_sets(paths)
    assert errors == []
    assert len(groups) == 1
    assert groups[0].name == "mouse_01"
    assert groups[0].left_csv == paths[0]


def test_matches_view_folders_and_compound_view_names(tmp_path):
    paths = [tmp_path / view / "mouse_01.csv" for view in ("left", "right", "bottom")]
    groups, errors = build_view_csv_sets(paths)
    assert not errors and len(groups) == 1
    paths = [tmp_path / f"mouse_01_{view}View.csv" for view in ("left", "right", "bottom")]
    groups, errors = build_view_csv_sets(paths)
    assert not errors and len(groups) == 1


def test_ambiguous_views_and_duplicate_candidates_are_not_silently_selected(tmp_path):
    assert csv_view_from_name(tmp_path / "mouse_left_right.csv") is None
    paths = [tmp_path / f"mouse_{view}.csv" for view in ("left", "right", "bottom")]
    paths.append(tmp_path / "mouse_left_filtered.csv")
    groups, errors = build_view_csv_sets(paths)
    assert groups == []
    assert any("Duplicate left" in error for error in errors)


def test_same_names_in_different_sessions_do_not_overwrite_outputs(tmp_path):
    paths = [
        tmp_path / session / f"mouse_{view}.csv" for session in ("day1", "day2") for view in ("left", "right", "bottom")
    ]
    groups, errors = build_view_csv_sets(paths)
    assert not errors
    assert {group.name for group in groups} == {"day1_mouse", "day2_mouse"}


def test_pairing_table_shows_partial_groups_and_does_not_guess_unknown_views(app, tmp_path):
    paths = [tmp_path / name for name in ("mouse_left.csv", "mouse_bottom.csv", "unknown.csv")]
    dialog = CsvPairingDialog(paths, [])
    assert len(dialog._rows) == 1
    row = dialog._rows[0]
    assert combo_path(row["left"]) == paths[0]
    assert combo_path(row["right"]) is None
    assert row["status"].text() == "Missing right"
    assert not dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
    row["right"].setCurrentIndex(row["right"].findData(str(paths[2])))
    assert dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
    assert dialog._collect_pairings()[0].right_csv == paths[2]
    dialog.close()


def test_auto_fill_preserves_manual_assignments_metadata_and_row_count(app, tmp_path):
    paths = [tmp_path / f"mouse_{view}.csv" for view in ("left", "right", "bottom")]
    metadata = StrokeStudyMetadata(animal_id="mouse-01", group="sham")
    initial = AlmaViewCsvSet("my_session", *paths, metadata=metadata)
    dialog = CsvPairingDialog(paths, [initial])
    dialog._use_filename_pairs()
    dialog._use_filename_pairs()
    assert len(dialog._rows) == 1
    result = dialog._collect_pairings()[0]
    assert result.name == "my_session"
    assert result.metadata.animal_id == "mouse-01"
    assert result.metadata.group == "sham"
    assert result.left_csv == paths[0]
    dialog.close()


def test_duplicate_file_assignment_is_visible_and_unsaved_search_text_is_not_a_path(app, tmp_path):
    paths = [tmp_path / f"mouse_{view}.csv" for view in ("left", "right", "bottom")]
    dialog = CsvPairingDialog(paths, [])
    row = dialog._rows[0]
    row["right"].setCurrentIndex(row["right"].findData(str(paths[0])))
    assert "CSV used more than once" in row["status"].text()
    assert not dialog.buttons.button(QDialogButtonBox.Save).isEnabled()
    row["right"].setEditText("some typed query")
    assert combo_path(row["right"]) is None
    dialog.close()


@pytest.mark.parametrize("label", ["back_toe", "back-toe", "Back Toe"])
def test_back_toe_alias_is_shared_by_ui_and_analysis(label):
    assert auto_bodypart_label([label], "toe") == label
    mapping, _ = detect_bodypart_mapping([label, "mtp", "ankle", "knee", "hip", "iliac_crest"])
    assert mapping[label] == "toe"
