from __future__ import annotations

import json
import os

import pytest
import pandas as pd


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.knee_correction import KneeCorrectionWidget
from dlc_gait_assembly.gui.knee_correction.window import KneeStickplotPreview


def test_unpaired_labels_are_red_until_matching_file_is_added(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(KneeCorrectionWidget, "_default_output_folder", lambda _self: tmp_path)
    widget = KneeCorrectionWidget()
    assert [
        widget.settings_tabs.tabText(index)
        for index in range(widget.settings_tabs.count())
    ] == ["Calibration", "Label selection"]
    csv_path = tmp_path / "mouse.csv"
    h5_path = tmp_path / "mouse.h5"
    video_path = tmp_path / "mouse.mp4"
    csv_path.touch()
    h5_path.touch()
    video_path.touch()

    widget._add_paths([csv_path])

    unpaired = widget.pair_table.topLevelItem(0)
    assert unpaired.text(4) == "Missing H5 + Missing Video"
    assert unpaired.foreground(0).color() == QColor(theme.STATUS_ERROR)
    assert not widget.run_button.isEnabled()

    widget._add_paths([h5_path])

    missing_video = widget.pair_table.topLevelItem(0)
    assert missing_video.text(4) == "Missing Video"
    assert not widget.run_button.isEnabled()

    widget._add_paths([video_path])

    paired = widget.pair_table.topLevelItem(0)
    assert paired.text(4) == "Paired"
    assert not widget.run_button.isEnabled()

    calibration_map = tmp_path / "conversion_factor_map.json"
    calibration_map.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "overall": {"mean_pixels_per_centimeter": 12.5}
                }
            }
        ),
        encoding="utf-8",
    )
    assert widget._set_calibration_map(calibration_map)
    assert "12.500 px/cm" in widget.calibration_map_label.text()
    assert widget.run_button.isEnabled()
    widget.close()
    app.processEvents()


def test_knee_label_selector_is_populated_from_dlc_header(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(KneeCorrectionWidget, "_default_output_folder", lambda _self: tmp_path)
    widget = KneeCorrectionWidget()
    columns = pd.MultiIndex.from_product(
        [["DLC_test"], ["hip", "custom_joint", "ankle"], ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"],
    )
    csv_path = tmp_path / "labels.csv"
    h5_path = tmp_path / "labels.h5"
    video_path = tmp_path / "labels.mp4"
    rows = [
        [offset, 0.0, 0.99, 2.0 + offset, 1.0, 0.5, 4.0 + offset, 0.0, 0.98]
        for offset in (0.0, 0.2, 0.4)
    ]
    pd.DataFrame(rows, columns=columns).to_csv(csv_path)
    h5_path.touch()
    video_path.touch()

    widget._add_paths([csv_path, h5_path, video_path])
    assert "calibration" in widget.preview_status_label.text().lower()
    assert "calibration" in widget.knee_preview._empty_message.lower()

    choices = [widget.knee_label_combo.itemText(index) for index in range(widget.knee_label_combo.count())]
    assert choices == [
        "Auto-detect labels containing 'knee'",
        "hip",
        "custom_joint",
        "ankle",
    ]
    assert widget.hip_label_combo.count() == 4
    assert widget.ankle_label_combo.count() == 4
    widget.knee_label_combo.setCurrentText("custom_joint")
    widget.hip_label_combo.setCurrentText("hip")
    widget.ankle_label_combo.setCurrentText("ankle")
    widget.generated_knee_label_edit.setText("generated_knee")
    widget.knee_direction_combo.setCurrentText("Manual side B")
    settings = widget._settings()
    assert settings.knee_bodyparts == ("custom_joint",)
    assert settings.hip_bodypart == "hip"
    assert settings.ankle_bodypart == "ankle"
    assert settings.output_knee_bodypart == "generated_knee"
    assert settings.knee_direction == "negative"
    calibration_map = tmp_path / "conversion_factor_map.json"
    calibration_map.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "overall": {"mean_pixels_per_centimeter": 2.0}
                }
            }
        ),
        encoding="utf-8",
    )
    assert widget._set_calibration_map(calibration_map)
    assert len(widget._preview_cache) == 1
    assert widget.preview_slider.maximum() == 2
    assert widget.preview_frame_label.minimumWidth() == widget.preview_frame_label.maximumWidth()
    assert widget.preview_slider.maximum() == 2
    assert widget.knee_preview._old_knee != widget.knee_preview._new_knee
    assert not widget.previous_frame_button.isEnabled()
    assert widget.next_frame_button.isEnabled()
    widget.next_frame_button.click()
    assert widget.preview_slider.value() == 1
    assert widget.previous_frame_button.isEnabled()
    widget.next_frame_button.click()
    assert widget.preview_slider.value() == 2
    assert not widget.next_frame_button.isEnabled()
    widget.previous_frame_button.click()
    assert widget.preview_slider.value() == 1
    widget.preview_slider.setValue(2)
    assert "Frame 2" in widget.preview_frame_label.text()
    widget._preview_original.loc[0, ("DLC_test", "custom_joint", "x")] = float("nan")
    widget._preview_original.loc[0, ("DLC_test", "custom_joint", "y")] = float("nan")
    widget._show_preview_frame(0)
    assert "unavailable: old knee" in widget.preview_frame_label.text()
    assert widget.knee_preview._old_knee is None
    widget._preview_original.loc[0, ("DLC_test", "hip", "x")] = float("nan")
    widget._preview_original.loc[0, ("DLC_test", "hip", "y")] = float("nan")
    widget._show_preview_frame(0)
    assert "hip" in widget.preview_frame_label.text()
    assert widget.knee_preview._hip is None
    widget.close()
    app.processEvents()


