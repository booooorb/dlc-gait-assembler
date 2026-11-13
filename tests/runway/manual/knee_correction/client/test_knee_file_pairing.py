from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from dlc_gait_assembly.app.app_bootstrap import create_knee_correction_use_cases, create_media_access
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_dataset_pairing import pair_coordinate_files
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_view import KneeCorrectionWidget
from dlc_gait_assembly.runway.manual.knee_correction.client.knee_pairing_dialog import KneePairingDialog
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def choose(combo, path):
    combo.setCurrentIndex(combo.findData(str(path)))


def test_custom_pairings_reach_workspace_and_survive_adding_files(app, tmp_path, monkeypatch):
    widget = KneeCorrectionWidget(
        use_cases=create_knee_correction_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
    )
    paths = [tmp_path / name for name in ("labels.csv", "tracking.h5", "recording.mp4")]
    for path in paths:
        path.touch()
    widget.inputs._add_paths(paths)
    assert not all(pair.is_paired for pair in widget.state.pairs)

    def apply_dialog(dialog):
        csv, h5, video, _ = dialog._rows[0]
        choose(h5, paths[1])
        choose(video, paths[2])
        dialog.accept()
        return dialog.result()

    monkeypatch.setattr(KneePairingDialog, "exec", apply_dialog)
    widget.customize_pairings_button.click()
    assert len(widget.state.pairs) == 1
    pair = widget.state.pairs[0]
    assert (pair.csv_path, pair.h5_path, pair.video_path) == tuple(paths)
    widget.state.pixels_per_cm = 10.0
    widget.controller._update_run_state()
    assert widget.run_button.isEnabled()
    extra = [tmp_path / f"extra{suffix}" for suffix in (".csv", ".h5", ".mp4")]
    for path in extra:
        path.touch()
    widget.inputs._add_paths(extra)
    assert widget.state.pairs[0] == pair
    assert len(widget.state.pairs) == 2
    assert all(pair.is_paired for pair in widget.state.pairs)
    widget.reset_pairings_button.click()
    assert not widget.state.custom_pairs
    assert not widget.run_button.isEnabled()
    widget.clear_button.click()
    assert not widget.state.pairs
    assert not widget.customize_pairings_button.isEnabled()
    widget.close()


def test_dialog_blocks_duplicate_assignments_and_requires_explicit_exclusion(app, tmp_path):
    paths = [tmp_path / name for name in ("a.csv", "a.h5", "a.mp4", "b.csv", "b.h5", "b.mp4", "spare.h5")]
    dialog = KneePairingDialog(paths, pair_coordinate_files(paths))
    save = dialog.buttons.button(QDialogButtonBox.Save)
    assert not save.isEnabled()
    dialog.exclude_unassigned.setChecked(True)
    assert save.isEnabled()
    assert dialog.excluded_paths() == [paths[-1]]
    choose(dialog._rows[1][1], paths[1])
    assert not save.isEnabled()
    assert "more than once" in dialog._rows[0][3].text()
    assert "more than once" in dialog._rows[1][3].text()
    dialog.accept()
    assert dialog.result() == 0
    choose(dialog._rows[1][1], paths[4])
    assert save.isEnabled()
    dialog.accept()
    assert dialog.result() == 1
    assert all(pair.is_paired for pair in dialog.pairings())
    dialog.close()


def test_removing_custom_pair_does_not_restore_its_files(app, tmp_path):
    widget = KneeCorrectionWidget(
        use_cases=create_knee_correction_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
    )
    paths = [tmp_path / name for name in ("a.csv", "a.h5", "a.mp4")]
    for path in paths:
        path.touch()
    widget.inputs._add_paths(paths)
    widget.state.custom_pairs = list(widget.state.pairs)
    widget.inputs._refresh_pairs()
    widget.pair_table.topLevelItem(0).setSelected(True)
    widget.remove_button.click()
    assert not widget.state.custom_pairs
    assert not widget.state.selected_paths
    assert not widget.state.pairs
    widget.close()
