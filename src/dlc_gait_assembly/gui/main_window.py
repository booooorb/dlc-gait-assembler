from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QProgressBar,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui.deeplabcut.window import DeepLabCutWidget
from dlc_gait_assembly.gui.gait_analysis.window import GaitAnalysisWidget
from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.pca_random_forest.window import PcaRandomForestWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget


TRANSITION_CONTROL_FADE_MS = 220
TRANSITION_CONTROL_STAGGER_MS = 14
TRANSITION_CONTROL_RISE_PX = 12
MAIN_MENU_STAGE_WIDTH = 1180
WORKFLOW_PATH_WIDTH = 1112
WORKFLOW_STEP_WIDTH = 192
WORKFLOW_STEP_HEIGHT = 190
WORKFLOW_CONNECTOR_WIDTH = 18
MAIN_MENU_LOGO_HEIGHT = 38
MAIN_MENU_LOGO_MAX_WIDTH = 150

ANIMATED_CONTROL_TYPES = (
    QAbstractButton,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QSlider,
    QSpinBox,
)
ANIMATED_OBJECT_NAMES = {
    "PreviewTitle",
    "TitleLabel",
    "WorkflowStep",
}


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    widget_factory: Callable[[], QWidget] | None = None
    enabled: bool = False
    description: str = ""
    status: str = "Coming soon"
    accent: str = theme.NUMBER_ICON


TOOL_SPECS = [
    ToolSpec(
        "manual_calibration",
        "Calibration",
        ManualCalibrationWidget,
        True,
        description="Set measurement references and check spatial scale.",
        status="Ready",
        accent=theme.STEP_NUMBER_COLORS[0],
    ),
    ToolSpec(
        "video_processing",
        "Video Processing",
        VideoEditorWidget,
        True,
        "Prepare videos, regions, trims, enhancements, and H.264 export.",
        "Ready",
        theme.STEP_NUMBER_COLORS[1],
    ),
    ToolSpec(
        "deeplabcut",
        "DeepLabCut",
        DeepLabCutWidget,
        True,
        description="Train, evaluate, and analyze pose estimation projects.",
        status="Ready",
        accent=theme.STEP_NUMBER_COLORS[2],
    ),
    ToolSpec(
        "gait_parameter_analysis",
        "Gait Parameter Analysis",
        GaitAnalysisWidget,
        True,
        description="Assemble stride, stance, swing, and gait outputs.",
        status="Ready",
        accent=theme.STEP_NUMBER_COLORS[3],
    ),
    ToolSpec(
        "pca_random_forest",
        "PCA and Random Forest Analysis",
        PcaRandomForestWidget,
        True,
        description="Reduce gait features and build classification models.",
        status="Ready",
        accent=theme.STEP_NUMBER_COLORS[4],
    ),
]


