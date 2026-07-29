"""Guided walkthrough controls and fixed tutorial asset definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QRegion
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.icons import interface_icon


@dataclass(frozen=True)
class TutorialAssets:
    preview_video: Path
    processed_preview_video: Path
    analyzed_video: Path
    coordinate_csv: Path
    coordinate_h5: Path
    processing_manifest: Path
    knee_manifest: Path
    calibration_map: Path
    gait_manifest: Path

    @classmethod
    def from_project_root(cls, project_root: Path) -> TutorialAssets:
        root = project_root / "assets" / "tutorial"
        return cls(
            preview_video=root / "GX010349 - trimmed.mp4",
            processed_preview_video=root / "GX010349 - trimmed_processed.mp4",
            analyzed_video=root / "GX010131_processed.mp4",
            coordinate_csv=(
                root
                / "GX010131_processedDLC_Resnet50_MAIN-SIDE #1Jun10shuffle1_snapshot_best-310.csv"
            ),
            coordinate_h5=(
                root
                / "GX010131_processedDLC_Resnet50_MAIN-SIDE #1Jun10shuffle1_snapshot_best-310.h5"
            ),
            processing_manifest=root / "processing_manifest.json",
            knee_manifest=root / "knee_analysis_manifest.json",
            calibration_map=root / "conversion_factor_map.json",
            gait_manifest=root / "gait_analysis_manifest.json",
        )

    def missing_paths(self) -> tuple[Path, ...]:
        return tuple(path for path in self.required_paths() if not path.is_file())

    def required_paths(self) -> tuple[Path, ...]:
        return (
            self.preview_video,
            self.processed_preview_video,
            self.analyzed_video,
            self.coordinate_csv,
            self.coordinate_h5,
            self.processing_manifest,
            self.knee_manifest,
            self.calibration_map,
            self.gait_manifest,
        )


@dataclass(frozen=True)
class TutorialStep:
    key: str
    title: str
    instruction: str


TUTORIAL_STEPS = (
    TutorialStep(
        "manual_calibration",
        "Calibration preview",
        "The trimmed tutorial video is loaded. Use the timeline and X/Y tools to "
        "practice placing calibration sticks.",
    ),
    TutorialStep(
        "video_processing",
        "Video processing preview",
        "The same trimmed video is loaded. Explore crop, enhancement, and trim controls; "
        "the processed tutorial clip is provided as a comparison.",
    ),
    TutorialStep(
        "deeplabcut",
        "DeepLabCut handoff",
        "This tutorial uses the supplied processed video, CSV, and H5 as precomputed "
        "DeepLabCut output, so no external analysis needs to run.",
    ),
    TutorialStep(
        "knee_correction",
        "Knee correction example",
        "The matching processed video, CSV, and H5 are paired for you. Inspect the "
        "detected labels and correction settings.",
    ),
    TutorialStep(
        "gait_parameter_analysis",
        "Gait analysis example",
        "The example is loaded in single-side mode from the supplied DLC coordinate "
        "dataset. Review setup, calibration, mapping, and preview controls.",
    ),
    TutorialStep(
        "pca_random_forest",
        "PCA and random forest",
        "This is the final manual stage. It consumes gait-analysis outputs for "
        "dimensionality reduction and classification; its controls are not available "
        "in this build.",
    ),
    TutorialStep(
        "automated_profiles",
        "Build an automated profile",
        "The tutorial manifests are loaded into a profile draft. Review how reusable "
        "video, model, calibration, gait, and knee settings fit together.",
    ),
    TutorialStep(
        "automated",
        "Automated pipeline",
        "The tutorial video is queued. Choose a saved profile, add videos, and start the "
        "combined workflow from this screen.",
    ),
)


@dataclass(frozen=True)
class TutorialGuideStep:
    title: str
    instruction: str
    expected: str
    target: Callable[[], QWidget | None]
    matches: Callable[[], bool]
    apply_value: Callable[[], None] | None = None
    prepare: Callable[[], None] | None = None


class TutorialSpotlightOverlay(QWidget):
    """Dim a workspace while leaving one highlighted control interactive."""

    apply_requested = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("TutorialSpotlightOverlay")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._target: QWidget | None = None
        self._spotlight_rect = QRect()
        self._step_number = QLabel()
        self._step_number.setObjectName("TutorialCalloutStep")
        self._title = QLabel()
        self._title.setObjectName("TutorialCalloutTitle")
        self._instruction = QLabel()
        self._instruction.setObjectName("TutorialCalloutInstruction")
        self._instruction.setWordWrap(True)
        self._expected = QLabel()
        self._expected.setObjectName("TutorialCalloutExpected")
        self._expected.setWordWrap(True)
        self._feedback = QLabel()
        self._feedback.setObjectName("TutorialCalloutFeedback")
        self._feedback.setWordWrap(True)
        self._feedback.hide()
        self.apply_button = QPushButton("Set for me")
        self.apply_button.setObjectName("TutorialApplyButton")
        self.apply_button.setToolTip(
            "Apply the exact value from the tutorial manifest to the highlighted setting."
        )
        self.apply_button.clicked.connect(self.apply_requested.emit)

        self._callout = QFrame(self)
        self._callout.setObjectName("TutorialCallout")
        layout = QVBoxLayout(self._callout)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(7)
        heading = QHBoxLayout()
        heading.setSpacing(8)
        heading.addWidget(self._step_number)
        heading.addWidget(self._title, 1)
        layout.addLayout(heading)
        layout.addWidget(self._instruction)
        layout.addWidget(self._expected)
        layout.addWidget(self._feedback)
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(self.apply_button)
        layout.addLayout(action_row)
        self._callout.setFixedWidth(400)
        self.apply_theme()
        self.hide()

    def set_guide(
        self,
        target: QWidget,
        *,
        index: int,
        total: int,
        title: str,
        instruction: str,
        expected: str,
        can_apply: bool,
    ) -> None:
        if self._target is not None:
            self._target.removeEventFilter(self)
        self._target = target
        self._target.installEventFilter(self)
        self._step_number.setText(f"{index + 1}/{total}")
        self._title.setText(title)
        self._instruction.setText(instruction)
        self._expected.setText(f"Target: {expected}")
        self._feedback.hide()
        self.apply_button.setVisible(can_apply)
        self.resize(self.parentWidget().size())
        self.show()
        self.raise_()
        QTimer.singleShot(0, self._refresh_geometry)

    def clear_guide(self) -> None:
        if self._target is not None:
            self._target.removeEventFilter(self)
        self._target = None
        self.clearMask()
        self.hide()

    def show_feedback(self, text: str, *, success: bool = False) -> None:
        self._feedback.setText(text)
        self._feedback.setProperty("tutorialSuccess", success)
        self._feedback.style().unpolish(self._feedback)
        self._feedback.style().polish(self._feedback)
        self._feedback.show()
        self._refresh_geometry()

    def eventFilter(self, watched, event) -> bool:
        if watched is self._target and event.type() in {
            QEvent.Move,
            QEvent.Resize,
            QEvent.Show,
            QEvent.Hide,
            QEvent.LayoutRequest,
        }:
            QTimer.singleShot(0, self._refresh_geometry)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_geometry()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(6, 10, 18, 210))
        if self._spotlight_rect.isEmpty():
            return

        accent = QColor(theme.PRIMARY)
        painter.setPen(QPen(accent, 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self._spotlight_rect.adjusted(1, 1, -1, -1), 8, 8)

        callout = self._callout.geometry()
        target = self._arrow_target(self._spotlight_rect, callout)
        start = self._arrow_start(callout, target)
        painter.setPen(QPen(accent, 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(start, target)
        direction = target - start
        length = max(1.0, (direction.x() ** 2 + direction.y() ** 2) ** 0.5)
        unit_x = direction.x() / length
        unit_y = direction.y() / length
        base = target - QPoint(round(unit_x * 14), round(unit_y * 14))
        normal = QPoint(round(-unit_y * 7), round(unit_x * 7))
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(
            QPolygonF([target, base + normal, base - normal])
        )

    def apply_theme(self) -> None:
        self._callout.setStyleSheet(
            theme.stylesheet(
                """
                QFrame#TutorialCallout {
                    background: {theme.SURFACE};
                    border: 2px solid {theme.PRIMARY};
                    border-radius: 8px;
                }
                QLabel#TutorialCalloutStep {
                    background: {theme.PRIMARY};
                    color: {theme.PRIMARY_TEXT};
                    border-radius: 9px;
                    font-size: 10px;
                    font-weight: 800;
                    min-width: 28px;
                    padding: 3px 6px;
                }
                QLabel#TutorialCalloutTitle {
                    color: {theme.TEXT};
                    font-size: 15px;
                    font-weight: 800;
                }
                QLabel#TutorialCalloutInstruction {
                    color: {theme.TEXT};
                    font-size: 12px;
                }
                QLabel#TutorialCalloutExpected {
                    background: {theme.PANEL};
                    border-left: 3px solid {theme.TOOL_2};
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 650;
                    padding: 7px 9px;
                }
                QLabel#TutorialCalloutFeedback {
                    color: {theme.STATUS_ERROR};
                    font-size: 11px;
                    font-weight: 700;
                }
                QLabel#TutorialCalloutFeedback[tutorialSuccess="true"] {
                    color: {theme.STATUS_READY};
                }
                QPushButton#TutorialApplyButton {
                    background: {theme.PRIMARY};
                    border: 1px solid {theme.PRIMARY};
                    border-radius: 4px;
                    color: {theme.PRIMARY_TEXT};
                    font-weight: 750;
                    min-height: 30px;
                    padding: 0 12px;
                }
                QPushButton#TutorialApplyButton:hover {
                    background: {theme.PRIMARY_HOVER};
                    border-color: {theme.PRIMARY_HOVER};
                }
                """
            )
        )

    def _refresh_geometry(self) -> None:
        if self._target is None or not self.isVisible():
            return
        target_top_left = self.mapFromGlobal(self._target.mapToGlobal(QPoint(0, 0)))
        target_rect = QRect(target_top_left, self._target.size()).adjusted(-8, -8, 8, 8)
        self._spotlight_rect = target_rect.intersected(self.rect().adjusted(3, 3, -3, -3))
        self._callout.adjustSize()
        self._position_callout()
        mask = QRegion(self.rect())
        if not self._spotlight_rect.isEmpty():
            mask -= QRegion(self._spotlight_rect)
        self.setMask(mask)
        self.update()

    def _position_callout(self) -> None:
        margin = 18
        target = self._spotlight_rect
        size = self._callout.sizeHint()
        width = self._callout.width()
        height = size.height()
        candidates = (
            QPoint(target.right() + margin, target.center().y() - height // 2),
            QPoint(target.left() - width - margin, target.center().y() - height // 2),
            QPoint(target.center().x() - width // 2, target.bottom() + margin),
            QPoint(target.center().x() - width // 2, target.top() - height - margin),
        )
        bounds = self.rect().adjusted(12, 12, -12, -12)
        chosen = candidates[-1]
        for candidate in candidates:
            candidate_rect = QRect(candidate, QSize(width, height))
            if bounds.contains(candidate_rect):
                chosen = candidate
                break
        x = max(bounds.left(), min(chosen.x(), bounds.right() - width))
        y = max(bounds.top(), min(chosen.y(), bounds.bottom() - height))
        self._callout.setGeometry(x, y, width, height)

    @staticmethod
    def _arrow_start(callout: QRect, target: QPoint) -> QPoint:
        if target.x() < callout.left():
            return QPoint(callout.left(), max(callout.top(), min(target.y(), callout.bottom())))
        if target.x() > callout.right():
            return QPoint(callout.right(), max(callout.top(), min(target.y(), callout.bottom())))
        if target.y() < callout.top():
            return QPoint(max(callout.left(), min(target.x(), callout.right())), callout.top())
        return QPoint(max(callout.left(), min(target.x(), callout.right())), callout.bottom())

    @staticmethod
    def _arrow_target(spotlight: QRect, callout: QRect) -> QPoint:
        callout_center = callout.center()
        if callout.left() > spotlight.right():
            return QPoint(
                spotlight.right() + 5,
                max(spotlight.top(), min(callout_center.y(), spotlight.bottom())),
            )
        if callout.right() < spotlight.left():
            return QPoint(
                spotlight.left() - 5,
                max(spotlight.top(), min(callout_center.y(), spotlight.bottom())),
            )
        if callout.top() > spotlight.bottom():
            return QPoint(
                max(spotlight.left(), min(callout_center.x(), spotlight.right())),
                spotlight.bottom() + 5,
            )
        return QPoint(
            max(spotlight.left(), min(callout_center.x(), spotlight.right())),
            spotlight.top() - 5,
        )


class TutorialBar(QFrame):
    previous_requested = Signal()
    next_requested = Signal()
    exit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("TutorialBar")
        self.setAccessibleName("Guided tutorial controls")
        self.setFixedHeight(76)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 16, 8)
        layout.setSpacing(14)

        self.progress_label = QLabel()
        self.progress_label.setObjectName("TutorialProgress")
        layout.addWidget(self.progress_label)

        copy_layout = QVBoxLayout()
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("TutorialTitle")
        copy_layout.addWidget(self.title_label)
        self.instruction_label = QLabel()
        self.instruction_label.setObjectName("TutorialInstruction")
        self.instruction_label.setWordWrap(True)
        copy_layout.addWidget(self.instruction_label)
        layout.addLayout(copy_layout, 1)

        self.previous_button = QPushButton("Back")
        self.previous_button.setObjectName("TutorialSecondaryButton")
        self.next_button = QPushButton("Next")
        self.next_button.setObjectName("TutorialNextButton")
        self.exit_button = QPushButton("Exit tutorial")
        self.exit_button.setObjectName("TutorialSecondaryButton")
        self.previous_button.setToolTip("Return to the previous tutorial step")
        self.exit_button.setToolTip("Stop the tutorial and return to the main menu")
        layout.addWidget(self.previous_button)
        layout.addWidget(self.next_button)
        layout.addWidget(self.exit_button)

        self.previous_button.clicked.connect(self.previous_requested.emit)
        self.next_button.clicked.connect(self.next_requested.emit)
        self.exit_button.clicked.connect(self.exit_requested.emit)
        self.apply_theme()

    def set_step(self, index: int, steps: tuple[TutorialStep, ...]) -> None:
        step = steps[index]
        self.progress_label.setText(f"Tutorial  {index + 1} / {len(steps)}")
        self.title_label.setText(step.title)
        self.instruction_label.setText(step.instruction)
        self.previous_button.setEnabled(index > 0)
        self.next_button.setText("Finish" if index == len(steps) - 1 else "Next")
        self.next_button.setToolTip(
            "Finish the tutorial" if index == len(steps) - 1 else f"Continue to {steps[index + 1].title}"
        )

    def apply_theme(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
                QFrame#TutorialBar {
                    background: {theme.PANEL};
                    border: 0;
                    border-top: 1px solid {theme.TOOL_2};
                    border-bottom: 1px solid {theme.BORDER};
                }
                QLabel#TutorialProgress {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.TOOL_2};
                    border-radius: 4px;
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 700;
                    padding: 5px 8px;
                }
                QLabel#TutorialTitle {
                    color: {theme.TEXT};
                    font-size: 13px;
                    font-weight: 700;
                }
                QLabel#TutorialInstruction {
                    color: {theme.CONNECTOR};
                    font-size: 11px;
                }
                QPushButton#TutorialSecondaryButton,
                QPushButton#TutorialNextButton {
                    border-radius: 4px;
                    min-height: 30px;
                    padding: 0 12px;
                }
                QPushButton#TutorialSecondaryButton {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    color: {theme.TEXT};
                }
                QPushButton#TutorialSecondaryButton:hover {
                    background: {theme.SOFT};
                    border-color: {theme.TEXT};
                }
                QPushButton#TutorialNextButton {
                    background: {theme.PRIMARY};
                    border: 1px solid {theme.PRIMARY};
                    color: {theme.PRIMARY_TEXT};
                    font-weight: 700;
                }
                QPushButton#TutorialNextButton:hover {
                    background: {theme.PRIMARY_HOVER};
                    border-color: {theme.PRIMARY_HOVER};
                }
                """
            )
        )
        self.next_button.setIcon(interface_icon("play", theme.PRIMARY_TEXT))
        self.exit_button.setIcon(interface_icon("clear", theme.TEXT))
        for button in (self.previous_button, self.next_button, self.exit_button):
            button.setIconSize(QSize(14, 14))
