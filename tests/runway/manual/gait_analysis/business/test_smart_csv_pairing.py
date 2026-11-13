"""Exercise ranked CSV matching against identity collisions and realistic naming variations."""

from pathlib import Path

import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_input_pairing import (
    build_view_csv_sets,
    build_view_pair_rows,
    csv_view_evidence,
    csv_view_from_bodyparts,
    csv_view_from_name,
    rank_view_candidates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_recording_similarity import recording_name_similarity


@pytest.mark.parametrize("labels, expected", [
    (["L_hip", "L_ankle", "L_knee"], "left"),
    (["hip_right", "ankle_right", "knee_right"], "right"),
    (["left_forelimb_wrist", "left_forelimb_elbow"], "left"),
    (["r-front-toe-tip", "r-wrist", "r-elbow"], "right"),
    (["hind_left_toe", "hind_left_knee"], "left"),
    (["HL_paw", "HR_paw", "FL_paw", "FR_paw"], "bottom"),
    (["back-left", "back-right", "front-left", "front-right"], "bottom"),
    (["left_hind_paw", "right_hind_paw"], "bottom"),
    (["FL", "FR", "HL", "HR"], "bottom"),
    (["hip", "ankle", "knee"], None),
    (["left_hip", "right_hip", "left_knee", "right_knee"], None),
    (["back-left", "back-right", "left_hip", "left_knee"], None),
])
def test_camera_detection_uses_explicit_anatomy(labels, expected):
    assert csv_view_from_bodyparts(labels) == expected


@pytest.mark.parametrize("name, expected", [
    ("M1LeftCam.csv", "left"), ("M1_R.csv", "right"), ("mouse1bottom.csv", "bottom"),
    ("MOUSE1_LEFTVIEW.csv", "left"), ("M1_ventral.csv", "bottom"),
    ("M1DLC_Resnet50_LEFT(MAIN)Jun30shuffle1_snapshot_best-80.csv", "left"),
    ("M1_rightDLC_left_model.csv", "right"), ("M1_left_right.csv", None),
])
def test_camera_names_include_abbreviations_and_model_fallback(name, expected):
    assert csv_view_from_name(Path(name)) == expected


def test_smart_grouping_combines_label_and_filename_evidence(tmp_path):
    paths = [tmp_path / "Mouse01_trial01_Left.csv", tmp_path / "M1_trial1_RIGHT_processed.csv",
             tmp_path / "trial1_mouse1_export.csv"]
    groups, errors = build_view_csv_sets(paths, {str(paths[2]): ("back left", "back right")})
    assert not errors and len(groups) == 1
    assert (groups[0].left_csv, groups[0].right_csv, groups[0].bottom_csv) == tuple(paths)


def test_similar_names_pair_when_one_view_has_extra_descriptive_text(tmp_path):
    paths = [tmp_path / "M3_trial2_left.csv", tmp_path / "M3_trial2_right.csv",
             tmp_path / "M3_trial2_runway_bottom.csv"]
    groups, errors = build_view_csv_sets(paths)
    assert not errors and len(groups) == 1


def test_nested_export_folders_and_camera_ids_preserve_the_session(tmp_path):
    paths = [tmp_path / view / "csv" / "M1.csv" for view in ("Left Camera", "Right View", "underside")]
    groups, errors = build_view_csv_sets(paths)
    assert not errors and len(groups) == 1
    assert csv_view_evidence(tmp_path / "Camera_B" / "M1.csv", ["R_hip", "R_knee"]) == ("right", "")


def test_camera_identifiers_do_not_conflict_with_view_abbreviations_or_animal_ids(tmp_path):
    paths = [tmp_path / f"M1_Camera_{camera}_{view}.csv"
             for camera, view in (("A", "left"), ("B", "right"), ("3", "bottom"))]
    groups, errors = build_view_csv_sets(paths)
    assert not errors and len(groups) == 1


@pytest.mark.parametrize("first, second", [
    ("mouse01_trial1", "mouse02_trial1"), ("mouse1_trial1", "mouse1_trial2"),
    ("mouse_alice_trial1", "mouse_bob_trial1"), ("mouse1_day7", "mouse1_day8"),
    ("GX010120_M3_seg5", "GX010121_M3_seg5"), ("mouse1_001", "mouse1_002"),
    ("mouse1_2026_09_10", "mouse1_2026_10_09"),
])
def test_similarity_cannot_override_distinct_recording_identifiers(first, second):
    assert recording_name_similarity(first, second) == 0


def test_animal_id_prefixes_and_field_order_are_equivalent():
    assert recording_name_similarity("Mouse_ID_002_trial01", "run1_animalid2") == 100


def test_incomplete_recordings_do_not_borrow_views_from_other_animals_or_trials(tmp_path):
    paths = [tmp_path / name for name in ("M1_trial1_left.csv", "M1_trial2_right.csv", "M2_trial1_bottom.csv")]
    groups, errors = build_view_csv_sets(paths)
    assert not groups and len(errors) == 3


def test_fuzzy_matching_does_not_cross_sessions(tmp_path):
    paths = [tmp_path / session / f"{mouse}_{view}.csv"
             for session, mouse, view in (("day1", "Mouse01", "left"), ("day2", "M1", "right"),
                                          ("day2", "mouse1", "bottom"))]
    groups, errors = build_view_csv_sets(paths)
    assert not groups and errors


def test_equal_same_view_candidates_require_review_and_input_order_does_not_decide(tmp_path):
    paths = [tmp_path / name for name in ("M1_trial1_left.csv", "mouse1_trial1_right.csv",
                                         "mouse01_trial01_right.csv", "M1_trial1_bottom.csv")]
    rows = build_view_pair_rows(paths)
    assert rows == build_view_pair_rows(list(reversed(paths)))
    assert not any(row["status"] == "Ready" for row in rows)
    assert not any(row["right"] for row in rows if row["left"] or row["bottom"])


def test_fuzzy_matching_does_not_hide_duplicate_exports(tmp_path):
    paths = [tmp_path / name for name in ("M1_left.csv", "M1_left_filtered.csv", "mouse1_right.csv",
                                         "mouse01_bottom.csv")]
    groups, errors = build_view_csv_sets(paths)
    assert not groups
    assert any("Duplicate left" in error for error in errors)


def test_candidates_rank_matching_recording_and_view_above_similar_wrong_animals(tmp_path):
    anchor = tmp_path / "Mouse02_trial01_left.csv"
    correct = tmp_path / "M2_trial1_right_export.csv"
    other = tmp_path / "Mouse01_trial1_right.csv"
    unknown = tmp_path / "mouse2_trial1.csv"
    opposite = tmp_path / "mouse2_trial1_bottom.csv"
    ranked = rank_view_candidates([other, opposite, correct, unknown], "right", reference_paths=[anchor])
    assert [item.path for item in ranked] == [correct, unknown, other, opposite]
    assert "Recording name similarity 100%" in ranked[0].reasons


def test_manual_ranking_prefers_explicit_labels_when_filename_is_wrong(tmp_path):
    misnamed = tmp_path / "M1_left.csv"
    wrong_labels = tmp_path / "M1_right.csv"
    ranked = rank_view_candidates([wrong_labels, misnamed], "right", recording="M1", bodyparts_by_path={
        misnamed: ("r_hip", "r_knee"), wrong_labels: ("l_hip", "l_knee"),
    })
    assert ranked[0].path == misnamed
    assert "Right body-part labels" in ranked[0].reasons
    assert "Camera name says left; labels say right" in ranked[0].reasons


def test_used_files_are_ranked_after_available_matches(tmp_path):
    used, available = (tmp_path / f"M1_right{suffix}.csv" for suffix in ("", "_export"))
    ranked = rank_view_candidates([used, available], "right", recording="M1", used_paths=[used])
    assert ranked[0].path == available
    assert "Already assigned to another recording" in ranked[1].reasons


def test_completed_rows_sort_first_then_recordings_sort_naturally(tmp_path):
    paths = [tmp_path / f"mouse{mouse}_{view}.csv" for mouse in (10, 2) for view in ("left", "right", "bottom")]
    rows = build_view_pair_rows([tmp_path / "mouse1_left.csv", *paths])
    assert [row["name"] for row in rows] == ["mouse2", "mouse10", "mouse1"]
