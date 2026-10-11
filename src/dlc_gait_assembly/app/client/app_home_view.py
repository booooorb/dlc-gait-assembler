"""Present the Ladder and Runway entry choices and animate the existing menu artwork."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPauseAnimation,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.client.app_branding_widgets import (
    HoverPixmapLabel,
    ManualMiniStage,
    MenuIllustrationLabel,
    WorkflowStep,
    WorkspaceChoiceCard,
)
from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
from dlc_gait_assembly.shared.client.theme.theme_application_styles import stylesheet as _dependency_theme_stylesheet
from dlc_gait_assembly.shared.client.theme.theme_menu_graphics import menu_colors, menu_font, menu_icon
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import mix_hex as _dependency_theme_mix_hex


class MainMenuWidget(QWidget):
    tool_requested = Signal(str)
    runway_requested = Signal()
    automated_requested = Signal()
    profiles_requested = Signal()
    manual_requested = Signal()

    def __init__(self, tools: list[ToolSpec], *, automatic_factory, runway_builder, manual_builder):
        super().__init__()
        self._automatic_factory = automatic_factory
        self._runway_builder, self._manual_builder = runway_builder, manual_builder
        self.setObjectName("MainMenuWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._tools = tools
        self._entrance_has_run = False
        self._entrance_animation: QParallelAnimationGroup | None = None
        self._manual_zoom_animation: QParallelAnimationGroup | None = None
        self._manual_zoom_overlay: QLabel | None = None
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 24, 40, 28)
        root.setSpacing(0)
        content = QWidget()
        content.setObjectName("MenuContent")
        content.setMaximumWidth(1320)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)
        view_stack = QStackedWidget()
        view_stack.setObjectName("MainMenuViewStack")
        home_page = QWidget()
        home_page.setObjectName("PipelineHomePage")
        home_layout = QVBoxLayout(home_page)
        home_layout.setContentsMargins(0, 0, 0, 0)
        home_layout.setSpacing(24)
        home_layout.addStretch(1)
        self._home_title = self._menu_heading(home_layout, "Choose a setup")
        choices = QHBoxLayout()
        choices.setSpacing(20)
        (runway_card, runway_button) = self._runway_choice_card()
        runway_button.clicked.connect(self.runway_requested.emit)
        runway_card.clicked.connect(self.runway_requested.emit)
        choices.addWidget(runway_card, 3)
        (ladder_card, ladder_button) = self._ladder_choice_card()
        ladder_button.clicked.connect(lambda: self.tool_requested.emit("ladder_analysis"))
        ladder_card.clicked.connect(lambda: self.tool_requested.emit("ladder_analysis"))
        choices.addWidget(ladder_card, 2)
        home_layout.addLayout(choices)
        home_layout.addStretch(1)
        self._runway_choice_card_widget = runway_card
        self._ladder_choice_card_widget = ladder_card
        self.ladder_choice_button = ladder_button
        self.runway_choice_button = runway_button
        self.manual_choice_button = runway_button
        self.home_page = home_page
        view_stack.addWidget(home_page)
        (automated_card, manual_card, runway_home_layout) = self._runway_builder(self, view_stack)
        self._manual_builder(
            self, automated_card, home_layout, ladder_card, manual_card, runway_card, runway_home_layout, view_stack
        )
        workspace_page = QWidget()
        workspace_page.setObjectName("PipelineWorkspacePage")
        workspace_layout = QVBoxLayout(workspace_page)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(10)
        section_title = QLabel("Manual pipeline")
        section_title.setObjectName("WorkflowTitle")
        workspace_layout.addWidget(section_title)
        self.section_title = section_title
        pipeline_tabs = QTabWidget()
        pipeline_tabs.setObjectName("PipelineTabs")
        pipeline_tabs.setDocumentMode(True)
        pipeline_tabs.tabBar().setExpanding(True)
        pipeline_tabs.tabBar().hide()
        pipeline_tabs.setAccessibleName("Pipeline type")
        manual_page = QWidget()
        manual_page.setObjectName("ManualPipelinePage")
        manual_layout = QVBoxLayout(manual_page)
        manual_layout.setContentsMargins(0, 4, 0, 0)
        manual_layout.addWidget(self._workflow_list(self._tools, connect_tools=True))
        pipeline_tabs.addTab(manual_page, "Manual pipeline")
        automated_page = QWidget()
        automated_page.setObjectName("AutomatedPipelinePage")
        automated_layout = QVBoxLayout(automated_page)
        automated_layout.setContentsMargins(0, 8, 0, 0)
        self.automated_profiles = self._automatic_factory()
        automated_layout.addWidget(self.automated_profiles)
        pipeline_tabs.addTab(automated_page, "Automated pipeline")
        self.pipeline_tabs = pipeline_tabs
        pipeline_tabs.currentChanged.connect(self._update_pipeline_heading)
        workspace_layout.addWidget(pipeline_tabs)
        self.workspace_page = workspace_page
        view_stack.addWidget(workspace_page)
        self.view_stack = view_stack
        content_layout.addWidget(view_stack)
        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        content_row.addStretch(1)
        content_row.addWidget(content, 100)
        content_row.addStretch(1)
        root.addLayout(content_row, 1)
        self._content = content

    @staticmethod
    def _menu_label(text: str, name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def _menu_heading(self, layout: QVBoxLayout, title: str) -> QLabel:
        heading = self._menu_label(title, "HomeTitle")
        heading.setAlignment(Qt.AlignCenter)
        layout.addWidget(heading)
        return heading

    @staticmethod
    def _menu_graphic(name: str, size: int = 28) -> HoverPixmapLabel:
        graphic = HoverPixmapLabel()
        graphic.setObjectName("MenuGraphic")
        graphic.setProperty("tablerIcon", name)
        graphic.setProperty("iconSize", size)
        graphic.setFixedSize(size + 8, size + 8)
        graphic.setAlignment(Qt.AlignCenter)
        return graphic

    @staticmethod
    def _menu_action(text: str, role: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("PipelineChoiceButton")
        button.setProperty("pipelineRole", role)
        button.setCursor(Qt.PointingHandCursor)
        button.setMinimumHeight(42)
        button.setIconSize(QSize(18, 18))
        return button

    def _automated_choice_card(self) -> tuple[WorkspaceChoiceCard, QPushButton, QPushButton]:
        card = WorkspaceChoiceCard("Run automated pipeline")
        card.setObjectName("PipelineChoiceCard")
        card.setProperty("pipelineRole", "automated")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(self._menu_graphic("player-play", 28))
        top.addStretch(1)
        top.addWidget(self._menu_label("Automated", "LaunchTitle"))
        layout.addLayout(top)
        layout.addStretch(1)
        flow = QHBoxLayout()
        flow.setSpacing(8)
        for index, (icon, label) in enumerate(
            (("folders", "Profile"), ("movie", "Videos"), ("chart-dots-3", "Results"))
        ):
            step = QVBoxLayout()
            step.setSpacing(7)
            step.addWidget(self._menu_graphic(icon, 24), 0, Qt.AlignCenter)
            title = self._menu_label(label, "FlowLabel")
            title.setAlignment(Qt.AlignCenter)
            step.addWidget(title)
            flow.addLayout(step, 1)
            if index < 2:
                flow.addWidget(self._menu_graphic("chevron-right", 16))
        layout.addLayout(flow)
        layout.addStretch(1)
        button = self._menu_action("Run automated pipeline", "automated")
        button.setToolTip("Select a profile and process a batch of videos.")
        layout.addWidget(button)
        profiles = QPushButton("Configure profiles")
        profiles.setObjectName("ConfigureProfilesButton")
        profiles.setCursor(Qt.PointingHandCursor)
        profiles.setToolTip("Create, edit, and manage reusable automation profiles.")
        card.make_decorations_mouse_transparent(button)
        return (card, button, profiles)

    def _manual_choice_card(self, *, expanded: bool = False) -> tuple[WorkspaceChoiceCard, QPushButton]:
        card = WorkspaceChoiceCard("Open manual pipeline")
        card.setObjectName("ManualStageDirectory" if expanded else "PipelineChoiceCard")
        card.setProperty("pipelineRole", "manual")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        if expanded:
            card.setFocusPolicy(Qt.NoFocus)
            card.setCursor(Qt.ArrowCursor)
            stages = QGridLayout()
            stages.setHorizontalSpacing(28)
            stages.setVerticalSpacing(0)
            names = (
                "Calibration",
                "Video processing",
                "DeepLabCut",
                "Knee correction",
                "Gait analysis",
                "PCA + random forest",
            )
            descriptions = (
                "Calibrate cameras and define 3D space.",
                "Crop, filter, and prepare videos.",
                "Track body keypoints with DLC.",
                "Compute knee positions and angles.",
                "Extract gait events and metrics.",
                "Explore patterns and classify movement.",
            )
            icons = ("ruler-measure", "movie", "topology-star-3", "angle", "walk", "chart-dots-3")
            for index, spec in enumerate(self._tools):
                stage = ManualMiniStage(spec.id)
                stage.setObjectName("ManualMiniStage")
                stage.setProperty("expandedStage", True)
                stage.setAccessibleName(f"Open {names[index]}")
                stage.setEnabled(spec.enabled)
                if spec.enabled:
                    stage.setCursor(Qt.PointingHandCursor)
                    stage.clicked.connect(self.tool_requested.emit)
                row = QHBoxLayout(stage)
                row.setContentsMargins(12, 16, 12, 16)
                row.setSpacing(16)
                row.addWidget(self._menu_graphic(icons[index], 26))
                copy = QVBoxLayout()
                copy.setSpacing(5)
                copy.addWidget(self._menu_label(f"{index + 1}. {names[index]}", "StageTitle"))
                copy.addWidget(self._menu_label(descriptions[index], "MenuBody"))
                row.addLayout(copy, 1)
                row.addWidget(self._menu_graphic("arrow-up-right", 18))
                for child in stage.findChildren(QWidget):
                    child.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                stages.addWidget(stage, index % 3, index // 3)
            stages.setColumnStretch(0, 1)
            stages.setColumnStretch(1, 1)
            layout.addLayout(stages, 1)
        else:
            top = QHBoxLayout()
            top.addWidget(self._menu_graphic("adjustments-horizontal", 28))
            top.addStretch(1)
            top.addWidget(self._menu_label("Manual", "LaunchTitle"))
            layout.addLayout(top)
            layout.addStretch(1)
            route = QFrame()
            route.setObjectName("ManualRoute")
            route_layout = QHBoxLayout(route)
            route_layout.setContentsMargins(0, 8, 0, 8)
            route_layout.setSpacing(12)
            for body in ("Calibration + video", "DLC + knee correction", "Gait + classification"):
                phase = QVBoxLayout()
                phase.setSpacing(5)
                phase.addWidget(self._menu_label(body, "MenuBody"))
                route_layout.addLayout(phase, 1)
            layout.addWidget(route)
            layout.addStretch(1)
        button = self._menu_action("Start with calibration" if expanded else "Open manual pipeline", "manual")
        button.setToolTip("Open the manual pipeline and choose an analysis stage.")
        layout.addWidget(button)
        if not expanded:
            card.make_decorations_mouse_transparent(button)
        return (card, button)

    def _runway_choice_card(self) -> tuple[WorkspaceChoiceCard, QPushButton]:
        card = WorkspaceChoiceCard("Open Runway analysis")
        card.setObjectName("RunwayChoiceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(10)
        illustration = MenuIllustrationLabel(
            "runway-mouse", "Laboratory mouse walking through a runway enclosure", card
        )
        layout.addWidget(illustration)
        layout.addWidget(self._menu_label("Runway analysis", "SetupTitle"))
        layout.addWidget(
            self._menu_label(
                "From tracked keypoints to gait metrics. Work stage by stage or automate a complete batch.",
                "LaunchBody",
            )
        )
        layout.addStretch(1)
        button = self._menu_action("Open Runway", "manual")
        layout.addWidget(button)
        card.make_decorations_mouse_transparent(button)
        self.runway_choice_illustration = illustration
        return (card, button)

    def _ladder_choice_card(self) -> tuple[WorkspaceChoiceCard, QPushButton]:
        card = WorkspaceChoiceCard("Open Ladder analysis")
        card.setObjectName("LadderChoiceCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(10)
        illustration = MenuIllustrationLabel(
            "ladder-mouse", "Laboratory mouse walking across a horizontal ladder", card
        )
        layout.addWidget(illustration)
        layout.addWidget(self._menu_label("Ladder analysis", "SetupTitle"))
        layout.addWidget(
            self._menu_label(
                "Review paw placements, detect slips and falls, and export rung-level events.", "LaunchBody"
            )
        )
        layout.addStretch(1)
        button = self._menu_action("Open ladder analysis", "ladder")
        layout.addWidget(button)
        card.make_decorations_mouse_transparent(button)
        self.ladder_choice_illustration = illustration
        return (card, button)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        compact = self.height() < 650
        if self.property("compactMenu") == compact:
            return
        self.setProperty("compactMenu", compact)
        self.layout().setContentsMargins(
            32 if compact else 40, 12 if compact else 24, 32 if compact else 40, 16 if compact else 28
        )
        for layout in self._menu_page_layouts:
            layout.setSpacing(10 if compact else 20)
        for card in self._launch_cards:
            card.layout().setContentsMargins(
                22 if compact else 28, 16 if compact else 24, 22 if compact else 28, 16 if compact else 24
            )
            card.layout().setSpacing(10 if compact else 16)
        self.setStyleSheet(self.styleSheet())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._entrance_has_run:
            QTimer.singleShot(0, self._start_home_entrance)

    def _start_home_entrance(self) -> None:
        if self._entrance_has_run or not self.isVisible():
            return
        self._entrance_has_run = True
        group = QParallelAnimationGroup(self)
        targets = (
            (self._home_title, 0, False),
            (self._runway_choice_card_widget, 80, True),
            (self._ladder_choice_card_widget, 170, True),
        )
        for widget, delay, add_depth in targets:
            end_position = widget.pos()
            start_position = end_position + QPoint(0, 14)
            widget.move(start_position)
            effect = QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.0)
            widget.setGraphicsEffect(effect)
            sequence = QSequentialAnimationGroup(group)
            if delay:
                sequence.addAnimation(QPauseAnimation(delay, sequence))
            reveal = QParallelAnimationGroup(sequence)
            opacity_animation = QPropertyAnimation(effect, b"opacity", reveal)
            opacity_animation.setDuration(300)
            opacity_animation.setStartValue(0.0)
            opacity_animation.setEndValue(1.0)
            opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            reveal.addAnimation(opacity_animation)
            rise_animation = QPropertyAnimation(widget, b"pos", reveal)
            rise_animation.setDuration(340)
            rise_animation.setStartValue(start_position)
            rise_animation.setEndValue(end_position)
            rise_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            reveal.addAnimation(rise_animation)
            reveal.finished.connect(
                lambda target=widget, depth=add_depth, final=end_position: self._finish_entrance_target(
                    target, depth, final
                )
            )
            sequence.addAnimation(reveal)
            group.addAnimation(sequence)
        self._entrance_animation = group
        group.start()

    def _finish_entrance_target(self, widget: QWidget, add_depth: bool, final_position: QPoint) -> None:
        widget.move(final_position)
        widget.setGraphicsEffect(None)
        if add_depth:
            self._apply_card_depth(widget)

    @staticmethod
    def _apply_card_depth(widget: QWidget) -> None:
        current_effect = widget.graphicsEffect()
        if isinstance(current_effect, QGraphicsDropShadowEffect):
            shadow = current_effect
        elif current_effect is not None:
            return
        else:
            shadow = QGraphicsDropShadowEffect(widget)
            widget.setGraphicsEffect(shadow)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 30 if theme.IS_DARK else 12))

    def show_home(self) -> None:
        self.view_stack.setCurrentWidget(self.home_page)
        QTimer.singleShot(0, self._apply_home_card_depth)

    def show_runway_home(self) -> None:
        self.view_stack.setCurrentWidget(self.runway_home_page)
        QTimer.singleShot(0, self._apply_runway_home_card_depth)

    def show_manual(self) -> None:
        self.pipeline_tabs.setCurrentIndex(0)
        animate = self.view_stack.currentWidget() is self.runway_home_page
        if not animate:
            self.view_stack.setCurrentWidget(self.manual_pipeline_page)
            QTimer.singleShot(0, lambda: self._apply_card_depth(self._expanded_manual_card_widget))
            return
        source = self._manual_choice_card_widget
        source_rect = QRect(source.mapTo(self, QPoint(0, 0)), source.size())
        source_pixmap = source.grab()
        self.view_stack.setCurrentWidget(self.manual_pipeline_page)
        destination_effect = QGraphicsOpacityEffect(self._expanded_manual_card_widget)
        destination_effect.setOpacity(0.0)
        self._expanded_manual_card_widget.setGraphicsEffect(destination_effect)
        overlay = QLabel(self)
        overlay.setObjectName("ManualPipelineZoomOverlay")
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        overlay.setScaledContents(True)
        overlay.setPixmap(source_pixmap)
        overlay.setGeometry(source_rect)
        overlay.show()
        overlay.raise_()
        self._manual_zoom_overlay = overlay
        QTimer.singleShot(0, self._start_manual_zoom)

    def _start_manual_zoom(self) -> None:
        overlay = self._manual_zoom_overlay
        if overlay is None:
            return
        target = self._expanded_manual_card_widget
        target_rect = QRect(target.mapTo(self, QPoint(0, 0)), target.size())
        group = QParallelAnimationGroup(self)
        geometry_animation = QPropertyAnimation(overlay, b"geometry", group)
        geometry_animation.setDuration(340)
        geometry_animation.setStartValue(overlay.geometry())
        geometry_animation.setEndValue(target_rect)
        geometry_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        group.addAnimation(geometry_animation)
        group.finished.connect(self._finish_manual_zoom)
        self._manual_zoom_animation = group
        group.start()

    def _finish_manual_zoom(self) -> None:
        overlay = self._manual_zoom_overlay
        destination_effect = self._expanded_manual_card_widget.graphicsEffect()
        if isinstance(destination_effect, QGraphicsOpacityEffect):
            destination_effect.setOpacity(1.0)
        self._expanded_manual_card_widget.repaint()
        if overlay is not None:
            overlay.hide()
            overlay.deleteLater()
        self._manual_zoom_overlay = None
        self._expanded_manual_card_widget.setGraphicsEffect(None)
        self._apply_card_depth(self._expanded_manual_card_widget)

    def show_automated(self) -> None:
        self.pipeline_tabs.setCurrentIndex(1)
        self.view_stack.setCurrentWidget(self.workspace_page)

    def _apply_home_card_depth(self) -> None:
        for card in (self._runway_choice_card_widget, self._ladder_choice_card_widget):
            self._apply_card_depth(card)

    def _apply_runway_home_card_depth(self) -> None:
        for card in (self._manual_choice_card_widget, self._automated_choice_card_widget):
            self._apply_card_depth(card)

    def _apply_workflow_card_depth(self) -> None:
        for card in self.workspace_page.findChildren(QFrame, "WorkflowStep"):
            self._apply_card_depth(card)

    def _update_pipeline_heading(self, index: int) -> None:
        self.section_title.setVisible(index == 0)
        if index == 0:
            self.section_title.setText("Manual pipeline")

    def _workflow_list(self, tools: list[ToolSpec], connect_tools: bool) -> QFrame:
        workflow_list = QFrame()
        workflow_list.setObjectName("WorkflowList")
        workflow_list.setFixedHeight(224)
        list_layout = QGridLayout(workflow_list)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setHorizontalSpacing(10)
        list_layout.setVerticalSpacing(10)
        for index, spec in enumerate(tools):
            step = WorkflowStep(index + 1, spec)
            if connect_tools and spec.enabled:
                step.clicked.connect(self.tool_requested.emit)
            list_layout.addWidget(step, index // 3, index % 3)
            list_layout.setColumnStretch(index % 3, 1)
        return workflow_list

    def _apply_style(self) -> None:
        self.automated_profiles._apply_style()
        c = menu_colors(theme.IS_DARK)
        self.setFont(menu_font())
        texture = _dependency_theme_stylesheet("{theme.BACKGROUND_TEXTURE}")
        self.setStyleSheet(
            f"""\n            QWidget#MainMenuWidget {{ background: {c["bg"]}; color: {c["text"]};\n                background-image: url({texture}); }}\n            QWidget#MenuContent, QStackedWidget#MainMenuViewStack,\n            QWidget#PipelineHomePage, QWidget#RunwayHomePage,\n            QWidget#ManualPipelineMenuPage, QWidget#PipelineWorkspacePage {{ background: transparent; border: 0; }}\n            QWidget#PipelineHomePage QWidget, QWidget#RunwayHomePage QWidget,\n            QWidget#ManualPipelineMenuPage QWidget {{ font-family: "Geist"; }}\n            QLabel {{ background: transparent; color: {c["text"]}; border: 0; }}\n            QLabel#HomeTitle {{ font-size: 42px; font-weight: 600; letter-spacing: -1px; }}\n            QLabel#MenuSubtitle {{ color: {c["muted"]}; font-size: 14px; }}\n            QFrame#PipelineChoiceCard, QFrame#RunwayChoiceCard, QFrame#LadderChoiceCard,\n            QFrame#ManualStageDirectory {{\n                background: {c["surface"]}; border: 1px solid {c["line"]}; border-radius: 10px;\n                min-height: 350px; max-height: 400px;\n            }}\n            QFrame#PipelineChoiceCard {{ min-height: 230px; max-height: 270px; }}\n            QFrame#PipelineChoiceCard[pipelineRole="manual"] {{ background: {c["tint"]}; }}\n            QFrame#PipelineChoiceCard:hover, QFrame#RunwayChoiceCard:hover,\n            QFrame#LadderChoiceCard:hover {{ border-color: {c["accent"]}; }}\n            QFrame#PipelineChoiceCard:focus, QFrame#RunwayChoiceCard:focus,\n            QFrame#LadderChoiceCard:focus {{ border: 2px solid {c["accent"]}; }}\n            QWidget#MainMenuWidget[compactMenu="true"] QLabel#HomeTitle {{ font-size: 34px; }}\n            QWidget#MainMenuWidget[compactMenu="true"] QLabel#LaunchTitle {{ font-size: 28px; }}\n            QWidget#MainMenuWidget[compactMenu="true"] QFrame#PipelineChoiceCard,\n            QWidget#MainMenuWidget[compactMenu="true"] QFrame#ManualStageDirectory {{\n                min-height: 300px; max-height: 350px;\n            }}\n            QWidget#MainMenuWidget[compactMenu="true"] QFrame#PipelineChoiceCard {{\n                min-height: 210px; max-height: 250px;\n            }}\n            QLabel#ModeName {{ color: {c["accent"]}; font-size: 14px; font-weight: 600; }}\n            QFrame#PipelineChoiceCard[pipelineRole="automated"] QLabel#ModeName {{ color: {theme.TOOL_1}; }}\n            QLabel#LaunchTitle {{ font-size: 34px; font-weight: 600; letter-spacing: -1px; }}\n            QFrame#PipelineChoiceCard[pipelineRole="manual"] QLabel#LaunchTitle {{ color: {theme.TOOL_3}; }}\n            QFrame#PipelineChoiceCard[pipelineRole="automated"] QLabel#LaunchTitle {{ color: {theme.TOOL_1}; }}\n            QFrame#PipelineChoiceCard[pipelineRole="automated"]:hover,\n            QFrame#PipelineChoiceCard[pipelineRole="automated"]:focus {{ border-color: {theme.TOOL_1}; }}\n            QFrame#LadderChoiceCard:hover, QFrame#LadderChoiceCard:focus {{ border-color: {theme.TOOL_2}; }}\n            QLabel#SetupTitle {{ font-size: 26px; font-weight: 600; letter-spacing: -0.5px; }}\n            QLabel#LaunchBody {{ color: {c["muted"]}; font-size: 14px; }}\n            QLabel#MenuBody {{ color: {c["muted"]}; font-size: 12px; }}\n            QLabel#PhaseTitle, QLabel#BridgeTitle {{ font-size: 14px; font-weight: 600; }}\n            QLabel#FlowLabel {{ color: {c["muted"]}; font-size: 12px; }}\n            QFrame#ManualRoute {{ background: transparent; border: 0; border-top: 1px solid {c["line"]}; }}\n            QFrame#ProfileBridge {{ background: {c["panel"]}; border: 0; border-radius: 10px; }}\n            QPushButton#PipelineChoiceButton {{\n                background: {c["button"]}; color: {c["button_text"]}; border: 1px solid {c["button"]};\n                border-radius: 8px; padding: 0 16px; min-height: 40px; font-size: 13px; font-weight: 600;\n            }}\n            QPushButton#PipelineChoiceButton[pipelineRole="automated"],\n            QPushButton#PipelineChoiceButton[pipelineRole="ladder"] {{\n                background: {c["surface"]}; color: {c["text"]}; border-color: {c["line"]};\n            }}\n            QPushButton#PipelineChoiceButton:hover {{ background: {c["accent"]}; color: {c["bg"]}; }}\n            QPushButton#PipelineChoiceButton[pipelineRole="automated"]:hover,\n            QPushButton#PipelineChoiceButton[pipelineRole="ladder"]:hover {{\n                background: {c["panel"]}; color: {c["text"]};\n            }}\n            QPushButton#PipelineChoiceButton[pipelineRole="automated"] {{\n                color: {theme.TOOL_1}; border-color: {theme.TOOL_1};\n            }}\n            QPushButton#PipelineChoiceButton[pipelineRole="automated"]:hover,\n            QPushButton#PipelineChoiceButton[pipelineRole="automated"]:focus {{\n                color: {theme.TOOL_1}; border-color: {theme.TOOL_1};\n                background: {_dependency_theme_mix_hex(theme.TOOL_1, theme.SURFACE, 0.9)};\n            }}\n            QPushButton#PipelineChoiceButton[pipelineRole="ladder"] {{\n                color: {theme.TOOL_2}; border-color: {theme.TOOL_2};\n            }}\n            QPushButton#PipelineChoiceButton[pipelineRole="ladder"]:hover,\n            QPushButton#PipelineChoiceButton[pipelineRole="ladder"]:focus {{\n                color: {theme.TOOL_2}; border-color: {theme.TOOL_2};\n            }}\n            QPushButton#PipelineChoiceButton:focus {{ border: 2px solid {c["accent"]}; }}\n            QPushButton#ConfigureProfilesButton {{\n                background: transparent; color: {theme.TOOL_2}; border: 1px solid {theme.TOOL_2};\n                border-radius: 6px; padding: 8px 12px; font-size: 12px; font-weight: 600;\n            }}\n            QPushButton#ConfigureProfilesButton:hover, QPushButton#ConfigureProfilesButton:focus {{\n                background: {_dependency_theme_mix_hex(theme.TOOL_2, theme.SURFACE, 0.9)}; border-color: {theme.TOOL_2};\n            }}\n            QFrame#ManualMiniStage {{ background: transparent; border: 0;\n                border-bottom: 1px solid {c["line"]}; min-height: 72px; }}\n            QFrame#ManualMiniStage:hover, QFrame#ManualMiniStage:focus {{\n                background: {c["tint"]}; border-radius: 8px;\n            }}\n            QLabel#StageTitle {{ font-size: 16px; font-weight: 600; }}\n            QFrame#WorkflowList, QFrame#WorkflowStep {{ background: {c["surface"]}; border: 0; }}\n            QLabel#StepTitle {{ color: {c["text"]}; font-size: 14px; font-weight: 600; }}\n            QLabel#StepDescription {{ color: {c["muted"]}; }}\n        """
        )
        for graphic in self.findChildren(HoverPixmapLabel):
            icon_name = graphic.property("tablerIcon")
            if icon_name:
                size = graphic.property("iconSize")
                color = c["accent"]
                parent = graphic.parentWidget()
                while parent is not None and parent is not self:
                    if parent.property("pipelineRole") == "automated":
                        color = theme.TOOL_1
                        break
                    if parent.property("pipelineRole") == "profiles":
                        color = theme.TOOL_2
                        break
                    parent = parent.parentWidget()
                graphic.setPixmap(menu_icon(icon_name, color, size).pixmap(QSize(size, size), 2.0))
        for button in (self.runway_choice_button, self.runway_manual_choice_button, self.start_manual_pipeline_button):
            button.setIcon(menu_icon("arrow-right", c["button_text"], 18))
        self.ladder_choice_button.setIcon(menu_icon("arrow-up-right", theme.TOOL_2, 18))
        self.automated_choice_button.setIcon(menu_icon("arrow-up-right", theme.TOOL_1, 18))
        self.configure_profiles_button.setIcon(menu_icon("folders", theme.TOOL_2, 18))
        for step in self.findChildren(WorkflowStep):
            step.apply_theme()
