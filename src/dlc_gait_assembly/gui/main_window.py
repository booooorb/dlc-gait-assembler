from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QEasingCurve, QPropertyAnimation, QTimer, Qt, Signal
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
from dlc_gait_assembly.gui.manual_calibration.window import ManualCalibrationWidget
from dlc_gait_assembly.gui.video_editor.window import VideoEditorWidget


TRANSITION_CONTROL_FADE_MS = 460
TRANSITION_CONTROL_STAGGER_MS = 32
MAIN_MENU_STAGE_WIDTH = 1180
WORKFLOW_PATH_WIDTH = 1112
WORKFLOW_STEP_WIDTH = 192
WORKFLOW_STEP_HEIGHT = 190
WORKFLOW_CONNECTOR_WIDTH = 18

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
    accent: str = "#94a3b8"


TOOL_SPECS = [
    ToolSpec(
        "manual_calibration",
        "Calibration",
        ManualCalibrationWidget,
        True,
        description="Set measurement references and check spatial scale.",
        status="Ready",
        accent="#065f46",
    ),
    ToolSpec(
        "video_processing",
        "Video Processing",
        VideoEditorWidget,
        True,
        "Prepare videos, trims, crops, enhancements, and H.264 export.",
        "Ready",
        "#0f766e",
    ),
    ToolSpec(
        "deeplabcut",
        "DeepLabCut",
        DeepLabCutWidget,
        True,
        description="Train, evaluate, and analyze pose estimation projects.",
        status="Ready",
        accent="#0369a1",
    ),
    ToolSpec(
        "gait_parameter_analysis",
        "Gait Parameter Analysis",
        GaitAnalysisWidget,
        True,
        description="Assemble stride, stance, swing, and gait outputs.",
        status="Ready",
        accent="#1d4ed8",
    ),
    ToolSpec(
        "pca_random_forest",
        "PCA and Random Forest Analysis",
        description="Reduce gait features and build classification models.",
        accent="#6d28d9",
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

            animation = QPropertyAnimation(effect, b"opacity", self)
            animation.setDuration(TRANSITION_CONTROL_FADE_MS)
            animation.setStartValue(0.0)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.InOutCubic)
            animation.finished.connect(
                lambda target=target, effect=effect: self._finish_transition_effect(target, effect)
            )
            animation.finished.connect(lambda animation=animation: self._clear_transition_animation(animation))
            self._transition_animations.append(animation)
            QTimer.singleShot(index * TRANSITION_CONTROL_STAGGER_MS, animation.start)

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
        self._tools = tools
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(44, 34, 44, 42)
        root.setSpacing(26)
        root.addStretch(1)

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
            """
            QWidget {
                background: #ffffff;
                color: #172033;
                font-size: 13px;
            }
            QLabel {
                background: transparent;
            }
            QFrame#MenuStage {
                background: #ffffff;
                border: 1px solid #d8dee8;
                border-radius: 8px;
            }
            QLabel#MainMenuTitle {
                color: #0f172a;
                font-size: 34px;
                font-weight: 800;
            }
            QFrame#WorkflowPath {
                background: transparent;
                border: 0;
            }
            QLabel#WorkflowConnector {
                color: #8aa0b6;
                font-size: 22px;
                font-weight: 800;
                min-width: 18px;
            }
            QFrame#WorkflowStep {
                background: #f8fafc;
                border: 1px solid #d6dee9;
                border-radius: 7px;
            }
            QFrame#WorkflowStep[enabledStep="true"]:hover {
                background: #eefbfc;
                border-color: #0891b2;
            }
            QFrame#WorkflowStep[enabledStep="false"] {
                background: #eef1f5;
                border-color: #dbe1ea;
            }
            QLabel#StepIndex {
                color: #ffffff;
                border-radius: 18px;
                font-size: 15px;
                font-weight: 700;
                min-width: 36px;
                min-height: 36px;
                max-width: 36px;
                max-height: 36px;
            }
            QLabel#StepIndex[enabledStep="false"] {
                color: #9aa5b5;
            }
            QLabel#StepTitle {
                color: #111827;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#StepTitle[enabledStep="false"] {
                color: #94a3b8;
            }
            QLabel#StepDescription {
                color: #526173;
                font-size: 11px;
            }
            QLabel#StepDescription[enabledStep="false"] {
                color: #9aa5b5;
            }
            """
        )

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
        else:
            self.setToolTip("Not available yet.")
        self._build_ui(index, spec)

    def _build_ui(self, index: int, spec: ToolSpec) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        number = QLabel(str(index))
        number.setObjectName("StepIndex")
        number.setProperty("enabledStep", spec.enabled)
        number.setAlignment(Qt.AlignCenter)
        number.setStyleSheet(f"background: {spec.accent if spec.enabled else '#d6dee9'};")
        root.addWidget(number, 0, Qt.AlignLeft)

        title = QLabel(spec.label)
        title.setObjectName("StepTitle")
        title.setProperty("enabledStep", spec.enabled)
        title.setWordWrap(True)
        root.addWidget(title)

        description = QLabel(spec.description)
        description.setObjectName("StepDescription")
        description.setProperty("enabledStep", spec.enabled)
        description.setWordWrap(True)
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
