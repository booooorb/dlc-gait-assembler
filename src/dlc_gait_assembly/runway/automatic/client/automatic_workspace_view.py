"""Compose profile editing, run execution, and artifact-review surfaces."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.runway.automatic.business.automatic_execution_contracts import StageReview
from dlc_gait_assembly.runway.automatic.client.automatic_display_constants import (
    PIPELINE_REVIEW_GATES,
    PIPELINE_STAGE_LABELS,
    PIPELINE_STAGES,
    RUN_PREVIEW_TOOLTIP,
)
from dlc_gait_assembly.runway.automatic.client.automatic_workspace_styles import automated_pipeline_stylesheet
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_contracts import AutomatedPipelineProfile
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_assets_panel import (
    AutomaticProfileAssetsPanel,
)
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_controller import AutomaticProfileController
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_editor import build_automatic_profile_editor
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_editor_state import (
    AutomaticProfileEditorState,
)
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_models_panel import (
    AutomaticProfileModelsPanel,
)
from dlc_gait_assembly.runway.automatic.profiles.client.automatic_profile_readiness_panel import (
    AutomaticProfileReadinessPanel,
)
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_controller import AutomaticReviewController
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_settings_link import AutomaticReviewSettingsLink
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_stickplot_panel import (
    AutomaticReviewStickplotPanel,
)
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_video_player import (
    AutomaticReviewVideoController,
    MediaPreviewDialog,
)
from dlc_gait_assembly.runway.automatic.review.client.automatic_review_view import build_automatic_review_view
from dlc_gait_assembly.runway.automatic.runs.client.automatic_demo_controller import AutomaticDemoController
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_controller import AutomaticRunController
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_log import AutomaticRunLog
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_view import build_automatic_run_workspace
from dlc_gait_assembly.runway.automatic.runs.client.automatic_run_worker import AutomatedPipelineWorker
from dlc_gait_assembly.runway.automatic.runs.client.automatic_stage_progress import AutomaticStageProgress
from dlc_gait_assembly.runway.automatic.runs.client.automatic_video_hover_preview import AutomaticVideoHoverPreview
from dlc_gait_assembly.runway.automatic.runs.client.automatic_video_queue import AutomaticVideoQueue
from dlc_gait_assembly.shared.business.media_access_contracts import MediaAccessPort
from dlc_gait_assembly.shared.client.qt_circular_progress import CircularProgressIndicator
from dlc_gait_assembly.shared.client.qt_linear_progress import DynamicProgressBar
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon

try:
    import cv2
except ImportError:
    cv2 = None


class AutomatedPipelineProfilesWidget(QWidget):
    """Switchable automation workspace and profile-configuration workspace."""

    workspace_changed = Signal(str)
    manual_tool_requested = Signal(str)

    def __init__(self, *, run_factory, media_access: MediaAccessPort, profile_use_cases, review_artifacts, workspace):
        super().__init__()
        self.workspace = workspace
        self.review_artifacts = review_artifacts
        self.profile_use_cases = profile_use_cases
        self.profile_state = AutomaticProfileEditorState()
        self.media_access = media_access
        self.run_factory = run_factory
        self.profiles = AutomaticProfileController(self)
        self.profile_assets = AutomaticProfileAssetsPanel(self)
        self.profile_models = AutomaticProfileModelsPanel(self)
        self.profile_readiness = AutomaticProfileReadinessPanel(self)
        self.runs = AutomaticRunController(self)
        self.demo = AutomaticDemoController(self)
        self.hover = AutomaticVideoHoverPreview(self)
        self.stage_progress = AutomaticStageProgress(self)
        self.queue = AutomaticVideoQueue(self)
        self.run_log = AutomaticRunLog(self)
        self.reviews = AutomaticReviewController(self)
        self.review_video = AutomaticReviewVideoController(self)
        self.review_stickplot = AutomaticReviewStickplotPanel(self)
        self.review_settings = AutomaticReviewSettingsLink(self)
        self.setObjectName("AutomatedPipelineProfilesWidget")
        project_root = self.workspace.root
        self._project_root = project_root
        self._automated_output_root = self.workspace.automatic_runs
        self._video_paths: list[Path] = []
        self._large_preview_dialog: MediaPreviewDialog | None = None
        self._large_review_dialog: QDialog | None = None
        self._hover_capture = None
        self._hover_preview_path: Path | None = None
        self._hover_preview_timer = QTimer(self)
        self._hover_preview_timer.timeout.connect(self.hover._advance_hover_preview)
        self._pipeline_running = False
        self._pipeline_demo_stage = -1
        self._pipeline_demo_progress = 0.0
        self._pipeline_demo_total_videos = 0
        self._pipeline_demo_last_processed = -1
        self._pipeline_demo_complete = False
        self._pipeline_demo_waiting_for_review: int | None = None
        self._pipeline_demo_blocked_stage: int | None = None
        self._pipeline_demo_timer = QTimer(self)
        self._pipeline_demo_timer.setInterval(60)
        self._pipeline_demo_timer.timeout.connect(self.demo._advance_pipeline_demo)
        self._pipeline_stage_emphasis_timer = QTimer(self)
        self._pipeline_stage_emphasis_timer.setInterval(33)
        self._pipeline_stage_emphasis_timer.timeout.connect(self.stage_progress._advance_pipeline_stage_emphasis)
        self._pipeline_emphasized_stage: int | None = None
        self._pipeline_stage_emphasis_initialized = False
        self._pipeline_stage_emphasis_elapsed = 0
        self._pipeline_stage_emphasis_starts: list[tuple[int, int]] = []
        self._pipeline_stage_emphasis_targets: list[tuple[int, int]] = []
        self._pipeline_worker: AutomatedPipelineWorker | None = None
        self._pipeline_output_folder: Path | None = None
        self._pipeline_real_complete = False
        self._pipeline_real_waiting_for_review: int | None = None
        self._pipeline_review_artifacts: StageReview | None = None
        self._pipeline_stickplot_path: Path | None = None
        self._pipeline_stickplot_pixmap: QPixmap | None = None
        self._pipeline_skipped_stages: set[int] = set()
        self._build_ui()
        self._connect_signals()
        self.profiles._refresh_profiles()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        header = QFrame()
        header.setObjectName("ProfileHeader")
        self._automation_header = header
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(24)
        title = QLabel("Automated pipeline")
        title.setObjectName("AutomatedProfileTitle")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_row.addWidget(self._field_label("Profile"))
        self.profile_selector = QComboBox()
        self.profile_selector.setObjectName("ProfileSelector")
        self.profile_selector.setMinimumWidth(220)
        self.profile_selector.setAccessibleName("Saved automated pipeline profile")
        self.profile_selector.setToolTip(
            "Choose the saved setup this run will use. A profile contains the video processing manifest, region-specific DeepLabCut models, and any analysis stages enabled when the profile was created."
        )
        selector_row.addWidget(self.profile_selector, 1)
        self.open_profile_configuration_button = QPushButton("Manage profiles")
        self.open_profile_configuration_button.setObjectName("OpenProfileConfigurationButton")
        self.open_profile_configuration_button.setToolTip(
            "Open profile setup to create, edit, or delete reusable automation inputs."
        )
        selector_row.addWidget(self.open_profile_configuration_button)
        header_layout.addLayout(selector_row, 1)
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.setObjectName("AutomationWorkspaceStack")
        automation_page = QWidget()
        automation_page.setObjectName("MainAutomationPage")
        main_layout = QVBoxLayout(automation_page)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        main_layout.addWidget(header)
        automation_menu = QFrame()
        automation_menu.setObjectName("MainAutomationMenu")
        self._automation_menu_surface = automation_menu
        automation_layout = QVBoxLayout(automation_menu)
        automation_layout.setContentsMargins(16, 16, 16, 14)
        automation_layout.setSpacing(12)
        automation_content = QHBoxLayout()
        automation_content.setSpacing(12)
        build_automatic_run_workspace(self, automation_content, automation_layout)
        run_bar = QFrame()
        run_bar.setObjectName("RunStatusBar")
        run_row = QHBoxLayout(run_bar)
        run_row.setContentsMargins(12, 10, 12, 10)
        run_row.setSpacing(10)
        self.run_readiness_label = QLabel("●  Ready")
        self.run_readiness_label.setObjectName("RunReadinessBadge")
        self.run_readiness_label.setProperty("readinessState", "ready")
        self.run_readiness_label.setAccessibleName("Run status")
        run_row.addWidget(self.run_readiness_label)
        run_row.addStretch(1)
        self.open_pipeline_output_button = QPushButton("Open outputs")
        self.open_pipeline_output_button.setObjectName("OpenPipelineOutputButton")
        self.open_pipeline_output_button.setToolTip(str(self._automated_output_root))
        run_row.addWidget(self.open_pipeline_output_button)
        self.run_pipeline_button = QPushButton("Run pipeline")
        self.run_pipeline_button.setObjectName("RunPipelineButton")
        self.run_pipeline_button.setEnabled(True)
        self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
        run_row.addWidget(self.run_pipeline_button)
        automation_layout.addWidget(run_bar)
        self.run_status_bar = run_bar
        main_layout.addWidget(automation_menu, 1)
        self.workspace_stack.addWidget(automation_page)
        self.automation_page = automation_page
        build_automatic_profile_editor(self)
        root.addWidget(self.workspace_stack, 1)
        self.profile_models._render_model_rows()

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        return label

    @staticmethod
    def _path_label() -> QLabel:
        label = QLabel("Not selected")
        label.setObjectName("AssetPath")
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _stage_page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("ProfileStagePage")
        content = QVBoxLayout(page)
        content.setContentsMargins(14, 12, 14, 12)
        content.setSpacing(6)
        return (page, content)

    def _build_pipeline_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PipelineStatusPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(4)
        header = QHBoxLayout()
        title = QLabel("Progress")
        title.setObjectName("AutomationPanelTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.pipeline_video_progress_label = QLabel("0 / 0 videos processed")
        self.pipeline_video_progress_label.setObjectName("PipelineVideoProgress")
        header.addWidget(self.pipeline_video_progress_label)
        layout.addLayout(header)
        stage_row = QHBoxLayout()
        stage_row.setSpacing(6)
        self.pipeline_stage_cards: list[QFrame] = []
        self.pipeline_stage_status_labels: list[QLabel] = []
        self.pipeline_stage_review_labels: list[QLabel] = []
        self.pipeline_stage_progress_bars: list[CircularProgressIndicator] = []
        for index, stage_title in enumerate(PIPELINE_STAGE_LABELS):
            if index:
                connector = QFrame()
                connector.setObjectName("PipelineConnector")
                connector.setFixedHeight(1)
                connector.setMinimumWidth(6)
                connector.setMaximumWidth(10)
                stage_row.addWidget(connector, 0, Qt.AlignVCenter)
            card = QFrame()
            card.setObjectName("PipelineStageCard")
            card.setProperty("pipelineState", "pending")
            card.setFixedHeight(128)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 8, 6, 7)
            card_layout.setSpacing(4)
            stage_progress = CircularProgressIndicator(accent_role="primary")
            stage_progress.setObjectName("PipelineStageProgress")
            stage_progress.setRange(0, 100)
            stage_progress.setValue(0)
            stage_progress.setTextVisible(False)
            stage_progress.set_center_text(str(index + 1))
            stage_progress.setFixedSize(44, 44)
            card_layout.addWidget(stage_progress, 0, Qt.AlignHCenter)
            name = QLabel(stage_title)
            name.setObjectName("PipelineStageName")
            name.setAlignment(Qt.AlignCenter)
            name.setWordWrap(True)
            card_layout.addWidget(name, 1)
            review_indicator = QLabel("")
            review_indicator.setObjectName("PipelineReviewIndicator")
            review_indicator.hide()
            status = QLabel("Waiting")
            status.setObjectName("PipelineStageStatus")
            status.setAlignment(Qt.AlignCenter)
            status.setWordWrap(True)
            card_layout.addWidget(status)
            stage_row.addWidget(card, 1, Qt.AlignVCenter)
            self.pipeline_stage_cards.append(card)
            self.pipeline_stage_status_labels.append(status)
            self.pipeline_stage_review_labels.append(review_indicator)
            self.pipeline_stage_progress_bars.append(stage_progress)
        layout.addLayout(stage_row)
        self.pipeline_activity_panel = QFrame()
        self.pipeline_activity_panel.setObjectName("PipelineActivityPanel")
        activity_layout = QVBoxLayout(self.pipeline_activity_panel)
        activity_layout.setContentsMargins(0, 16, 0, 0)
        activity_layout.setSpacing(10)
        self.pipeline_current_stage_label = QLabel("Overall progress")
        self.pipeline_current_stage_label.setObjectName("PipelineCurrentStage")
        activity_layout.addWidget(self.pipeline_current_stage_label)
        self.pipeline_progress_bar = DynamicProgressBar(accent_role="primary")
        self.pipeline_progress_bar.setObjectName("PipelineProgressBar")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(0)
        self.pipeline_progress_bar.setTextVisible(True)
        activity_layout.addWidget(self.pipeline_progress_bar)
        activity_layout.addStretch(1)
        layout.addWidget(self.pipeline_activity_panel, 1)
        build_automatic_review_view(self, layout)
        return panel

    def _connect_signals(self) -> None:
        self.profile_selector.currentIndexChanged.connect(self.profiles._profile_selection_changed)
        self.configuration_profile_selector.currentIndexChanged.connect(
            self.profiles._configuration_profile_selection_changed
        )
        self.new_profile_button.clicked.connect(self.profiles._new_profile)
        self.duplicate_profile_button.clicked.connect(self.profiles._duplicate_profile)
        self.delete_profile_button.clicked.connect(self.profiles._delete_profile)
        self.open_profile_configuration_button.clicked.connect(self.profiles._show_profile_configuration)
        self.back_to_automation_button.clicked.connect(self.profiles._show_automation_menu)
        self.open_video_settings_button.clicked.connect(
            lambda _checked=False: self.manual_tool_requested.emit("video_processing")
        )
        self.open_calibration_settings_button.clicked.connect(
            lambda _checked=False: self.manual_tool_requested.emit("manual_calibration")
        )
        self.open_gait_settings_button.clicked.connect(
            lambda _checked=False: self.manual_tool_requested.emit("gait_parameter_analysis")
        )
        self.open_knee_settings_button.clicked.connect(
            lambda _checked=False: self.manual_tool_requested.emit("knee_correction")
        )
        self.manifest_upload_button.clicked.connect(self.profile_assets._choose_processing_manifest)
        self.calibration_upload_button.clicked.connect(self.profile_assets._choose_calibration_map)
        self.analysis_manifest_upload_button.clicked.connect(self.profile_assets._choose_analysis_manifest)
        self.knee_manifest_upload_button.clicked.connect(self.profile_assets._choose_knee_manifest)
        self.include_gait_analysis_button.toggled.connect(self.profile_assets._profile_stage_options_changed)
        self.include_knee_correction_button.toggled.connect(self.profile_assets._profile_stage_options_changed)
        self.save_profile_button.clicked.connect(self.profiles._save_profile)
        self.upload_videos_button.clicked.connect(self.queue._choose_videos)
        self.remove_videos_button.clicked.connect(self.queue._remove_selected_videos)
        self.clear_videos_button.clicked.connect(self.queue._clear_videos)
        self.video_list.paths_dropped.connect(self.queue._add_video_paths)
        self.video_list.itemSelectionChanged.connect(self.queue._sync_video_actions)
        self.video_list.itemEntered.connect(self.hover._start_hover_preview)
        self.video_list.pointer_left.connect(self.hover._stop_hover_preview)
        self.video_list.itemDoubleClicked.connect(self.hover._open_large_video_preview)
        self.run_pipeline_button.clicked.connect(self.runs._toggle_pipeline_run)
        self.open_pipeline_output_button.clicked.connect(self.runs._open_pipeline_output)
        self.pipeline_approve_button.clicked.connect(self.reviews._approve_pipeline_review)
        self.pipeline_needs_changes_button.clicked.connect(self.reviews._reject_pipeline_review)
        self.pipeline_change_settings_button.clicked.connect(self.review_settings._open_pipeline_fix_settings)
        self.pipeline_review_video_list.itemDoubleClicked.connect(self.review_video._open_pipeline_review_video)
        self.pipeline_stickplot_preview.double_clicked.connect(self.review_stickplot._open_large_stickplot_preview)
        self.pipeline_stickplot_preview.clicked.connect(self.review_stickplot._open_large_stickplot_preview)

    def _apply_style(self) -> None:
        self.setStyleSheet(automated_pipeline_stylesheet())
        surface_names = {
            "ProfileHeader",
            "MainAutomationMenu",
            "ProfileConfigurationToolbar",
            "ProfileManagementPanel",
            "ProfileReadinessPanel",
        }
        for surface in (frame for frame in self.findChildren(QFrame) if frame.objectName() in surface_names):
            surface.setProperty("elevatedWorkspaceSurface", True)
            if surface.graphicsEffect() is not None:
                surface.setGraphicsEffect(None)
        icon_specs = (
            (self.remove_videos_button, "trash", theme.STATUS_ERROR),
            (self.clear_videos_button, "clear", theme.STATUS_ERROR),
            (self.open_profile_configuration_button, "stack", theme.PRIMARY_TEXT),
            (self.back_to_automation_button, "arrow-left", theme.TEXT),
            (self.new_profile_button, "plus", theme.PRIMARY_TEXT),
            (self.duplicate_profile_button, "copy", theme.TOOL_1),
            (self.delete_profile_button, "trash", theme.STATUS_ERROR),
            (self.open_video_settings_button, "external", theme.PRIMARY),
            (self.open_calibration_settings_button, "external", theme.PRIMARY),
            (self.open_gait_settings_button, "external", theme.PRIMARY),
            (self.open_knee_settings_button, "external", theme.PRIMARY),
            (self.manifest_upload_button, "upload", theme.PRIMARY_TEXT),
            (self.calibration_upload_button, "upload", theme.PRIMARY_TEXT),
            (self.analysis_manifest_upload_button, "upload", theme.PRIMARY_TEXT),
            (self.knee_manifest_upload_button, "upload", theme.PRIMARY_TEXT),
            (self.save_profile_button, "check", theme.PRIMARY_TEXT),
            (self.pipeline_change_settings_button, "sliders", theme.TEXT),
            (self.open_pipeline_output_button, "folder", theme.TEXT),
            (self.run_pipeline_button, "play", theme.PRIMARY_TEXT),
        )
        for button, icon_name, color in icon_specs:
            button.setIcon(interface_icon(icon_name, color))
            button.setIconSize(QSize(16, 16))

    def create_profile_from_manual_presets(
        self,
        name: str,
        *,
        processing_manifest: Path | None = None,
        calibration_map: Path | None = None,
        analysis_manifest: Path | None = None,
        knee_manifest: Path | None = None,
    ) -> AutomatedPipelineProfile:
        """Save a named profile containing every available manual-workspace preset."""
        profile = self.profile_use_cases.save(
            name,
            processing_manifest,
            calibration_map,
            {},
            analysis_manifest=analysis_manifest,
            knee_manifest=knee_manifest,
            gait_analysis_enabled=analysis_manifest is not None,
            knee_correction_enabled=knee_manifest is not None,
            allow_incomplete=True,
        )
        self.profiles._refresh_profiles(profile.id)
        self.profiles._show_profile_configuration()
        self.status_label.setText(f'Profile "{profile.name}" created from the available manual settings.')
        return profile

    def set_pipeline_running(self, running: bool) -> None:
        """Swap the video queue for pipeline progress without starting any work."""
        was_running = self._pipeline_running
        self._pipeline_running = running
        if running:
            self.runs._set_run_readiness("Running", "running")
            self.stage_progress._set_pipeline_overview_compact(True)
            self.hover._stop_hover_preview()
            self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
            if self._pipeline_demo_waiting_for_review is None:
                self.pipeline_activity_panel.show()
            self.pipeline_progress_bar.set_accent_role("running")
            self.pipeline_progress_bar.set_active(True)
            if not was_running:
                total = len(self._video_paths)
                self.set_pipeline_stage(
                    0, progress=0, processed_videos=0, total_videos=total, status_text="Preparing videos"
                )
        else:
            self._pipeline_skipped_stages.clear()
            self.stage_progress._emphasize_pipeline_stage(None)
            self.stage_progress._set_pipeline_overview_compact(False)
            self.automation_input_stack.setCurrentWidget(self.video_panel)
            self.pipeline_progress_bar.set_active(False)
            self.run_log._set_pipeline_log_state("Ready", "ready")
            self.runs._set_run_readiness("Ready", "ready")

    def set_pipeline_stage(
        self,
        stage_index: int,
        *,
        progress: float | None = None,
        processed_videos: int | None = None,
        total_videos: int | None = None,
        status_text: str | None = None,
    ) -> None:
        """Update the ordered progress view for a future pipeline controller."""
        if not 0 <= stage_index < len(PIPELINE_STAGES):
            raise ValueError(f"Pipeline stage index must be between 0 and {len(PIPELINE_STAGES) - 1}.")
        self._pipeline_running = True
        self.stage_progress._set_pipeline_overview_compact(True)
        if self._pipeline_demo_waiting_for_review is None:
            self.pipeline_review_panel.hide()
            self.pipeline_activity_panel.show()
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        self.run_log._set_pipeline_log_state("Running", "running")
        active_status = status_text or "In progress"
        stage_progress = None if progress is None else max(0.0, min(100.0, float(progress)))
        for index, (card, label, review_label) in enumerate(
            zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_status_labels,
                self.pipeline_stage_review_labels,
                strict=True,
            )
        ):
            if index < stage_index and index in self._pipeline_skipped_stages:
                (state, text) = ("skipped", "Skipped")
                self.stage_progress._set_pipeline_stage_progress(index, 0, False, "primary", indicator_state="skipped")
            elif index < stage_index:
                (state, text) = ("complete", "Complete")
                self.stage_progress._set_pipeline_stage_progress(index, 100, False, "ready", indicator_state="complete")
            elif index == stage_index:
                text = active_status
                if stage_progress is not None:
                    text = f"{active_status} {stage_progress:g}%"
                state = "active"
                self.stage_progress._set_pipeline_stage_progress(
                    index, stage_progress, True, "running", indicator_state="active"
                )
            else:
                (state, text) = ("pending", "Waiting")
                self.stage_progress._set_pipeline_stage_progress(index, 0, False, "primary", indicator_state="pending")
            card.setProperty("pipelineState", state)
            label.setText(text)
            if index in PIPELINE_REVIEW_GATES:
                if index in self._pipeline_skipped_stages:
                    review_label.setText("Not included")
                else:
                    review_label.setText("Reviewed" if index < stage_index else "Review required")
            card.style().unpolish(card)
            card.style().polish(card)
        self.stage_progress._emphasize_pipeline_stage(stage_index)
        if processed_videos is not None or total_videos is not None:
            processed = max(0, processed_videos or 0)
            total = max(0, total_videos or 0)
            self.pipeline_video_progress_label.setText(f"{processed} / {total} videos processed")
        if progress is None:
            self.pipeline_progress_bar.set_accent_role("running")
            self.pipeline_progress_bar.setRange(0, 0)
            self.pipeline_progress_bar.set_active(True)
            self.pipeline_progress_bar.setFormat("Working")
            return
        overall = round((stage_index + stage_progress / 100.0) / len(PIPELINE_STAGES) * 100)
        self.pipeline_progress_bar.set_accent_role("running")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(overall)
        self.pipeline_progress_bar.set_active(True)
        self.pipeline_progress_bar.setFormat("%p%")

    def complete_pipeline(self, status_text: str = "Pipeline complete") -> None:
        self._pipeline_running = False
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        self.pipeline_review_panel.hide()
        self.pipeline_activity_panel.show()
        for index, (card, label, review_label) in enumerate(
            zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_status_labels,
                self.pipeline_stage_review_labels,
                strict=True,
            )
        ):
            skipped = index in self._pipeline_skipped_stages
            card.setProperty("pipelineState", "skipped" if skipped else "complete")
            label.setText("Skipped" if skipped else "Complete")
            if review_label.text():
                review_label.setText("Not included" if skipped else "Reviewed")
            self.stage_progress._set_pipeline_stage_progress(
                index,
                0 if skipped else 100,
                False,
                "primary" if skipped else "ready",
                indicator_state="skipped" if skipped else "complete",
            )
            card.style().unpolish(card)
            card.style().polish(card)
        self.stage_progress._emphasize_pipeline_stage(None)
        self.pipeline_progress_bar.set_accent_role("ready")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(100)
        self.pipeline_progress_bar.set_active(False)
        self.pipeline_progress_bar.setFormat("%p%")
        self.run_log._set_pipeline_log_state("Complete", "complete")

    def closeEvent(self, event) -> None:
        self._pipeline_demo_timer.stop()
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.request_cancel()
            self._pipeline_worker.wait()
        self.hover._release_hover_capture()
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        if self._large_review_dialog is not None:
            self._large_review_dialog.close()
        super().closeEvent(event)

    def show_created_profile(self, profile):
        self.profiles._refresh_profiles(profile.id)
        self.profiles._show_profile_configuration()
        self.status_label.setText(f'Profile "{profile.name}" created from the available manual settings.')