class MainWindow(QMainWindow):
    def __init__(self, initial_tool_id: str | None = None):
        super().__init__()
        self.setWindowTitle("DLC Gait Assembler")
        self.resize(1280, 820)
        self._active_tool: QWidget | None = None
        self._active_tool_id: str | None = None
        self._did_initial_reveal = False
        self._transition_animations: list[QPropertyAnimation] = []
        self._transition_positions: dict[QWidget, QPoint] = {}
        self._tool_widgets: dict[str, QWidget] = {}
        self._stack = QStackedWidget()
        self._main_menu = MainMenuWidget(TOOL_SPECS)
        self._main_menu.tool_requested.connect(self._open_tool)
        self._stack.addWidget(self._main_menu)
        self.setCentralWidget(self._stack)
        self._build_navigation()
        if initial_tool_id is None:
            self._show_main_menu()
        else:
            self._open_tool(initial_tool_id)

    def closeEvent(self, event):
        for tool in self._tool_widgets.values():
            if hasattr(tool, "can_close") and not tool.can_close(self):
                event.ignore()
                return

        self._release_all_tools()

        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._did_initial_reveal:
            return

        self._did_initial_reveal = True
        QTimer.singleShot(0, lambda: self._fade_controls(self._stack.currentWidget()))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._repaint_current_widget)

    def _build_navigation(self) -> None:
        navigation = self.menuBar().addMenu("Navigation")
        main_menu_action = navigation.addAction("Main Menu")
        main_menu_action.triggered.connect(self._show_main_menu)
        navigation.addSeparator()

        for spec in TOOL_SPECS:
            action = navigation.addAction(spec.label)
            action.setEnabled(spec.enabled)
            if spec.enabled:
                action.triggered.connect(lambda _checked=False, tool_id=spec.id: self._open_tool(tool_id))

    def _show_main_menu(self) -> None:
        if not self._can_leave_active_tool():
            return

        self._active_tool = None
        self._active_tool_id = None
        self.setWindowTitle("DLC Gait Assembler")
        self._fade_to_widget(self._main_menu)

    def _open_tool(self, tool_id: str) -> None:
        if not self._can_leave_active_tool():
            return

        spec = self._tool_spec(tool_id)
        if spec.widget_factory is None or not spec.enabled:
            return

        tool = self._tool_widgets.get(tool_id)
        if tool is None:
            tool = spec.widget_factory()
            self._tool_widgets[tool_id] = tool
            self._stack.addWidget(tool)

        self._active_tool = tool
        self._active_tool_id = tool_id
        self.setWindowTitle(f"DLC Gait Assembler - {spec.label}")
        self._fade_to_widget(tool)

    def _tool_spec(self, tool_id: str) -> ToolSpec:
        for spec in TOOL_SPECS:
            if spec.id == tool_id:
                return spec
        raise ValueError(f"Unknown tool: {tool_id}")

    def _can_leave_active_tool(self) -> bool:
        if self._active_tool is None or not hasattr(self._active_tool, "can_close"):
            return True
        return bool(self._active_tool.can_close(self))

    def _fade_to_widget(self, widget: QWidget) -> None:
        for animation in self._transition_animations:
            animation.stop()
        self._transition_animations.clear()
        self._restore_transition_positions()

        self._stack.setCurrentWidget(widget)
        self._clear_opacity_effects(widget)
        if not self.isVisible():
            return

        self._fade_controls(widget)

    def _fade_controls(self, widget: QWidget) -> None:
        targets = self._transition_targets(widget)
        for index, target in enumerate(targets):
            effect = target.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(target)
                target.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            end_pos = QPoint(target.pos())
            start_pos = QPoint(end_pos.x(), end_pos.y() + TRANSITION_CONTROL_RISE_PX)
            self._transition_positions[target] = end_pos
            target.move(start_pos)

            opacity_animation = QPropertyAnimation(effect, b"opacity", self)
            opacity_animation.setDuration(TRANSITION_CONTROL_FADE_MS)
            opacity_animation.setStartValue(0.0)
            opacity_animation.setEndValue(1.0)
            opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
            opacity_animation.finished.connect(
                lambda target=target, effect=effect: self._finish_transition_effect(target, effect)
            )
            opacity_animation.finished.connect(lambda animation=opacity_animation: self._clear_transition_animation(animation))

            rise_animation = QPropertyAnimation(target, b"pos", self)
            rise_animation.setDuration(TRANSITION_CONTROL_FADE_MS)
            rise_animation.setStartValue(start_pos)
            rise_animation.setEndValue(end_pos)
            rise_animation.setEasingCurve(QEasingCurve.OutCubic)
            rise_animation.finished.connect(lambda target=target: self._finish_transition_position(target))
            rise_animation.finished.connect(lambda animation=rise_animation: self._clear_transition_animation(animation))

            self._transition_animations.append(opacity_animation)
            self._transition_animations.append(rise_animation)
            delay_ms = index * TRANSITION_CONTROL_STAGGER_MS
            QTimer.singleShot(delay_ms, opacity_animation.start)
            QTimer.singleShot(delay_ms, rise_animation.start)

    def _transition_targets(self, widget: QWidget) -> list[QWidget]:
        targets: list[QWidget] = []
        for child in widget.findChildren(QWidget):
            if not child.isVisible() or isinstance(child, QGraphicsView):
                continue
            if not _should_animate_transition_child(child):
                continue
            if _has_transition_target_ancestor(child, targets):
                continue
            targets.append(child)
        return targets

    def _clear_opacity_effects(self, widget: QWidget) -> None:
        for child in (widget, *widget.findChildren(QWidget)):
            effect = child.graphicsEffect()
            if isinstance(effect, QGraphicsOpacityEffect):
                effect.setOpacity(1.0)
                child.setGraphicsEffect(None)
                child.update()

    def _clear_transition_animation(self, animation: QPropertyAnimation) -> None:
        if animation in self._transition_animations:
            self._transition_animations.remove(animation)

    def _finish_transition_effect(self, target: QWidget, effect: QGraphicsOpacityEffect) -> None:
        effect.setOpacity(1.0)
        if target.graphicsEffect() is effect:
            target.setGraphicsEffect(None)
        target.updateGeometry()
        target.update()

    def _finish_transition_position(self, target: QWidget) -> None:
        end_pos = self._transition_positions.pop(target, None)
        if end_pos is not None:
            target.move(end_pos)
            target.updateGeometry()
            target.update()

    def _restore_transition_positions(self) -> None:
        for target, end_pos in list(self._transition_positions.items()):
            target.move(end_pos)
            target.updateGeometry()
            target.update()
        self._transition_positions.clear()

    def _repaint_current_widget(self) -> None:
        widget = self._stack.currentWidget()
        if widget is not None:
            widget.updateGeometry()
            widget.update()
            for child in widget.findChildren(QWidget):
                child.updateGeometry()
                child.update()

    def _release_all_tools(self) -> None:
        for tool in self._tool_widgets.values():
            if hasattr(tool, "release_resources"):
                tool.release_resources()
        self._tool_widgets.clear()
        self._active_tool = None
        self._active_tool_id = None