def test_calibration_auto_generates_previews_for_all_paired_datasets(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(KneeCorrectionWidget, "_default_output_folder", lambda _self: tmp_path)
    widget = KneeCorrectionWidget()
    columns = pd.MultiIndex.from_product(
        [["DLC_test"], ["hip", "knee", "ankle"], ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"],
    )
    rows = [
        [offset, 0.0, 0.99, 2.0 + offset, 1.0, 0.9, 4.0 + offset, 0.0, 0.98]
        for offset in (0.0, 0.2)
    ]
    paths = []
    for stem in ("first", "second"):
        csv_path = tmp_path / f"{stem}.csv"
        h5_path = tmp_path / f"{stem}.h5"
        video_path = tmp_path / f"{stem}.mp4"
        pd.DataFrame(rows, columns=columns).to_csv(csv_path)
        h5_path.touch()
        video_path.touch()
        paths.extend([csv_path, h5_path, video_path])
    widget._add_paths(paths)
    calibration_map = tmp_path / "conversion_factor_map.json"
    calibration_map.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "overall": {"mean_pixels_per_centimeter": 2.0}
                }
            }
        ),
        encoding="utf-8",
    )

    assert widget._set_calibration_map(calibration_map)

    assert len(widget._preview_cache) == 2
    assert widget._preview_original is not None
    widget.pair_table.setCurrentItem(widget.pair_table.topLevelItem(1))
    assert "second" in widget.preview_status_label.text()
    widget.close()
    app.processEvents()


def test_preview_slider_skips_low_confidence_frames(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(KneeCorrectionWidget, "_default_output_folder", lambda _self: tmp_path)
    widget = KneeCorrectionWidget()
    columns = pd.MultiIndex.from_product(
        [["DLC_test"], ["hip", "knee", "ankle"], ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"],
    )
    rows = [
        [0.0, 0.0, 0.99, 2.0, 1.0, 0.9, 4.0, 0.0, 0.99],
        [0.1, 0.0, 0.99, 2.1, 1.0, 0.9, 4.1, 0.0, 0.1],
        [0.2, 0.0, 0.1, 2.2, 1.0, 0.9, 4.2, 0.0, 0.99],
        [0.3, 0.0, 0.99, 2.3, 1.0, 0.9, 4.3, 0.0, 0.99],
    ]
    csv_path = tmp_path / "labels.csv"
    h5_path = tmp_path / "labels.h5"
    video_path = tmp_path / "labels.mp4"
    pd.DataFrame(rows, columns=columns).to_csv(csv_path)
    h5_path.touch()
    video_path.touch()
    widget._add_paths([csv_path, h5_path, video_path])
    widget.likelihood_threshold.setValue(0.5)
    calibration_map = tmp_path / "conversion_factor_map.json"
    calibration_map.write_text(
        json.dumps(
            {
                "conversion_factor_map": {
                    "overall": {"mean_pixels_per_centimeter": 2.0}
                }
            }
        ),
        encoding="utf-8",
    )

    assert widget._set_calibration_map(calibration_map)

    assert widget._preview_frame_positions == (0, 3)
    assert widget.preview_slider.maximum() == 1
    assert "Frame 0" in widget.preview_frame_label.text()
    widget.next_frame_button.click()
    assert widget.preview_slider.value() == 1
    assert "Frame 3" in widget.preview_frame_label.text()
    assert "Low-confidence" not in widget.preview_frame_label.text()
    widget.close()
    app.processEvents()


def test_knee_preview_frame_crop_zooms_around_limb_points():
    app = QApplication.instance() or QApplication([])
    preview = KneeStickplotPreview()
    preview.resize(400, 260)

    close_crop = preview._frame_crop_rect(
        [(900.0, 720.0), (940.0, 730.0), (918.0, 700.0)],
        1920,
        1080,
    )
    wide_crop = preview._frame_crop_rect(
        [(200.0, 200.0), (1600.0, 850.0), (900.0, 450.0)],
        1920,
        1080,
    )

    assert close_crop.width() < 1920
    assert close_crop.height() < 1080
    assert close_crop.left() <= 900.0 <= close_crop.right()
    assert close_crop.top() <= 700.0 <= close_crop.bottom()
    assert wide_crop.width() > close_crop.width()
    assert wide_crop.height() > close_crop.height()
    preview.close()
    app.processEvents()
