"""Exercise marker manipulation and frame filters through the Qt label editor."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QKeySequence, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from dlc_gait_assembly.app.app_bootstrap import create_automatic_workspace
from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import ReviewArtifact, StageReview
from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AutomatedStage
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_repository import (
    AutomatedProfileStore,
)
from dlc_gait_assembly.runway.automatic.review.business.automatic_label_correction import LabelReviewSource
from dlc_gait_assembly.runway.automatic.review.client.automatic_label_dialog import LabelCorrectionDialog
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_contracts import KneeCorrectionSettings


@pytest.fixture
def labels():
    columns = pd.MultiIndex.from_product(
        [["DLC"], ["hip", "knee", "ankle"], ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"],
    )
    return pd.DataFrame(
        [
            [21, 30, 0.95, 31, 30, 0.43, 41, 30, 0.9],
            [21, 30, 0.97, 35, 45, 0.93, 41, 30, 0.9],
            [21, 30, 0.99, np.nan, np.nan, 0.12, 41, 30, 0.9],
        ],
        columns=columns,
    )


class Capture:
    info = SimpleNamespace(frame_count=3)

    def __init__(self):
        self.closed = False
        self.read_calls = []

    def read_frame(self, frame):
        self.read_calls.append(frame)
        return np.zeros((80, 100, 3), dtype=np.uint8)

    def close(self):
        self.closed = True


def test_edit_move_copy_remove_and_restore_markers_with_filtered_frames(labels):
    app = QApplication.instance() or QApplication([])
    source = LabelReviewSource("Side", Path("video.mp4"), Path("video.csv"), Path("video.h5"), Path("model"))
    capture = Capture()
    review = StageReview(
        AutomatedStage.LABELED_VIDEOS,
        "videos",
        label_sources=(source,),
        knee_settings=KneeCorrectionSettings(10, 10, 1),
    )
    dialog = LabelCorrectionDialog(
        None,
        review,
        SimpleNamespace(label_artifacts=lambda _: (labels, labels, (4, 5))),
        SimpleNamespace(open_video=lambda _: capture),
    )
    try:
        dialog.show()
        app.processEvents()
        assert dialog.frame_model.frames == (2, 0)
        assert dialog.confidence_row.isVisible() and not dialog.distance_row.isVisible()
        assert not dialog.paste_button.isEnabled() and not dialog.undo_button.isEnabled()
        dialog.confidence.setValue(0)
        assert dialog.empty_preview.text() == "No frames match this filter."
        assert dialog.empty_preview.isVisible() and not dialog.copy_button.isEnabled()
        dialog.show_all.setFocus()
        QTest.keyClick(dialog.show_all, Qt.Key_Space)
        assert dialog.filter.currentText() == "All frames"
        assert not dialog.confidence_row.isVisible() and not dialog.distance_row.isVisible()
        assert capture.read_calls == [2, 0]
        dialog.filter.setCurrentIndex(1)
        assert dialog.frame_model.frames == (1,)
        assert dialog.distance_row.isVisible() and not dialog.confidence_row.isVisible()
        dialog.filter.setCurrentIndex(3)
        dialog.frame_list.setCurrentIndex(dialog.frame_model.index(0, 0))
        canvas = dialog.canvas
        canvas.fit_frame()
        canvas.setFocus()
        QTest.keyClick(canvas, Qt.Key_3)
        QTest.mouseClick(canvas.viewport(), Qt.LeftButton, pos=canvas.mapFromScene(QPointF(25, 35)))
        QTest.mouseClick(canvas.viewport(), Qt.LeftButton, Qt.ShiftModifier, canvas.mapFromScene(QPointF(35, 35)))
        assert dialog._selected() == {("hip",), ("knee",)}
        corner = canvas.mapFromScene(QPointF(19, 29))
        opposite = canvas.mapFromScene(QPointF(39, 40))
        QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=corner)
        QTest.mouseMove(canvas.viewport(), opposite)
        QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=opposite)
        assert dialog._selected() == {("hip",), ("knee",)}
        begin = canvas.mapFromScene(QPointF(35, 35))
        QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=begin)
        QTest.mouseMove(canvas.viewport(), begin + QPoint(18, 22))
        QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=begin + QPoint(18, 22))
        moved = dict(dialog.points)
        assert moved[("hip",)][0] > 21 and moved[("knee",)][1] > 30

        QTest.mouseClick(dialog.copy_button, Qt.LeftButton)
        assert dialog.marker_status.text() == "2 copied"
        binding = QKeySequence(QKeySequence.StandardKey.Copy)[0]
        QTest.keyClick(canvas, binding.key(), binding.keyboardModifiers())
        assert dialog.marker_status.text() == "2 copied"
        assert dialog.paste_button.isEnabled()
        QTest.keyClick(canvas, Qt.Key_Right)
        assert dialog.frame == 1
        QTest.mouseClick(dialog.paste_button, Qt.LeftButton)
        assert dialog.marker_status.text() == "2 pasted"
        assert dialog.points[("knee",)] == moved[("knee",)]
        QTest.keyClick(canvas, Qt.Key_Delete)
        assert ("knee",) not in dialog.points
        QTest.mouseClick(dialog.undo_button, Qt.LeftButton)
        assert dialog.points[("knee",)] == moved[("knee",)]
        assert dialog.marker_status.text() == "Undid change on frame 2"

        position = canvas.viewport().rect().center()
        starting_scale = canvas.transform().m11()
        wheel = QWheelEvent(
            QPointF(position),
            QPointF(canvas.viewport().mapToGlobal(position)),
            QPoint(),
            QPoint(0, 360),
            Qt.NoButton,
            Qt.NoModifier,
            Qt.NoScrollPhase,
            False,
        )
        QCoreApplication.sendEvent(canvas.viewport(), wheel)
        assert canvas.transform().m11() > starting_scale

        QTest.keyPress(dialog.frame_list, Qt.Key_Space)
        assert canvas._space
        starting_scroll = canvas.horizontalScrollBar().value()
        QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=position)
        QTest.mouseMove(canvas.viewport(), position - QPoint(35, 0))
        QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=position - QPoint(35, 0))
        assert canvas.horizontalScrollBar().value() > starting_scroll
        QTest.keyRelease(canvas, Qt.Key_Space)
        assert not canvas._space
        assert dialog.points[("knee",)] == moved[("knee",)]

        # A frame change during a drag clears the gesture, even if the marker is absent in the new frame.
        canvas.fit_frame()
        knee = moved[("knee",)]
        begin = canvas.mapFromScene(QPointF(knee[0] + 4, knee[1] + 5))
        QTest.mousePress(canvas.viewport(), Qt.LeftButton, pos=begin)
        assert canvas._gesture == "move"
        QTest.keyClick(canvas, Qt.Key_Right)
        QTest.mouseRelease(canvas.viewport(), Qt.LeftButton, pos=begin)
        assert dialog.frame == 2 and ("knee",) not in dialog.points
        assert capture.read_calls == [2, 0, 1]

        QTest.mouseClick(
            dialog.marker_list.viewport(),
            Qt.LeftButton,
            pos=dialog.marker_list.visualItemRect(dialog.marker_list.item(1)).center(),
        )
        assert dialog.active_marker == ("knee",)
        canvas.setFocus()
        QTest.keyClick(canvas, Qt.Key_2)
        assert canvas._mode == "add"
        assert dialog.tool_hint.text().startswith("Click to place knee.")
        QTest.keyClick(canvas, Qt.Key_1)
        assert canvas._mode == "pan"
        dialog.tune_save.click()
        assert dialog.correction.fine_tune
        assert len(dialog.correction.edits) == 4
        assert capture.closed
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def test_switching_recordings_keeps_edits_and_loads_the_right_video(labels):
    app = QApplication.instance() or QApplication([])
    sources = tuple(
        LabelReviewSource(name, Path(f"{name}.mp4"), Path(f"{name}.csv"), Path(f"{name}.h5"), Path("model"))
        for name in ("Left", "Right")
    )
    captures = []

    def open_video(_):
        capture = Capture()
        captures.append(capture)
        return capture

    review = StageReview(AutomatedStage.LABELED_VIDEOS, "videos", label_sources=sources)
    right = labels.copy()
    right.iloc[0, 0] = 32
    dialog = LabelCorrectionDialog(
        None,
        review,
        SimpleNamespace(
            label_artifacts=lambda source: (labels, labels, (0, 0)) if source == sources[0] else (right, right, (0, 0))
        ),
        SimpleNamespace(open_video=open_video),
    )
    try:
        dialog.show()
        app.processEvents()
        dialog.filter.setCurrentIndex(3)
        assert dialog.frame == 2
        dialog.keep_button.click()
        dialog.copy_button.click()
        assert dialog.paste_button.isEnabled()
        dialog.recording.setCurrentIndex(1)
        assert captures[0].closed and captures[1].read_calls == [0]
        assert dialog.points[("hip",)] == (32, 30)
        assert not dialog.paste_button.isEnabled()
        assert dialog.saved_status.text() == "1 frame ready to save"
        dialog.recording.setCurrentIndex(0)
        assert captures[1].closed and captures[2].read_calls == [2]
        assert dialog.frame == 2
        assert dialog.points[("hip",)] == (21, 30)
        assert dialog.paste_button.isEnabled()
        dialog.frame_save.click()
        assert {edit.marker for edit in dialog.correction.edits} == {("hip",), ("ankle",)}
        assert {edit.video for edit in dialog.correction.edits} == {sources[0].video}
    finally:
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("stage", [AutomatedStage.LABELED_VIDEOS, AutomatedStage.STICKPLOT])
def test_batch_review_correct_labels_opens_and_returns_to_the_same_review(tmp_path, stage, labels):
    app = QApplication.instance() or QApplication([])
    workspace = create_automatic_workspace(AutomatedProfileStore(tmp_path / "profiles"))
    capture = Capture()
    workspace.review_artifacts.label_artifacts = lambda _: (labels, labels, (0, 0))
    workspace.media_access.open_video = lambda _: capture
    original = tmp_path / "processed.mp4"
    source = LabelReviewSource("Side", original, original.with_suffix(".csv"), original.with_suffix(".h5"), tmp_path)
    reviewing_video = stage is AutomatedStage.LABELED_VIDEOS
    path = tmp_path / ("processed_labeled.mp4" if reviewing_video else "stickplot.svg")
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="32"/>' if not reviewing_video else "")
    review = StageReview(
        stage,
        "videos" if reviewing_video else "stickplots",
        items=(ReviewArtifact(path, path.name, "Side"),),
        label_sources=(source,),
    )
    submitted = []
    workspace._pipeline_worker = SimpleNamespace(
        waiting_for_review=True, correct_labels=submitted.append, isRunning=lambda: False
    )
    workspace.resize(1080, 660)
    workspace.show()
    workspace.set_pipeline_running(True)
    workspace.runs._pipeline_review_requested(stage, review)
    app.processEvents()

    try:
        button = workspace.pipeline_correct_labels_button
        preview = workspace.pipeline_review_preview_stack
        assert button.isVisible() and button.y() > preview.geometry().bottom()
        observations = []

        def close_editor(save):
            editor = app.activeModalWidget()
            if isinstance(editor, LabelCorrectionDialog):
                QTest.keyClick(editor.canvas, Qt.Key_2)
                observations.append(editor.mode == "add")
            else:
                observations.append(False)
            if isinstance(editor, LabelCorrectionDialog) and save:
                editor.keep_button.click()
                editor.frame_save.click()
            elif editor is not None:
                editor.reject()

        QTimer.singleShot(0, lambda: close_editor(False))
        QTest.mouseClick(button, Qt.LeftButton)
        assert observations == [True]
        assert workspace._pipeline_real_waiting_for_review == stage and button.isVisible()
        assert not submitted and capture.closed

        QTimer.singleShot(0, lambda: close_editor(True))
        QTest.mouseClick(button, Qt.LeftButton)
        (correction,) = submitted
        assert observations == [True, True]
        assert not correction.fine_tune and len(correction.edits) == 2
        assert workspace._pipeline_real_waiting_for_review is None and not button.isVisible()
    finally:
        workspace.close()
        workspace.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