class MainMenuWidget(QWidget):
    tool_requested = Signal(str)

    def __init__(self, tools: list[ToolSpec]):
        super().__init__()
        self.setObjectName("MainMenuWidget")
        self._tools = tools
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 34, 44, 42)
        root.setSpacing(18)
        root.addStretch(1)

        logo_row = QHBoxLayout()
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.setSpacing(22)
        logo_row.addStretch(1)
        logo_row.addWidget(_main_menu_logo_label("choforcelab.png"))
        logo_row.addWidget(_main_menu_logo_label("NERVES_Logo.png"))
        logo_row.addStretch(1)
        root.addLayout(logo_row)

        stage = QFrame()
        stage.setObjectName("MenuStage")
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(34, 32, 34, 34)
        stage_layout.setSpacing(30)
        stage.setFixedWidth(MAIN_MENU_STAGE_WIDTH)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title = QLabel("DLC Gait Assembler")
        title.setObjectName("MainMenuTitle")
        title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title)

        stage_layout.addWidget(header)

        path_frame = QFrame()
        path_frame.setObjectName("WorkflowPath")
        path_frame.setFixedWidth(WORKFLOW_PATH_WIDTH)
        path_layout = QHBoxLayout(path_frame)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(10)

        for index, spec in enumerate(self._tools):
            step = WorkflowStep(index + 1, spec)
            if spec.enabled:
                step.clicked.connect(self.tool_requested.emit)
            path_layout.addWidget(step, 1)
            if index < len(self._tools) - 1:
                connector = QLabel(">")
                connector.setObjectName("WorkflowConnector")
                connector.setAlignment(Qt.AlignCenter)
                connector.setFixedWidth(WORKFLOW_CONNECTOR_WIDTH)
                path_layout.addWidget(connector, 0, Qt.AlignVCenter)

        stage_layout.addWidget(path_frame)

        root.addWidget(stage, 0, Qt.AlignHCenter)
        root.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
            QWidget#MainMenuWidget {
                background: {theme.BACKGROUND};
                color: {theme.TEXT};
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QFrame#MenuStage {
                background: {theme.PANEL};
                border: 1px solid {theme.ACCENT};
                border-radius: 8px;
            }
            QLabel#MainMenuTitle {
                color: {theme.TEXT};
                font-size: 34px;
                font-weight: 800;
            }
            QLabel#MainMenuLogo {
                background: transparent;
            }
            QFrame#WorkflowPath {
                background: transparent;
                border: 0;
            }
            QLabel#WorkflowConnector {
                color: {theme.CONNECTOR};
                font-size: 22px;
                font-weight: 800;
                min-width: 18px;
            }
            QFrame#WorkflowStep {
                background: {theme.SURFACE};
                border: 1px solid {theme.ACCENT};
                border-radius: 7px;
            }
            QFrame#WorkflowStep[enabledStep="true"]:hover {
                background: {theme.SURFACE};
                border-color: {theme.TEXT};
            }
            QFrame#WorkflowStep[enabledStep="false"] {
                background: {theme.SURFACE};
                border-color: {theme.ACCENT};
            }
            QLabel#StepIndex {
                color: {theme.BACKGROUND};
                border-radius: 18px;
                font-size: 15px;
                font-weight: 700;
                min-width: 36px;
                min-height: 36px;
                max-width: 36px;
                max-height: 36px;
            }
            QLabel#StepIndex[enabledStep="false"] {
                color: {theme.TEXT};
            }
            QLabel#StepTitle {
                color: {theme.TEXT};
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#StepTitle[enabledStep="false"] {
                color: {theme.ACCENT};
            }
            QLabel#StepDescription {
                color: {theme.TEXT};
                font-size: 11px;
                font-weight: 500;
            }
            QLabel#StepDescription[enabledStep="false"] {
                color: {theme.ACCENT};
            }
            """
            )
        )


def _main_menu_logo_label(filename: str) -> QLabel:
    label = QLabel()
    label.setObjectName("MainMenuLogo")
    label.setAlignment(Qt.AlignCenter)
    path = Path(__file__).resolve().parents[3] / "assets" / "images" / filename
    pixmap = QPixmap(str(path))
    if not pixmap.isNull():
        scale = max(1.0, QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() is not None else 1.0)
        scaled = pixmap.scaled(
            round(MAIN_MENU_LOGO_MAX_WIDTH * scale),
            round(MAIN_MENU_LOGO_HEIGHT * scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(scale)
        label.setPixmap(scaled)
        label.setFixedSize(round(scaled.width() / scale), round(scaled.height() / scale))
    return label


class WorkflowStep(QFrame):
    clicked = Signal(str)

    def __init__(self, index: int, spec: ToolSpec):
        super().__init__()
        self._spec = spec
        self.setObjectName("WorkflowStep")
        self.setProperty("enabledStep", spec.enabled)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(WORKFLOW_STEP_WIDTH, WORKFLOW_STEP_HEIGHT)
        if spec.enabled:
            self.setCursor(Qt.PointingHandCursor)
            if spec.description:
                self.setToolTip(spec.description)
        else:
            self.setToolTip("Not available yet.")
        self._build_ui(index, spec)

    def _build_ui(self, index: int, spec: ToolSpec) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 15, 16, 15)
        root.setSpacing(10)

        number = QLabel(str(index))
        number.setObjectName("StepIndex")
        number.setProperty("enabledStep", spec.enabled)
        number.setAlignment(Qt.AlignCenter)
        number.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        number.setStyleSheet(f"background: {spec.accent if spec.enabled else theme.SURFACE};")
        root.addWidget(number, 0, Qt.AlignLeft)

        title = QLabel(spec.label)
        title.setObjectName("StepTitle")
        title.setProperty("enabledStep", spec.enabled)
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(title)

        description = QLabel(spec.description)
        description.setObjectName("StepDescription")
        description.setProperty("enabledStep", spec.enabled)
        description.setWordWrap(True)
        description.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(description)
        root.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:
        if self._spec.enabled and event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit(self._spec.id)
            event.accept()
            return

        super().mouseReleaseEvent(event)


def _should_animate_transition_child(child: QWidget) -> bool:
    return child.objectName() in ANIMATED_OBJECT_NAMES or isinstance(child, ANIMATED_CONTROL_TYPES)


def _has_transition_target_ancestor(child: QWidget, targets: list[QWidget]) -> bool:
    parent = child.parentWidget()
    while parent is not None:
        if parent in targets:
            return True
        parent = parent.parentWidget()
    return False
