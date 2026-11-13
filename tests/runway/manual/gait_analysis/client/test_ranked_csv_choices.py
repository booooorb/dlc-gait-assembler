"""Verify that CSV choices rerank with the current row without replacing user input."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.runway.manual.gait_analysis.client.dialogs.gait_view_pairing_dialog import (
    CsvPairingDialog,
    combo_path,
)


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def empty_pairing_dialog(paths):
    dialog = CsvPairingDialog(paths, [])
    for row in list(dialog._rows):
        dialog._remove_row(row)
    return dialog, dialog._add_row()


def test_selecting_an_anchor_reorders_other_views_and_keeps_the_selected_path(app, tmp_path):
    paths = { (mouse, view): tmp_path / f"Mouse{mouse:02}_trial1_{view}.csv"
              for mouse in (1, 2) for view in ("left", "right", "bottom") }
    dialog, row = empty_pairing_dialog(list(paths.values()))
    row["name"].setText("My custom recording title")
    for mouse in (2, 1):
        row["left"].setCurrentIndex(row["left"].findData(str(paths[mouse, "left"])))
        assert combo_path(row["left"]) == paths[mouse, "left"]
        assert row["right"].itemData(1) == str(paths[mouse, "right"])
        assert row["bottom"].itemData(1) == str(paths[mouse, "bottom"])
        assert "Recording name similarity 100%" in row["right"].itemData(1, Qt.ToolTipRole)
        assert combo_path(row["right"]) is None
    assert row["name"].text() == "My custom recording title"
    dialog.close()


def test_mouse_id_and_recording_name_edits_update_ranking_without_an_anchor(app, tmp_path):
    first, second = [tmp_path / f"mouse{mouse}_right.csv" for mouse in (1, 2)]
    dialog, row = empty_pairing_dialog([first, second])
    row["animal_id"].setText("M2")
    assert row["right"].itemData(1) == str(second)
    row["animal_id"].clear()
    row["name"].setText("M2")
    assert row["right"].itemData(1) == str(second)
    row["name"].setText("M1")
    assert row["right"].itemData(1) == str(first)
    dialog.close()


def test_reranking_keeps_search_queries_and_manual_choices(app, tmp_path):
    paths = [tmp_path / f"M1_{view}.csv" for view in ("left", "right", "bottom")]
    dialog, row = empty_pairing_dialog(paths)
    row["right"].setEditText("still searching")
    row["left"].setCurrentIndex(row["left"].findData(str(paths[0])))
    assert row["right"].currentText() == "still searching"
    assert combo_path(row["right"]) is None
    row["right"].setCurrentIndex(row["right"].findData(str(paths[1])))
    row["animal_id"].setText("M1")
    assert combo_path(row["right"]) == paths[1]
    assert "Right camera name" in row["right"].toolTip()
    dialog.close()


def test_files_assigned_elsewhere_move_down_the_choices(app, tmp_path):
    paths = [tmp_path / name for name in ("M1_right.csv", "M1_right_export.csv")]
    dialog, first_row = empty_pairing_dialog(paths)
    second_row = dialog._add_row()
    first_row["right"].setCurrentIndex(first_row["right"].findData(str(paths[0])))
    assert second_row["right"].itemData(1) == str(paths[1])
    assert "Already assigned" in second_row["right"].itemData(2, Qt.ToolTipRole)
    first_row["right"].setCurrentIndex(0)
    assert second_row["right"].itemData(1) == str(paths[0])
    dialog.close()
