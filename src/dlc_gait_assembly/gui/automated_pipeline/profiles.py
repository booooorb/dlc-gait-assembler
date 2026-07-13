from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.shared.progress import CircularProgressIndicator, DynamicProgressBar
from dlc_gait_assembly.services.analysis_manifests import (
    read_analysis_manifest,
    read_knee_analysis_manifest,
)
from dlc_gait_assembly.services.domain.videos import VIDEO_EXTENSIONS
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedPipelineProfile,
    AutomatedProfileStore,
    regions_from_processing_manifest,
)
from dlc_gait_assembly.services.project_paths import find_project_root

try:
    import cv2
except ImportError:
    cv2 = None


PIPELINE_STAGES = (
    "Video processing",
    "DLC analyzing videos",
    "Triangulate knee coordinate",
    "Stickplot generation",
    "Gait analysis",
)
PIPELINE_STAGE_LABELS = (
    "Process videos",
    "DLC analysis",
    "Triangulate knee",
    "Make stickplot",
    "Gait analysis",
)
PIPELINE_PREVIEW_MESSAGES = (
    "Preparing and processing source videos",
    "Running DeepLabCut pose estimation",
    "Triangulating the knee coordinate",
    "Generating gait stickplots",
    "Running gait analysis",
)
PIPELINE_STAGE_ACTIVITY = (
    "Processing",
    "Analyzing poses",
    "Triangulating knee",
    "Generating",
    "Analyzing gait",
)
RUN_PREVIEW_TOOLTIP = (
    "Start a visual walkthrough of every pipeline stage and review checkpoint. "
    "Preview mode does not process videos or change files."
)
STOP_PREVIEW_TOOLTIP = (
    "Stop the pipeline walkthrough and return to the video queue. No files have been changed."
)
PIPELINE_REVIEW_GATES = {
    0: {
        "title": "Confirm processed video regions",
        "description": "Check that every cropped region is correct before pose analysis continues. Double-click a video for a large preview.",
        "preview": "Processed region-video previews appear here.",
        "setting": "video processing manifest",
        "tab": 0,
        "replay_stage": 0,
    },
    2: {
        "title": "Confirm DeepLabCut analyzed videos",
        "description": "Check the tracking overlays and confirm that each region used the correct model. Double-click a video for a large preview.",
        "preview": "DeepLabCut overlay-video previews appear here.",
        "setting": "region model configuration",
        "tab": 1,
        "replay_stage": 1,
    },
    3: {
        "title": "Confirm generated stickplot",
        "description": "Check the generated stickplot before the final gait analysis runs. Double-click the stickplot for a large view.",
        "preview": "The generated stickplot preview appears here.",
        "setting": "gait analysis manifest",
        "tab": 2,
        "replay_stage": 3,
    },
}


class AutomatedPipelineProfilesWidget(QWidget):
    """Switchable automation workspace and profile-configuration workspace."""

    workspace_changed = Signal(str)

    def __init__(self, store: AutomatedProfileStore | None = None):
        super().__init__()
        self.setObjectName("AutomatedPipelineProfilesWidget")
        project_root = find_project_root(Path.cwd())
        self._store = store or AutomatedProfileStore(project_root / "outputs" / "automated_profiles")
        self._profiles: dict[str, AutomatedPipelineProfile] = {}
        self._current_profile_id: str | None = None
        self._manifest_source: Path | None = None
        self._calibration_source: Path | None = None
        self._analysis_manifest_source: Path | None = None
        self._knee_manifest_source: Path | None = None
        self._regions: tuple[str, ...] = ()
        self._model_sources: dict[str, Path | None] = {}
        self._video_paths: list[Path] = []
        self._large_preview_dialog: AutomationVideoPreviewDialog | None = None
        self._large_review_dialog: QDialog | None = None
        self._hover_capture = None
        self._hover_preview_path: Path | None = None
        self._hover_preview_timer = QTimer(self)
        self._hover_preview_timer.timeout.connect(self._advance_hover_preview)
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
        self._pipeline_demo_timer.timeout.connect(self._advance_pipeline_demo)
        self._saved_snapshot: tuple[str, ...] | None = None
        self._build_ui()
        self._connect_signals()
        self._refresh_profiles()
        self._apply_style()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QFrame()
        header.setObjectName("ProfileHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(8)
        title = QLabel("Automated pipeline")
        title.setObjectName("AutomatedProfileTitle")
        header_layout.addWidget(title)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        selector_row.addWidget(self._field_label("Profile"))
        self.profile_selector = QComboBox()
        self.profile_selector.setObjectName("ProfileSelector")
        self.profile_selector.setAccessibleName("Saved automated pipeline profile")
        self.profile_selector.setToolTip(
            "Choose the saved setup this run will use. A profile contains the video "
            "processing manifest, region-specific DeepLabCut models, calibration map, "
            "gait-analysis manifest, and optional knee-analysis manifest."
        )
        selector_row.addWidget(self.profile_selector, 1)
        self.duplicate_profile_button = QPushButton("Duplicate")
        self.duplicate_profile_button.setObjectName("SmallProfileButton")
        self.duplicate_profile_button.setToolTip(
            "Copy the selected profile under a new name. The original profile and all "
            "of its saved input files remain unchanged."
        )
        selector_row.addWidget(self.duplicate_profile_button)
        self.open_profile_configuration_button = QPushButton("Manage profiles")
        self.open_profile_configuration_button.setObjectName("OpenProfileConfigurationButton")
        self.open_profile_configuration_button.setToolTip(
            "Open profile setup to create, edit, or delete reusable automation inputs."
        )
        selector_row.addWidget(self.open_profile_configuration_button)
        header_layout.addLayout(selector_row)

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
        automation_layout = QVBoxLayout(automation_menu)
        automation_layout.setContentsMargins(16, 12, 16, 12)
        automation_layout.setSpacing(8)
        automation_content = QHBoxLayout()
        automation_content.setSpacing(10)
        video_panel = QFrame()
        video_panel.setObjectName("VideoDropPanel")
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(10, 8, 10, 10)
        video_layout.setSpacing(6)
        video_toolbar = QHBoxLayout()
        videos_title = QLabel("Videos")
        videos_title.setObjectName("AutomationPanelTitle")
        video_toolbar.addWidget(videos_title)
        self.video_count_label = QLabel("0 videos")
        self.video_count_label.setObjectName("VideoCountLabel")
        video_toolbar.addWidget(self.video_count_label)
        video_toolbar.addStretch(1)
        self.upload_videos_button = QPushButton("Upload videos")
        self.upload_videos_button.setToolTip(
            "Add one or more source videos to the queue. Supported video files can also "
            "be dragged into the list below; adding a video does not modify it."
        )
        video_toolbar.addWidget(self.upload_videos_button)
        self.remove_videos_button = QPushButton("Remove")
        self.remove_videos_button.setObjectName("RemoveButton")
        self.remove_videos_button.setToolTip(
            "Remove the selected videos from this queue. Files on disk are not deleted."
        )
        video_toolbar.addWidget(self.remove_videos_button)
        self.clear_videos_button = QPushButton("Clear")
        self.clear_videos_button.setObjectName("ClearButton")
        self.clear_videos_button.setToolTip(
            "Remove every video from this queue. Files on disk are not deleted."
        )
        video_toolbar.addWidget(self.clear_videos_button)
        video_layout.addLayout(video_toolbar)
        self.video_list = VideoDropList()
        self.video_list.setObjectName("AutomationVideoDropList")
        self.video_list.setAccessibleDescription(
            "Hover over a video to play a preview. Double-click to open the expanded preview."
        )
        self.video_list.setToolTip(
            "Queued source videos. Hover over a row for a quick preview, double-click it "
            "for a larger viewer, or select rows before choosing Remove."
        )
        self.video_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.video_list.setMinimumHeight(310)
        video_layout.addWidget(self.video_list, 1)

        self.video_hover_card = QFrame(self.video_list.viewport())
        self.video_hover_card.setObjectName("VideoHoverCard")
        self.video_hover_card.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.video_hover_card.setFixedSize(276, 206)
        hover_layout = QVBoxLayout(self.video_hover_card)
        hover_layout.setContentsMargins(8, 8, 8, 8)
        hover_layout.setSpacing(5)
        self.video_hover_preview = QLabel("Loading preview…")
        self.video_hover_preview.setObjectName("VideoHoverPreview")
        self.video_hover_preview.setAlignment(Qt.AlignCenter)
        self.video_hover_preview.setFixedSize(258, 145)
        hover_layout.addWidget(self.video_hover_preview)
        self.video_hover_name = QLabel()
        self.video_hover_name.setObjectName("VideoHoverName")
        hover_layout.addWidget(self.video_hover_name)
        self.video_hover_details = QLabel("Double-click for expanded preview")
        self.video_hover_details.setObjectName("VideoHoverDetails")
        hover_layout.addWidget(self.video_hover_details)
        self.video_hover_card.hide()
        self.video_panel = video_panel
        self.pipeline_status_panel = self._build_pipeline_status_panel()
        self.automation_input_stack = QStackedWidget()
        self.automation_input_stack.setObjectName("AutomationInputStack")
        self.automation_input_stack.addWidget(self.video_panel)
        self.automation_input_stack.addWidget(self.pipeline_status_panel)
        self.automation_input_stack.setCurrentWidget(self.video_panel)
        automation_content.addWidget(self.automation_input_stack, 3)

        console_panel = QFrame()
        console_panel.setObjectName("AutomationConsolePanel")
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(10, 8, 10, 10)
        console_layout.setSpacing(6)
        console_title = QLabel("Log")
        console_title.setObjectName("AutomationPanelTitle")
        console_layout.addWidget(console_title)
        self.automation_console = QPlainTextEdit()
        self.automation_console.setObjectName("AutomationConsole")
        self.automation_console.setReadOnly(True)
        self.automation_console.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.automation_console.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.automation_console.setFont(theme.fixed_width_font())
        self.automation_console.setToolTip(
            "Read-only activity log for the current automation preview, including stage "
            "progress, review pauses, and errors."
        )
        self.automation_console.setPlainText("[Ready]")
        console_layout.addWidget(self.automation_console, 1)
        automation_content.addWidget(console_panel, 2)
        automation_layout.addLayout(automation_content, 1)

        run_row = QHBoxLayout()
        self.run_readiness_label = QLabel("Preview only")
        self.run_readiness_label.setObjectName("ProfileStatusLabel")
        run_row.addWidget(self.run_readiness_label, 1)
        self.run_pipeline_button = QPushButton("RUN pipeline")
        self.run_pipeline_button.setObjectName("RunPipelineButton")
        self.run_pipeline_button.setEnabled(True)
        self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
        run_row.addWidget(self.run_pipeline_button)
        automation_layout.addLayout(run_row)
        main_layout.addWidget(automation_menu, 1)
        self.workspace_stack.addWidget(automation_page)
        self.automation_page = automation_page

        configuration_page = QWidget()
        configuration_page.setObjectName("ProfileConfigurationPage")
        configuration_layout = QVBoxLayout(configuration_page)
        configuration_layout.setContentsMargins(0, 0, 0, 0)
        configuration_layout.setSpacing(8)

        configuration_toolbar = QFrame()
        configuration_toolbar.setObjectName("ProfileConfigurationToolbar")
        toolbar_layout = QHBoxLayout(configuration_toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        self.back_to_automation_button = QPushButton("← Back to automation")
        self.back_to_automation_button.setObjectName("BackToAutomationButton")
        self.back_to_automation_button.setToolTip(
            "Return to the video queue. Unsaved profile edits remain in this window until "
            "you close the application or select another profile."
        )
        toolbar_layout.addWidget(self.back_to_automation_button)
        configuration_title = QLabel("Manage automated profiles")
        configuration_title.setObjectName("ProfileConfigurationTitle")
        toolbar_layout.addWidget(configuration_title)
        toolbar_layout.addStretch(1)
        configuration_layout.addWidget(configuration_toolbar)

        management = QFrame()
        management.setObjectName("ProfileManagementPanel")
        management_layout = QHBoxLayout(management)
        management_layout.setContentsMargins(12, 10, 12, 10)
        management_layout.setSpacing(8)
        self.new_profile_button = QPushButton("New profile")
        self.new_profile_button.setToolTip(
            "Clear the profile form so you can build a new reusable automation setup. "
            "This does not delete existing profiles."
        )
        management_layout.addWidget(self.new_profile_button)
        management_layout.addWidget(self._field_label("Profile"))
        self.configuration_profile_selector = QComboBox()
        self.configuration_profile_selector.setObjectName("ConfigurationProfileSelector")
        self.configuration_profile_selector.setToolTip(
            "Load an existing profile into the form for inspection or editing."
        )
        management_layout.addWidget(self.configuration_profile_selector, 1)
        management_layout.addWidget(self._field_label("Name"))
        self.profile_name = QLineEdit()
        self.profile_name.setObjectName("ProfileNameInput")
        self.profile_name.setPlaceholderText("Example: Treadmill camera setup")
        self.profile_name.setToolTip(
            "Enter a recognizable name for this complete automation setup, such as the "
            "camera position, animal group, or experiment type."
        )
        management_layout.addWidget(self.profile_name, 1)
        self.delete_profile_button = QPushButton("Delete profile")
        self.delete_profile_button.setObjectName("DeleteProfileButton")
        self.delete_profile_button.setToolTip(
            "Permanently delete the selected saved profile after confirmation. Source "
            "manifests, models, and videos are not deleted."
        )
        management_layout.addWidget(self.delete_profile_button)
        configuration_layout.addWidget(management)

        self.configuration_tabs = QTabWidget()
        self.configuration_tabs.setObjectName("ProfileConfigurationTabs")
        self.configuration_tabs.setDocumentMode(True)
        self.configuration_tabs.tabBar().setExpanding(True)

        manifest_page, manifest_content = self._stage_page()
        manifest_row = QHBoxLayout()
        self.manifest_path_label = self._path_label()
        manifest_row.addWidget(self.manifest_path_label, 1)
        self.manifest_upload_button = QPushButton("Upload manifest")
        self.manifest_upload_button.setToolTip(
            "Choose a video settings or processing manifest JSON file. Its crop-region "
            "names create the model slots in step 2."
        )
        manifest_row.addWidget(self.manifest_upload_button)
        manifest_content.addLayout(manifest_row)
        self.regions_label = QLabel("No regions detected yet.")
        self.regions_label.setObjectName("DetectedRegionsLabel")
        self.regions_label.setWordWrap(True)
        manifest_content.addWidget(self.regions_label)
        manifest_content.addStretch(1)
        self.configuration_tabs.addTab(manifest_page, "1  Manifest + regions")
        self.configuration_tabs.setTabToolTip(
            0,
            "Choose the video settings or processing manifest that defines cropping, "
            "trimming, enhancement settings, and named regions.",
        )

        models_page, models_content = self._stage_page()
        self.models_container = QWidget()
        self.models_layout = QVBoxLayout(self.models_container)
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        self.models_layout.setSpacing(6)
        models_content.addWidget(self.models_container)
        models_content.addStretch(1)
        self.configuration_tabs.addTab(models_page, "2  Region models")
        self.configuration_tabs.setTabToolTip(
            1,
            "Assign one trained DeepLabCut model file or model folder to each region "
            "detected in step 1.",
        )

        calibration_page, calibration_content = self._stage_page()
        calibration_content.addWidget(self._field_label("Calibration map"))
        calibration_row = QHBoxLayout()
        self.calibration_path_label = self._path_label()
        calibration_row.addWidget(self.calibration_path_label, 1)
        self.calibration_upload_button = QPushButton("Upload calibration map")
        self.calibration_upload_button.setToolTip(
            "Choose the calibration-map JSON exported by the Calibration tool. It converts "
            "tracked image coordinates into physical measurements."
        )
        calibration_row.addWidget(self.calibration_upload_button)
        calibration_content.addLayout(calibration_row)

        calibration_content.addSpacing(10)
        calibration_content.addWidget(self._field_label("Gait analysis manifest"))
        analysis_row = QHBoxLayout()
        self.analysis_manifest_path_label = self._path_label()
        analysis_row.addWidget(self.analysis_manifest_path_label, 1)
        self.analysis_manifest_upload_button = QPushButton("Upload analysis manifest")
        self.analysis_manifest_upload_button.setToolTip(
            "Choose the gait-analysis manifest exported by the Gait tool. It stores the "
            "analysis settings that will be reused for this profile."
        )
        analysis_row.addWidget(self.analysis_manifest_upload_button)
        calibration_content.addLayout(analysis_row)

        calibration_content.addSpacing(10)
        calibration_content.addWidget(self._field_label("Knee analysis manifest"))
        knee_row = QHBoxLayout()
        self.knee_manifest_path_label = self._path_label()
        knee_row.addWidget(self.knee_manifest_path_label, 1)
        self.knee_manifest_upload_button = QPushButton("Upload knee manifest")
        self.knee_manifest_upload_button.setToolTip(
            "Choose the knee-analysis manifest exported by the Knee tool. It stores "
            "the knee lengths, label choices, confidence cutoff, and correction direction."
        )
        knee_row.addWidget(self.knee_manifest_upload_button)
        calibration_content.addLayout(knee_row)
        calibration_content.addStretch(1)
        self.configuration_tabs.addTab(calibration_page, "3  Gait analysis")
        self.configuration_tabs.setTabToolTip(
            2,
            "Choose the calibration map plus gait and knee manifests produced by the manual tools.",
        )

        save_page, save_content = self._stage_page()
        save_row = QHBoxLayout()
        self.status_label = QLabel("Start with the video processing manifest in step 1.")
        self.status_label.setObjectName("ProfileStatusLabel")
        self.status_label.setWordWrap(True)
        save_row.addWidget(self.status_label, 1)
        self.save_profile_button = QPushButton("Save new profile")
        self.save_profile_button.setObjectName("PrimaryButton")
        self.save_profile_button.setToolTip(
            "Validate the required inputs and save them together as a reusable profile. "
            "Saving a profile does not start the pipeline."
        )
        save_row.addWidget(self.save_profile_button)
        save_content.addLayout(save_row)
        save_content.addStretch(1)
        self.configuration_tabs.addTab(save_page, "4  Review + save")
        self.configuration_tabs.setTabToolTip(
            3,
            "Check validation messages, then save the complete setup for future runs.",
        )
        self.configuration_tabs.setMinimumHeight(320)
        configuration_layout.addWidget(self.configuration_tabs)
        self.workspace_stack.addWidget(configuration_page)
        self.configuration_page = configuration_page
        root.addWidget(self.workspace_stack, 1)
        self._render_model_rows()

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
        return page, content

    def _build_pipeline_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PipelineStatusPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Automated pipeline progress")
        title.setObjectName("AutomationPanelTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.pipeline_video_progress_label = QLabel("0 / 0 videos processed")
        self.pipeline_video_progress_label.setObjectName("PipelineVideoProgress")
        header.addWidget(self.pipeline_video_progress_label)
        layout.addLayout(header)

        stage_row = QHBoxLayout()
        stage_row.setSpacing(5)
        self.pipeline_stage_cards: list[QFrame] = []
        self.pipeline_stage_status_labels: list[QLabel] = []
        self.pipeline_stage_review_labels: list[QLabel] = []
        self.pipeline_stage_progress_bars: list[CircularProgressIndicator] = []
        for index, stage_title in enumerate(PIPELINE_STAGE_LABELS):
            if index:
                connector = QLabel("→")
                connector.setObjectName("PipelineConnector")
                connector.setAlignment(Qt.AlignCenter)
                stage_row.addWidget(connector)
            card = QFrame()
            card.setObjectName("PipelineStageCard")
            card.setProperty("pipelineState", "pending")
            card.setFixedHeight(116)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(4, 5, 4, 5)
            card_layout.setSpacing(2)
            stage_progress = CircularProgressIndicator(accent_role="primary")
            stage_progress.setObjectName("PipelineStageProgress")
            stage_progress.setRange(0, 100)
            stage_progress.setValue(0)
            stage_progress.setTextVisible(False)
            stage_progress.set_center_text(str(index + 1))
            stage_progress.setFixedSize(52, 52)
            card_layout.addWidget(stage_progress, 0, Qt.AlignHCenter)
            name = QLabel(stage_title)
            name.setObjectName("PipelineStageName")
            name.setAlignment(Qt.AlignCenter)
            name.setWordWrap(True)
            card_layout.addWidget(name, 1)
            review_indicator = QLabel(
                "Review required" if index in PIPELINE_REVIEW_GATES else ""
            )
            review_indicator.setObjectName("PipelineReviewIndicator")
            review_indicator.setAlignment(Qt.AlignCenter)
            review_indicator.setVisible(index in PIPELINE_REVIEW_GATES)
            card_layout.addWidget(review_indicator)
            status = QLabel("Waiting")
            status.setObjectName("PipelineStageStatus")
            status.setAlignment(Qt.AlignCenter)
            status.setWordWrap(True)
            card_layout.addWidget(status)
            stage_row.addWidget(card, 1)
            self.pipeline_stage_cards.append(card)
            self.pipeline_stage_status_labels.append(status)
            self.pipeline_stage_review_labels.append(review_indicator)
            self.pipeline_stage_progress_bars.append(stage_progress)
        layout.addLayout(stage_row)

        self.pipeline_current_stage_label = QLabel("Waiting to start")
        self.pipeline_current_stage_label.setObjectName("PipelineCurrentStage")
        layout.addWidget(self.pipeline_current_stage_label)
        self.pipeline_progress_bar = DynamicProgressBar(accent_role="primary")
        self.pipeline_progress_bar.setObjectName("PipelineProgressBar")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(0)
        self.pipeline_progress_bar.setTextVisible(True)
        layout.addWidget(self.pipeline_progress_bar)
        self.pipeline_progress_detail = QLabel(
            "Stages run in order; inspection stages pause for review."
        )
        self.pipeline_progress_detail.setObjectName("PipelineProgressDetail")
        layout.addWidget(self.pipeline_progress_detail)

        self.pipeline_review_panel = QFrame()
        self.pipeline_review_panel.setObjectName("PipelineReviewPanel")
        review_layout = QHBoxLayout(self.pipeline_review_panel)
        review_layout.setContentsMargins(6, 6, 6, 6)
        review_layout.setSpacing(6)
        self.pipeline_review_preview_stack = QStackedWidget()
        self.pipeline_review_preview_stack.setObjectName("PipelineReviewPreviewStack")
        self.pipeline_review_preview_stack.setMinimumSize(240, 78)
        self.pipeline_review_video_list = QListWidget()
        self.pipeline_review_video_list.setObjectName("PipelineReviewVideoList")
        self.pipeline_review_video_list.setToolTip(
            "Review the generated preview for each queued video. Double-click a row to "
            "open a larger viewer before accepting or rejecting this checkpoint."
        )
        self.pipeline_review_video_list.setWordWrap(False)
        self.pipeline_review_video_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.pipeline_review_preview_stack.addWidget(self.pipeline_review_video_list)
        self.pipeline_component_tabs = QTabWidget()
        self.pipeline_component_tabs.setObjectName("PipelineComponentTabs")
        self.pipeline_component_tabs.setDocumentMode(True)
        self.pipeline_component_tabs.tabBar().setExpanding(True)
        self.pipeline_component_tabs.setToolTip(
            "Switch between region outputs to verify that each one used the correct model."
        )
        self.pipeline_review_preview_stack.addWidget(self.pipeline_component_tabs)
        self.pipeline_component_video_lists: dict[str, QListWidget] = {}
        self.pipeline_stickplot_preview = DoubleClickLabel()
        self.pipeline_stickplot_preview.setObjectName("PipelineStickplotPreview")
        self.pipeline_stickplot_preview.setAlignment(Qt.AlignCenter)
        self.pipeline_stickplot_preview.setScaledContents(True)
        self.pipeline_review_preview_stack.addWidget(self.pipeline_stickplot_preview)
        review_layout.addWidget(self.pipeline_review_preview_stack, 1)
        review_copy = QVBoxLayout()
        self.pipeline_review_title = QLabel()
        self.pipeline_review_title.setObjectName("PipelineReviewTitle")
        review_copy.addWidget(self.pipeline_review_title)
        self.pipeline_review_description = QLabel()
        self.pipeline_review_description.setObjectName("PipelineReviewDescription")
        self.pipeline_review_description.setWordWrap(True)
        review_copy.addWidget(self.pipeline_review_description)
        review_copy.addStretch(1)
        review_buttons = QHBoxLayout()
        self.pipeline_change_settings_button = QPushButton("Change configuration")
        self.pipeline_change_settings_button.setObjectName("PipelineChangeSettingsButton")
        self.pipeline_change_settings_button.setToolTip(
            "Open the profile setting responsible for this rejected preview. After fixing "
            "it, return here and resume the walkthrough."
        )
        self.pipeline_needs_changes_button = QPushButton("Needs changes")
        self.pipeline_needs_changes_button.setObjectName("RemoveButton")
        self.pipeline_needs_changes_button.setToolTip(
            "Reject this checkpoint and pause the pipeline so its profile settings can be corrected."
        )
        self.pipeline_approve_button = QPushButton("Confirm and continue")
        self.pipeline_approve_button.setObjectName("PrimaryButton")
        self.pipeline_approve_button.setToolTip(
            "Accept this preview as correct and continue to the next pipeline stage."
        )
        review_buttons.addWidget(self.pipeline_change_settings_button)
        review_buttons.addStretch(1)
        review_buttons.addWidget(self.pipeline_needs_changes_button)
        review_buttons.addWidget(self.pipeline_approve_button)
        review_copy.addLayout(review_buttons)
        review_layout.addLayout(review_copy, 2)
        self.pipeline_review_panel.hide()
        layout.addWidget(self.pipeline_review_panel)
        layout.addStretch(1)
        return panel

    def _connect_signals(self) -> None:
        self.profile_selector.currentIndexChanged.connect(self._profile_selection_changed)
        self.configuration_profile_selector.currentIndexChanged.connect(
            self._configuration_profile_selection_changed
        )
        self.new_profile_button.clicked.connect(self._new_profile)
        self.duplicate_profile_button.clicked.connect(self._duplicate_profile)
        self.delete_profile_button.clicked.connect(self._delete_profile)
        self.open_profile_configuration_button.clicked.connect(self._show_profile_configuration)
        self.back_to_automation_button.clicked.connect(self._show_automation_menu)
        self.manifest_upload_button.clicked.connect(self._choose_processing_manifest)
        self.calibration_upload_button.clicked.connect(self._choose_calibration_map)
        self.analysis_manifest_upload_button.clicked.connect(self._choose_analysis_manifest)
        self.knee_manifest_upload_button.clicked.connect(self._choose_knee_manifest)
        self.save_profile_button.clicked.connect(self._save_profile)
        self.upload_videos_button.clicked.connect(self._choose_videos)
        self.remove_videos_button.clicked.connect(self._remove_selected_videos)
        self.clear_videos_button.clicked.connect(self._clear_videos)
        self.video_list.paths_dropped.connect(self._add_video_paths)
        self.video_list.itemEntered.connect(self._start_hover_preview)
        self.video_list.pointer_left.connect(self._stop_hover_preview)
        self.video_list.itemDoubleClicked.connect(self._open_large_video_preview)
        self.run_pipeline_button.clicked.connect(self._toggle_pipeline_demo)
        self.pipeline_approve_button.clicked.connect(self._approve_pipeline_review)
        self.pipeline_needs_changes_button.clicked.connect(self._reject_pipeline_review)
        self.pipeline_change_settings_button.clicked.connect(self._open_pipeline_fix_settings)
        self.pipeline_review_video_list.itemDoubleClicked.connect(
            self._open_pipeline_review_video
        )
        self.pipeline_stickplot_preview.double_clicked.connect(
            self._open_large_stickplot_preview
        )

    def _refresh_profiles(self, selected_id: str | None = None) -> None:
        profiles = self._store.list_profiles()
        self._profiles = {profile.id: profile for profile in profiles}
        selectors = (self.profile_selector, self.configuration_profile_selector)
        blockers = [QSignalBlocker(selector) for selector in selectors]
        for selector in selectors:
            selector.clear()
        if not profiles:
            for selector in selectors:
                selector.addItem("No saved profiles", None)
                selector.setEnabled(False)
            self.duplicate_profile_button.setEnabled(False)
            del blockers
            self._show_new_profile()
            return
        for selector in selectors:
            selector.setEnabled(True)
            for profile in profiles:
                selector.addItem(profile.name, profile.id)
        profile_ids = [profile.id for profile in profiles]
        selected_id = selected_id if selected_id in profile_ids else profile_ids[0]
        for selector in selectors:
            selector.setCurrentIndex(profile_ids.index(selected_id))
        del blockers
        self._load_profile(self._profiles[selected_id])

    def _profile_selection_changed(self, index: int) -> None:
        self._profile_id_selected(self.profile_selector.itemData(index))

    def _configuration_profile_selection_changed(self, index: int) -> None:
        self._profile_id_selected(self.configuration_profile_selector.itemData(index))

    def _profile_id_selected(self, profile_id: str | None) -> None:
        if not profile_id or profile_id == self._current_profile_id:
            return
        if not self._confirm_discard_changes():
            self._select_combo_id(self._current_profile_id)
            return
        self._load_profile(self._profiles[profile_id])
        self._select_combo_id(profile_id)

    def _new_profile(self) -> None:
        if not self._confirm_discard_changes():
            return
        self._select_combo_id(None)
        self._show_new_profile()
        self.profile_name.setFocus()

    def _duplicate_profile(self) -> None:
        if self._current_profile_id is None or not self._confirm_discard_changes():
            return
        source = self._store.load(self._current_profile_id)
        duplicate_name, accepted = QInputDialog.getText(
            self,
            "Duplicate profile",
            "Name for the duplicated profile:",
            QLineEdit.Normal,
            f"{source.name} copy",
        )
        duplicate_name = duplicate_name.strip()
        if not accepted or not duplicate_name:
            return
        try:
            duplicate = self._store.save(
                duplicate_name,
                source.processing_manifest,
                source.calibration_map,
                source.deeplabcut_models,
                analysis_manifest=source.analysis_manifest,
                knee_manifest=source.knee_manifest,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not duplicate profile", str(exc))
            return
        self._refresh_profiles(duplicate.id)
        self.status_label.setText(f'Profile duplicated as "{duplicate.name}".')

    def _show_profile_configuration(self) -> None:
        self.workspace_stack.setCurrentWidget(self.configuration_page)
        self.workspace_changed.emit("profiles")

    def _show_automation_menu(self) -> None:
        self.workspace_stack.setCurrentWidget(self.automation_page)
        self.workspace_changed.emit("run")

    def _show_new_profile(self) -> None:
        self._current_profile_id = None
        self.profile_name.clear()
        self._manifest_source = None
        self._calibration_source = None
        self._analysis_manifest_source = None
        self._knee_manifest_source = None
        self._regions = ()
        self._model_sources = {}
        self._saved_snapshot = None
        self._refresh_paths()
        self._render_model_rows()
        self.delete_profile_button.setEnabled(False)
        self.duplicate_profile_button.setEnabled(False)
        self.save_profile_button.setText("Save new profile")
        self.status_label.setText("Start with the video processing manifest in step 1.")

    def _load_profile(self, profile: AutomatedPipelineProfile) -> None:
        self._current_profile_id = profile.id
        self.profile_name.setText(profile.name)
        self._manifest_source = profile.processing_manifest
        self._calibration_source = profile.calibration_map
        self._analysis_manifest_source = profile.analysis_manifest
        self._knee_manifest_source = profile.knee_manifest
        self._regions = regions_from_processing_manifest(profile.processing_manifest)
        self._model_sources = {region: profile.deeplabcut_models.get(region) for region in self._regions}
        self._refresh_paths()
        self._render_model_rows()
        self._saved_snapshot = self._snapshot()
        self.delete_profile_button.setEnabled(True)
        self.duplicate_profile_button.setEnabled(True)
        self.save_profile_button.setText("Save changes")
        self.status_label.setText(f'Profile "{profile.name}" is selected. Saving does not run the pipeline.')

    def _choose_processing_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose video settings or processing manifest",
            str(find_project_root(Path.cwd()) / "outputs" / "videos"),
            "Video manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_manifest_source(Path(path))

    def _set_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            regions = regions_from_processing_manifest(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not read regions", str(exc))
            return False
        previous_models = self._model_sources
        self._manifest_source = path
        self._regions = regions
        self._model_sources = {region: previous_models.get(region) for region in regions}
        self._refresh_paths()
        self._render_model_rows()
        self.status_label.setText(
            f"Detected {len(regions)} region(s). Upload one model per region in step 2."
        )
        return True

    def _choose_calibration_map(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose calibration map",
            str(find_project_root(Path.cwd()) / "outputs" / "calibration"),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._calibration_source = Path(path).expanduser().resolve()
            self._refresh_paths()
            self.status_label.setText("Calibration selected. Add the gait manifest and optional knee manifest below it.")

    def _choose_analysis_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose gait analysis manifest",
            str(find_project_root(Path.cwd()) / "outputs" / "gait_analysis"),
            "Analysis manifest (analysis_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_analysis_manifest_source(Path(path))

    def _set_analysis_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            read_analysis_manifest(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not read analysis manifest", str(exc))
            return False
        self._analysis_manifest_source = path
        self._refresh_paths()
        self.status_label.setText("Gait analysis settings selected. Review and save the profile.")
        return True

    def _choose_knee_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose knee analysis manifest",
            str(find_project_root(Path.cwd()) / "outputs" / "knee_correction"),
            "Knee analysis manifest (*.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._set_knee_manifest_source(Path(path))

    def _set_knee_manifest_source(self, path: Path) -> bool:
        path = path.expanduser().resolve()
        try:
            read_knee_analysis_manifest(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not read knee manifest", str(exc))
            return False
        self._knee_manifest_source = path
        self._refresh_paths()
        self.status_label.setText("Knee analysis settings selected. Review and save the profile.")
        return True

    def _choose_videos(self) -> None:
        extensions = " ".join(f"*{extension}" for extension in sorted(VIDEO_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Upload videos for automated processing",
            str(Path.home()),
            f"Video files ({extensions});;All files (*)",
        )
        self._add_video_paths([Path(path) for path in paths])

    def _add_video_paths(self, paths: object) -> None:
        added = 0
        skipped = 0
        known_paths = {str(path) for path in self._video_paths}
        for raw_path in paths if isinstance(paths, (list, tuple)) else ():
            path = Path(raw_path).expanduser().resolve()
            key = str(path)
            if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS or key in known_paths:
                skipped += 1
                continue
            self._video_paths.append(path)
            known_paths.add(key)
            item = QListWidgetItem(path.name)
            item.setData(Qt.UserRole, key)
            self.video_list.addItem(item)
            added += 1
        self._update_video_count()
        if added and self.video_list.currentRow() < 0:
            self.video_list.setCurrentRow(0)
        if added:
            self._append_console(f"[Videos] Added {added} video(s); {len(self._video_paths)} queued.")
        if skipped:
            self._append_console(f"[Videos] Skipped {skipped} unsupported or duplicate item(s).")

    def _remove_selected_videos(self) -> None:
        selected = self.video_list.selectedItems()
        if not selected:
            return
        self._stop_hover_preview()
        removed_paths = {str(item.data(Qt.UserRole)) for item in selected}
        for item in selected:
            self.video_list.takeItem(self.video_list.row(item))
        self._video_paths = [path for path in self._video_paths if str(path) not in removed_paths]
        self._update_video_count()
        self._append_console(f"[Videos] Removed {len(removed_paths)} video(s).")

    def _clear_videos(self) -> None:
        if not self._video_paths:
            return
        self._release_hover_capture()
        count = len(self._video_paths)
        self._video_paths.clear()
        self.video_list.clear()
        self.video_hover_card.hide()
        self._update_video_count()
        self._append_console(f"[Videos] Cleared {count} video(s).")

    def _update_video_count(self) -> None:
        count = len(self._video_paths)
        self.video_count_label.setText(f"{count} video" if count == 1 else f"{count} videos")
        self.video_list.viewport().update()

    def _append_console(self, message: str) -> None:
        self.automation_console.appendPlainText(message)

    def _toggle_pipeline_demo(self) -> None:
        if self._pipeline_demo_complete:
            self._pipeline_demo_complete = False
            self.pipeline_review_panel.hide()
            self.set_pipeline_running(False)
            self.run_pipeline_button.setText("RUN pipeline")
            self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.run_readiness_label.setText("Preview only")
            return
        if self._pipeline_demo_blocked_stage is not None:
            self._resume_pipeline_demo()
            return
        if self._pipeline_demo_waiting_for_review is not None:
            return
        if self._pipeline_demo_timer.isActive():
            self._pipeline_demo_timer.stop()
            self._pipeline_demo_waiting_for_review = None
            self._pipeline_demo_blocked_stage = None
            self.pipeline_review_panel.hide()
            self.set_pipeline_running(False)
            self.run_pipeline_button.setText("RUN pipeline")
            self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.run_readiness_label.setText("Stopped")
            self._append_console("[Preview] Stopped. No processing was performed.")
            return

        self._pipeline_demo_stage = 0
        self._pipeline_demo_progress = 0.0
        self._pipeline_demo_total_videos = len(self._video_paths) or 4
        self._pipeline_demo_last_processed = -1
        self._pipeline_demo_complete = False
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_demo_blocked_stage = None
        self.pipeline_review_panel.hide()
        self.set_pipeline_running(True)
        self.run_pipeline_button.setText("Stop preview")
        self.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self.run_readiness_label.setText("Playing preview")
        self._append_console("[Preview] Pipeline UI preview started; no files will be changed.")
        self._begin_pipeline_demo_stage(0)

    def _begin_pipeline_demo_stage(self, stage_index: int) -> None:
        self.pipeline_progress_detail.show()
        self._pipeline_demo_stage = stage_index
        self._pipeline_demo_progress = 0.0
        if stage_index == 0:
            self._pipeline_demo_last_processed = -1
        self._append_console(
            f"[{stage_index + 1}/{len(PIPELINE_STAGES)}] "
            f"{PIPELINE_PREVIEW_MESSAGES[stage_index]}."
        )
        self.set_pipeline_stage(
            stage_index,
            progress=0,
            processed_videos=0 if stage_index == 0 else None,
            total_videos=self._pipeline_demo_total_videos if stage_index == 0 else None,
            status_text=PIPELINE_STAGE_ACTIVITY[stage_index],
        )
        self._pipeline_demo_timer.start()

    def _advance_pipeline_demo(self) -> None:
        if (
            self._pipeline_demo_waiting_for_review is not None
            or self._pipeline_demo_blocked_stage is not None
        ):
            return
        if not 0 <= self._pipeline_demo_stage < len(PIPELINE_STAGES):
            return
        self._pipeline_demo_progress = min(100.0, self._pipeline_demo_progress + 4.0)
        processed_videos = None
        total_videos = None
        if self._pipeline_demo_stage == 0:
            total_videos = self._pipeline_demo_total_videos
            processed_videos = min(
                total_videos,
                round(total_videos * self._pipeline_demo_progress / 100.0),
            )
            if processed_videos != self._pipeline_demo_last_processed:
                self._pipeline_demo_last_processed = processed_videos
                self._append_console(
                    f"[Video processing] {processed_videos} / {total_videos} videos processed."
                )

        self.set_pipeline_stage(
            self._pipeline_demo_stage,
            progress=self._pipeline_demo_progress,
            processed_videos=processed_videos,
            total_videos=total_videos,
            status_text=PIPELINE_STAGE_ACTIVITY[self._pipeline_demo_stage],
        )
        if self._pipeline_demo_progress < 100:
            return

        completed_stage = self._pipeline_demo_stage
        if completed_stage in PIPELINE_REVIEW_GATES:
            self._pause_for_pipeline_review(completed_stage)
            return
        self._append_console(f"[Complete] {PIPELINE_STAGES[completed_stage]}.")
        next_stage = completed_stage + 1
        if next_stage >= len(PIPELINE_STAGES):
            self._pipeline_demo_timer.stop()
            self._pipeline_demo_complete = True
            self.complete_pipeline("Pipeline preview complete")
            self.run_pipeline_button.setText("Back to videos")
            self.run_pipeline_button.setToolTip(
                "Return to the queued videos after the completed walkthrough. No files were changed."
            )
            self.run_readiness_label.setText("Complete")
            self._append_console("[Preview complete] No processing was performed.")
            return
        self._begin_pipeline_demo_stage(next_stage)

    def _pause_for_pipeline_review(self, stage_index: int) -> None:
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._pipeline_demo_timer.stop()
        self._pipeline_demo_waiting_for_review = stage_index
        self.pipeline_review_title.setText(str(gate["title"]))
        self.pipeline_review_description.setText(str(gate["description"]))
        self._populate_pipeline_review_preview(stage_index)
        self.pipeline_change_settings_button.hide()
        self.pipeline_needs_changes_button.show()
        self.pipeline_approve_button.show()
        self.pipeline_review_panel.show()
        self.pipeline_stage_status_labels[stage_index].setText("Awaiting confirmation")
        self.pipeline_stage_review_labels[stage_index].setText("Awaiting review")
        self.pipeline_current_stage_label.setText(f"Manual check: {gate['title']}")
        self.pipeline_progress_detail.setText(
            "The pipeline is paused until this preview is confirmed."
        )
        self.pipeline_progress_detail.hide()
        self.pipeline_progress_bar.set_active(False)
        self._set_pipeline_stage_progress(stage_index, 100, False, "ready")
        self.run_pipeline_button.setText("Awaiting confirmation")
        self.run_pipeline_button.setEnabled(False)
        self.run_pipeline_button.setToolTip(
            "The walkthrough is paused. Use Confirm and continue or Needs changes in the review panel."
        )
        self.run_readiness_label.setText("Review required")
        self._append_console(f"[Manual check] {gate['title']}. Pipeline paused.")

    def _populate_pipeline_review_preview(self, stage_index: int) -> None:
        if stage_index == 3:
            self.pipeline_stickplot_preview.setPixmap(_demo_stickplot_pixmap(640, 240))
            self.pipeline_stickplot_preview.setToolTip(
                "Inspect the generated gait stickplot for obvious tracking or stride "
                "errors. Double-click it to open a larger viewer."
            )
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_stickplot_preview
            )
            return

        self.pipeline_review_video_list.clear()
        component_names = self._regions or ("Full frame",)
        regions = ", ".join(component_names)
        enhancements = self._processing_enhancement_summary()
        preview_paths: list[Path | None] = list(self._video_paths)
        if not preview_paths:
            preview_paths = [None] * self._pipeline_demo_total_videos
        if stage_index == 0:
            for index, path in enumerate(preview_paths, start=1):
                source_name = path.name if path is not None else f"Demo video {index}.mp4"
                display_name = source_name
                details = f"Regions: {regions}  •  Enhancements: {enhancements}"
                item = QListWidgetItem(f"{display_name}  —  {details}")
                item.setData(Qt.UserRole, str(path) if path is not None else "")
                item.setData(Qt.UserRole + 1, details)
                item.setData(Qt.UserRole + 2, display_name)
                item.setToolTip(
                    "Inspect this processed output for the expected crop regions and "
                    "enhancements. Double-click to open a larger preview."
                )
                self.pipeline_review_video_list.addItem(item)
        else:
            self.pipeline_component_video_lists.clear()
            while self.pipeline_component_tabs.count():
                page = self.pipeline_component_tabs.widget(0)
                self.pipeline_component_tabs.removeTab(0)
                page.deleteLater()
            for component in component_names:
                model_source = self._model_sources.get(component)
                model_name = model_source.name if model_source is not None else "configured model"
                component_list = QListWidget()
                component_list.setObjectName("PipelineReviewVideoList")
                component_list.setWordWrap(False)
                component_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                component_list.itemDoubleClicked.connect(
                    self._open_pipeline_review_video
                )
                self.pipeline_component_tabs.addTab(component_list, component)
                self.pipeline_component_tabs.setTabToolTip(
                    self.pipeline_component_tabs.count() - 1,
                    f"{component} component • {model_name}",
                )
                self.pipeline_component_video_lists[component] = component_list
                component_slug = component.replace(" ", "_")
                for index, path in enumerate(preview_paths, start=1):
                    source_name = path.name if path is not None else f"Demo video {index}.mp4"
                    display_name = f"{Path(source_name).stem}_{component_slug}_DLC.mp4"
                    details = f"Component: {component}  •  Model: {model_name}"
                    item = QListWidgetItem(f"{display_name}  —  {details}")
                    item.setData(Qt.UserRole, str(path) if path is not None else "")
                    item.setData(Qt.UserRole + 1, details)
                    item.setData(Qt.UserRole + 2, display_name)
                    item.setToolTip(
                        f"Inspect the {component} tracking overlay produced with {model_name}. "
                        "Double-click to open a larger preview."
                    )
                    component_list.addItem(item)
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_component_tabs
            )
            return
        self.pipeline_review_preview_stack.setCurrentWidget(
            self.pipeline_review_video_list
        )

    def _processing_enhancement_summary(self) -> str:
        if self._manifest_source is None:
            return "manifest settings"
        try:
            data = json.loads(self._manifest_source.read_text(encoding="utf-8"))
            enhancements = data["operations"].get("enhancements", {})
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return "manifest settings"
        if not isinstance(enhancements, dict):
            return "manifest settings"
        neutral_one = {"contrast", "saturation", "gamma"}
        active = []
        for name, value in enhancements.items():
            if isinstance(value, bool):
                enabled = value
            elif isinstance(value, (int, float)):
                enabled = value != (1 if name in neutral_one else 0)
            else:
                enabled = value not in (None, "", "none", "None")
            if enabled:
                active.append(name.replace("_", " "))
        return ", ".join(active) if active else "none"

    def _open_pipeline_review_video(self, item: QListWidgetItem) -> None:
        if item.data(Qt.UserRole + 3) == "component_header":
            return
        path_text = str(item.data(Qt.UserRole) or "")
        title = str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0])
        details = str(item.data(Qt.UserRole + 1) or "")
        try:
            if path_text and Path(path_text).is_file():
                dialog: QDialog = AutomationVideoPreviewDialog(
                    Path(path_text),
                    self,
                    subtitle=f"{details}\nDemo preview uses the queued source video until output exists.",
                )
            else:
                dialog = PipelineTextPreviewDialog(
                    title,
                    f"{details}\n\nNo generated video exists in UI preview mode.",
                    self,
                )
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not preview video", str(exc))
            return
        self._show_large_review_dialog(dialog)

    def _open_large_stickplot_preview(self) -> None:
        self._show_large_review_dialog(
            PipelineImagePreviewDialog(
                "Generated stickplot preview",
                _demo_stickplot_pixmap(1200, 700),
                self,
            )
        )

    def _show_large_review_dialog(self, dialog: QDialog) -> None:
        if self._large_review_dialog is not None:
            self._large_review_dialog.close()
        self._large_review_dialog = dialog
        dialog.finished.connect(
            lambda _result, closed_dialog=dialog: self._large_review_closed(closed_dialog)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _large_review_closed(self, dialog: QDialog) -> None:
        if self._large_review_dialog is dialog:
            self._large_review_dialog = None

    def _approve_pipeline_review(self) -> None:
        stage_index = self._pipeline_demo_waiting_for_review
        if stage_index is None:
            return
        self._pipeline_demo_waiting_for_review = None
        self.pipeline_review_panel.hide()
        self.run_pipeline_button.setEnabled(True)
        self.run_pipeline_button.setText("Stop preview")
        self.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self.run_readiness_label.setText("Playing preview")
        self._append_console(f"[Confirmed] {PIPELINE_STAGES[stage_index]}.")
        self._append_console(f"[Complete] {PIPELINE_STAGES[stage_index]}.")
        self._begin_pipeline_demo_stage(stage_index + 1)

    def _reject_pipeline_review(self) -> None:
        stage_index = self._pipeline_demo_waiting_for_review
        if stage_index is None:
            return
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_demo_blocked_stage = stage_index
        self.pipeline_review_title.setText("Pipeline paused — changes required")
        self.pipeline_review_description.setText(
            f"Update the {gate['setting']}. Resuming will replay the preceding stage and "
            "show this preview check again."
        )
        self.pipeline_change_settings_button.setText(f"Open {gate['setting']}")
        self.pipeline_change_settings_button.show()
        self.pipeline_needs_changes_button.hide()
        self.pipeline_approve_button.hide()
        card = self.pipeline_stage_cards[stage_index]
        card.setProperty("pipelineState", "blocked")
        card.style().unpolish(card)
        card.style().polish(card)
        self.pipeline_stage_status_labels[stage_index].setText("Changes required")
        self.pipeline_stage_review_labels[stage_index].setText("Needs changes")
        self._set_pipeline_stage_progress(stage_index, 100, False, "error")
        self.pipeline_current_stage_label.setText("Pipeline paused for configuration changes")
        self.pipeline_progress_detail.setText(
            f"Change the {gate['setting']}, then resume the preview."
        )
        self.run_pipeline_button.setEnabled(True)
        self.run_pipeline_button.setText("Resume preview")
        self.run_pipeline_button.setToolTip(
            f"Replay the affected stage after updating the {gate['setting']}, then return "
            "to this review checkpoint."
        )
        self.run_readiness_label.setText("Changes required")
        self._append_console(
            f"[Changes required] Update the {gate['setting']}; pipeline remains paused."
        )

    def _open_pipeline_fix_settings(self) -> None:
        stage_index = self._pipeline_demo_blocked_stage
        if stage_index is None:
            return
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._show_profile_configuration()
        self.configuration_tabs.setCurrentIndex(int(gate["tab"]))

    def _resume_pipeline_demo(self) -> None:
        stage_index = self._pipeline_demo_blocked_stage
        if stage_index is None:
            return
        replay_stage = int(PIPELINE_REVIEW_GATES[stage_index]["replay_stage"])
        self._pipeline_demo_blocked_stage = None
        self.pipeline_review_panel.hide()
        self.run_pipeline_button.setText("Stop preview")
        self.run_pipeline_button.setToolTip(STOP_PREVIEW_TOOLTIP)
        self.run_readiness_label.setText("Replaying stage")
        self._append_console(
            f"[Resume] Replaying {PIPELINE_STAGES[replay_stage]} before re-checking the preview."
        )
        self._begin_pipeline_demo_stage(replay_stage)

    def set_pipeline_running(self, running: bool) -> None:
        """Swap the video queue for pipeline progress without starting any work."""
        was_running = self._pipeline_running
        self._pipeline_running = running
        if running:
            self._stop_hover_preview()
            self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
            self.pipeline_progress_bar.set_accent_role("running")
            self.pipeline_progress_bar.set_active(True)
            if not was_running:
                total = len(self._video_paths)
                self.set_pipeline_stage(
                    0,
                    progress=0,
                    processed_videos=0,
                    total_videos=total,
                    status_text="Preparing videos",
                )
        else:
            self.automation_input_stack.setCurrentWidget(self.video_panel)
            self.pipeline_progress_detail.show()
            self.pipeline_progress_bar.set_active(False)

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
        if self._pipeline_demo_waiting_for_review is None:
            self.pipeline_progress_detail.show()
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        active_status = status_text or "In progress"
        stage_progress = None if progress is None else max(0.0, min(100.0, float(progress)))
        for index, (card, label, review_label) in enumerate(
            zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_status_labels,
                self.pipeline_stage_review_labels,
            )
        ):
            if index < stage_index:
                state, text = "complete", "Complete"
                self._set_pipeline_stage_progress(index, 100, False, "ready")
            elif index == stage_index:
                state, text = "active", active_status
                self._set_pipeline_stage_progress(index, stage_progress, True, "running")
            else:
                state, text = "pending", "Waiting"
                self._set_pipeline_stage_progress(index, 0, False, "primary")
            card.setProperty("pipelineState", state)
            label.setText(text)
            if index in PIPELINE_REVIEW_GATES:
                review_label.setText("Reviewed" if index < stage_index else "Review required")
            card.style().unpolish(card)
            card.style().polish(card)

        stage_title = PIPELINE_STAGES[stage_index]
        self.pipeline_current_stage_label.setText(f"Current stage: {stage_title}")
        if processed_videos is not None or total_videos is not None:
            processed = max(0, processed_videos or 0)
            total = max(0, total_videos or 0)
            self.pipeline_video_progress_label.setText(
                f"{processed} / {total} videos processed"
            )

        if progress is None:
            self.pipeline_progress_bar.set_accent_role("running")
            self.pipeline_progress_bar.setRange(0, 0)
            self.pipeline_progress_bar.set_active(True)
            self.pipeline_progress_bar.setFormat("Working…")
            self.pipeline_progress_detail.setText(active_status)
            return

        overall = round(((stage_index + stage_progress / 100.0) / len(PIPELINE_STAGES)) * 100)
        self.pipeline_progress_bar.set_accent_role("running")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(overall)
        self.pipeline_progress_bar.set_active(True)
        self.pipeline_progress_bar.setFormat(f"Overall progress  %p%")
        self.pipeline_progress_detail.setText(
            f"{stage_title}: {stage_progress:g}% complete"
        )

    def complete_pipeline(self, status_text: str = "Pipeline complete") -> None:
        self._pipeline_running = False
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        for index, (card, label, review_label) in enumerate(zip(
            self.pipeline_stage_cards,
            self.pipeline_stage_status_labels,
            self.pipeline_stage_review_labels,
        )):
            card.setProperty("pipelineState", "complete")
            label.setText("Complete")
            if review_label.text():
                review_label.setText("Reviewed")
            self._set_pipeline_stage_progress(index, 100, False, "ready")
            card.style().unpolish(card)
            card.style().polish(card)
        self.pipeline_current_stage_label.setText(status_text)
        self.pipeline_progress_bar.set_accent_role("ready")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(100)
        self.pipeline_progress_bar.set_active(False)
        self.pipeline_progress_bar.setFormat("Overall progress  %p%")
        self.pipeline_progress_detail.show()
        self.pipeline_progress_detail.setText("All automated stages completed.")

    def _set_pipeline_stage_progress(
        self,
        stage_index: int,
        value: float | None,
        active: bool,
        accent_role: str,
    ) -> None:
        if not 0 <= stage_index < len(self.pipeline_stage_progress_bars):
            return
        bar = self.pipeline_stage_progress_bars[stage_index]
        bar.set_accent_role(accent_role)
        if value is None:
            bar.setRange(0, 0)
        else:
            bar.setRange(0, 100)
            bar.setValue(round(max(0.0, min(100.0, value))))
        bar.set_active(active)

    def _start_hover_preview(self, item: QListWidgetItem) -> None:
        self._release_hover_capture()
        path = Path(str(item.data(Qt.UserRole)))
        self._show_hover_card(item, path)
        self.video_hover_preview.setPixmap(QPixmap())
        if cv2 is None:
            self.video_hover_preview.setText("Preview unavailable")
            return
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            capture.release()
            self.video_hover_preview.setText("Could not play preview")
            return
        self._hover_capture = capture
        self._hover_preview_path = path
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        details = []
        if width > 0 and height > 0:
            details.append(f"{width}×{height}")
        if fps > 0:
            fps_text = f"{fps:.2f}".rstrip("0").rstrip(".")
            details.append(f"{fps_text} fps")
        if duration > 0:
            details.append(f"{duration:.1f} s")
        details.append(self._format_file_size(path.stat().st_size))
        self.video_hover_details.setText("  •  ".join(details))
        interval = round(1000 / fps) if fps > 0 else 83
        self._hover_preview_timer.start(max(33, min(150, interval)))
        self._advance_hover_preview()

    def _advance_hover_preview(self) -> None:
        capture = self._hover_capture
        if capture is None:
            return
        success, frame = capture.read()
        if not success or frame is None:
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
            success, frame = capture.read()
        if not success or frame is None:
            self._release_hover_capture()
            self.video_hover_preview.setPixmap(QPixmap())
            self.video_hover_preview.setText("Could not play preview")
            return
        self._render_hover_preview_frame(frame)

    def _stop_hover_preview(self) -> None:
        self._release_hover_capture()
        self.video_hover_card.hide()

    def _release_hover_capture(self) -> None:
        self._hover_preview_timer.stop()
        if self._hover_capture is not None:
            self._hover_capture.release()
        self._hover_capture = None
        self._hover_preview_path = None

    def _show_hover_card(self, item: QListWidgetItem, path: Path) -> None:
        display_name = path.name if len(path.name) <= 36 else f"{path.stem[:29]}…{path.suffix}"
        self.video_hover_name.setText(display_name)
        self.video_hover_name.setToolTip(str(path))
        self.video_hover_details.setText("Double-click for expanded preview")
        viewport = self.video_list.viewport()
        item_rect = self.video_list.visualItemRect(item)
        margin = 8
        x = max(margin, viewport.width() - self.video_hover_card.width() - margin)
        y = item_rect.bottom() + 5
        if y + self.video_hover_card.height() > viewport.height() - margin:
            y = item_rect.top() - self.video_hover_card.height() - 5
        y = max(margin, y)
        self.video_hover_card.move(x, y)
        self.video_hover_card.raise_()
        self.video_hover_card.show()

    @staticmethod
    def _format_file_size(size: int) -> str:
        if size >= 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        if size >= 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size} B"

    def _render_hover_preview_frame(self, frame) -> None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image).scaled(
            self.video_hover_preview.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_hover_preview.setText("")
        self.video_hover_preview.setPixmap(pixmap)

    def _open_large_video_preview(self, item: QListWidgetItem | None = None) -> None:
        item = item or self.video_list.currentItem()
        if item is None:
            return
        path = Path(str(item.data(Qt.UserRole)))
        try:
            dialog = AutomationVideoPreviewDialog(path, self)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not preview video", str(exc))
            return
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        self._large_preview_dialog = dialog
        dialog.finished.connect(
            lambda _result, closed_dialog=dialog: self._large_preview_closed(closed_dialog)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _large_preview_closed(self, dialog: AutomationVideoPreviewDialog) -> None:
        if self._large_preview_dialog is dialog:
            self._large_preview_dialog = None

    def closeEvent(self, event) -> None:
        self._pipeline_demo_timer.stop()
        self._release_hover_capture()
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        if self._large_review_dialog is not None:
            self._large_review_dialog.close()
        super().closeEvent(event)

    def _choose_model_file(self, region: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose DeepLabCut model for {region}",
            str(Path.home()),
            "Model files (*.zip *.tar *.gz *.h5 *.pt *.pth *.yaml *.yml);;All files (*)",
        )
        if path:
            self._set_model_source(region, Path(path))

    def _choose_model_folder(self, region: str) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            f"Choose DeepLabCut model folder for {region}",
            str(Path.home()),
        )
        if path:
            self._set_model_source(region, Path(path))

    def _set_model_source(self, region: str, path: Path) -> None:
        if region not in self._model_sources:
            raise ValueError(f"Unknown manifest region: {region}")
        self._model_sources[region] = path.expanduser().resolve()
        self._render_model_rows()
        selected = sum(path is not None for path in self._model_sources.values())
        self.status_label.setText(f"Models selected for {selected} of {len(self._regions)} regions.")

    def _render_model_rows(self) -> None:
        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self._regions:
            placeholder = QLabel("Manifest required")
            placeholder.setObjectName("ModelsPlaceholder")
            placeholder.setWordWrap(True)
            placeholder.setToolTip(
                "Complete step 1 first. The manifest supplies the region names needed to "
                "create one DeepLabCut model slot per region."
            )
            self.models_layout.addWidget(placeholder)
            return
        for region in self._regions:
            row = QFrame()
            row.setObjectName("RegionModelRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 6, 8, 6)
            layout.setSpacing(8)
            region_label = QLabel(region)
            region_label.setObjectName("RegionName")
            region_label.setMinimumWidth(110)
            layout.addWidget(region_label)
            model_path = self._model_sources.get(region)
            path_label = self._path_label()
            path_label.setText(str(model_path) if model_path is not None else "Model required")
            path_label.setToolTip(str(model_path) if model_path is not None else "")
            layout.addWidget(path_label, 1)
            file_button = QPushButton("Upload file")
            file_button.setToolTip(
                f"Choose the trained DeepLabCut model file used to analyze the {region} region."
            )
            file_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_file(name))
            layout.addWidget(file_button)
            folder_button = QPushButton("Upload folder")
            folder_button.setToolTip(
                f"Choose the trained DeepLabCut model folder used to analyze the {region} region."
            )
            folder_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_folder(name))
            layout.addWidget(folder_button)
            self.models_layout.addWidget(row)

    def _refresh_paths(self) -> None:
        self._set_path_label(self.manifest_path_label, self._manifest_source)
        self._set_path_label(self.calibration_path_label, self._calibration_source)
        self._set_path_label(
            self.analysis_manifest_path_label,
            self._analysis_manifest_source,
        )
        self._set_path_label(self.knee_manifest_path_label, self._knee_manifest_source)
        if self._regions:
            self.regions_label.setText("Detected regions: " + " → ".join(self._regions))
        else:
            self.regions_label.setText("No regions detected yet.")

    @staticmethod
    def _set_path_label(label: QLabel, path: Path | None) -> None:
        label.setText(str(path) if path is not None else "Not selected")
        label.setToolTip(str(path) if path is not None else "")

    def _save_profile(self) -> None:
        name = self.profile_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Profile name required", "Enter a name for this profile.")
            return
        if self._manifest_source is None:
            QMessageBox.warning(self, "Manifest required", "Complete step 1 by uploading a processing manifest.")
            return
        missing_models = [region for region in self._regions if self._model_sources.get(region) is None]
        if missing_models:
            QMessageBox.warning(
                self,
                "Region models required",
                "Upload one DeepLabCut model for each region:\n• " + "\n• ".join(missing_models),
            )
            return
        if self._calibration_source is None:
            QMessageBox.warning(self, "Calibration required", "Complete step 3 by uploading a calibration map.")
            return
        if self._analysis_manifest_source is None:
            QMessageBox.warning(
                self,
                "Analysis manifest required",
                "Complete step 3 by uploading a gait analysis manifest.",
            )
            return
        if self._current_profile_id is not None:
            if not self._is_dirty():
                self.status_label.setText("No profile changes to save.")
                return
            if not self._confirm_replace_profile(name):
                return
        try:
            profile = self._store.save(
                name,
                self._manifest_source,
                self._calibration_source,
                {region: path for region, path in self._model_sources.items() if path is not None},
                profile_id=self._current_profile_id,
                analysis_manifest=self._analysis_manifest_source,
                knee_manifest=self._knee_manifest_source,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Could not save profile", str(exc))
            return
        self._refresh_profiles(profile.id)
        self.status_label.setText(f'Profile "{profile.name}" saved. No pipeline was started.')

    def _delete_profile(self) -> None:
        if self._current_profile_id is None:
            return
        profile_name = self.profile_name.text().strip() or "this profile"
        if not self._confirm_delete_profile(profile_name):
            return
        try:
            self._store.delete(self._current_profile_id)
        except OSError as exc:
            QMessageBox.critical(self, "Could not delete profile", str(exc))
            return
        self._refresh_profiles()
        self.status_label.setText(f'Profile "{profile_name}" was permanently deleted.')

    def _confirm_replace_profile(self, profile_name: str) -> bool:
        return QMessageBox.question(
            self,
            "Replace saved profile?",
            f'Saving will replace the files currently stored in "{profile_name}" and delete those '
            "app-managed copies forever. Keep your own backup. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _confirm_delete_profile(self, profile_name: str) -> bool:
        return QMessageBox.question(
            self,
            "Delete profile forever?",
            f'Deleting "{profile_name}" will permanently remove the profile and all of its stored '
            "files. Keep your own backup. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _confirm_discard_changes(self) -> bool:
        if not self._is_dirty():
            return True
        return QMessageBox.question(
            self,
            "Discard unsaved profile changes?",
            "Changing profiles will discard the selections you have not saved. Are you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) == QMessageBox.Yes

    def _snapshot(self) -> tuple[str, ...]:
        return (
            self.profile_name.text().strip(),
            str(self._manifest_source or ""),
            *(f"{region}\0{self._model_sources.get(region) or ''}" for region in self._regions),
            str(self._calibration_source or ""),
            str(self._analysis_manifest_source or ""),
            str(self._knee_manifest_source or ""),
        )

    def _is_dirty(self) -> bool:
        if self._saved_snapshot is None:
            return any(self._snapshot())
        return self._snapshot() != self._saved_snapshot

    def _select_combo_id(self, profile_id: str | None) -> None:
        selectors = (self.profile_selector, self.configuration_profile_selector)
        blockers = [QSignalBlocker(selector) for selector in selectors]
        for selector in selectors:
            target_index = -1
            for index in range(selector.count()):
                if selector.itemData(index) == profile_id:
                    target_index = index
                    break
            selector.setCurrentIndex(target_index)
        del blockers

    def _apply_style(self) -> None:
        self.setStyleSheet(
            theme.stylesheet(
                """
                QWidget#AutomatedPipelineProfilesWidget {
                    background: {theme.BACKGROUND};
                    color: {theme.TEXT};
                }
                QFrame#ProfileHeader, QFrame#MainAutomationMenu,
                QFrame#ProfileConfigurationToolbar, QFrame#ProfileManagementPanel {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 3px;
                }
                QLabel#AutomatedProfileTitle, QLabel#MainAutomationTitle,
                QLabel#ProfileConfigurationTitle, QLabel#ProfileStageTitle {
                    color: {theme.TEXT};
                    font-size: 15px;
                    font-weight: 650;
                }
                QLabel#AutomatedProfileDescription, QLabel#ProfileStageDescription,
                QLabel#DetectedRegionsLabel, QLabel#ModelsPlaceholder, QLabel#ProfileStatusLabel {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QLabel#AutomationPanelTitle {
                    color: {theme.TEXT};
                    font-weight: 650;
                }
                QLabel#VideoCountLabel {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QLabel#FieldLabel, QLabel#RegionName {
                    color: {theme.TEXT};
                    font-weight: 600;
                    min-width: 48px;
                }
                QFrame#VideoDropPanel, QFrame#AutomationConsolePanel,
                QFrame#PipelineStatusPanel {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                QStackedWidget#AutomationInputStack {
                    background: {theme.BACKGROUND};
                    border: 0;
                }
                QFrame#PipelineStageCard {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 3px;
                    min-width: 58px;
                    min-height: 72px;
                }
                QFrame#PipelineStageCard[pipelineState="active"] {
                    background: {theme.SOFT};
                    border: 2px solid {theme.PRIMARY};
                }
                QFrame#PipelineStageCard[pipelineState="complete"] {
                    background: {theme.SURFACE};
                    border: 2px solid {theme.STATUS_READY};
                }
                QFrame#PipelineStageCard[pipelineState="blocked"] {
                    background: {theme.SURFACE};
                    border: 2px solid {theme.STATUS_ERROR};
                }
                QProgressBar#PipelineStageProgress {
                    background: transparent;
                    border: 0;
                    min-width: 52px;
                    max-width: 52px;
                    min-height: 52px;
                    max-height: 52px;
                }
                QLabel#PipelineStageName {
                    color: {theme.TEXT};
                    font-size: 10px;
                    font-weight: 650;
                }
                QLabel#PipelineStageStatus, QLabel#PipelineProgressDetail,
                QLabel#PipelineVideoProgress {
                    color: {theme.CONNECTOR};
                    font-size: 10px;
                }
                QLabel#PipelineReviewIndicator {
                    color: {theme.PRIMARY};
                    font-size: 9px;
                    font-weight: 700;
                }
                QLabel#PipelineCurrentStage {
                    color: {theme.TEXT};
                    font-size: 12px;
                    font-weight: 650;
                }
                QLabel#PipelineConnector {
                    color: {theme.CONNECTOR};
                    font-size: 16px;
                    font-weight: 700;
                    max-width: 10px;
                }
                QProgressBar#PipelineProgressBar {
                    min-height: 22px;
                    text-align: center;
                    font-weight: 650;
                }
                QProgressBar#PipelineProgressBar::chunk {
                    background: {theme.PRIMARY};
                }
                QFrame#PipelineReviewPanel {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.PRIMARY};
                    border-radius: 3px;
                }
                QStackedWidget#PipelineReviewPreviewStack,
                QListWidget#PipelineReviewVideoList,
                QLabel#PipelineStickplotPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                    font-size: 10px;
                }
                QListWidget#PipelineReviewVideoList::item {
                    background: {theme.CANVAS};
                    color: {theme.CANVAS_TEXT};
                    padding: 6px;
                    border-bottom: 1px solid {theme.BORDER};
                }
                QListWidget#PipelineReviewVideoList::item:selected {
                    background: {theme.SOFT};
                    color: {theme.TEXT};
                }
                QTabWidget#PipelineComponentTabs::pane {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                }
                QTabWidget#PipelineComponentTabs QTabBar::tab {
                    padding: 4px 8px;
                    font-size: 10px;
                }
                QLabel#PipelineReviewTitle {
                    color: {theme.TEXT};
                    font-size: 12px;
                    font-weight: 700;
                }
                QLabel#PipelineReviewDescription {
                    color: {theme.CONNECTOR};
                    font-size: 11px;
                }
                QFrame#VideoHoverCard {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 5px;
                }
                QLabel#VideoHoverPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    color: {theme.CANVAS_TEXT};
                    font-size: 11px;
                }
                QLabel#VideoHoverName {
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 650;
                }
                QLabel#VideoHoverDetails {
                    color: {theme.CONNECTOR};
                    font-size: 10px;
                }
                QListWidget#AutomationVideoDropList {
                    background: {theme.SURFACE};
                    border: 2px dashed {theme.BORDER};
                    border-radius: 3px;
                    color: {theme.TEXT};
                    padding: 6px;
                }
                QListWidget#AutomationVideoDropList:focus {
                    border-color: {theme.PRIMARY};
                }
                QPlainTextEdit#AutomationConsole {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                    font-size: 11px;
                }
                QPushButton#RunPipelineButton {
                    background: {theme.PRIMARY};
                    border-color: {theme.PRIMARY};
                    color: {theme.PRIMARY_TEXT};
                    font-size: 14px;
                    font-weight: 700;
                    min-width: 150px;
                    padding: 9px 16px;
                }
                QPushButton#RunPipelineButton:disabled {
                    background: {theme.PANEL};
                    border-color: {theme.BORDER};
                    color: {theme.CONNECTOR};
                }
                QTabWidget#ProfileConfigurationTabs::pane {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                }
                QTabWidget#ProfileConfigurationTabs QTabBar::tab {
                    background: {theme.PANEL};
                }
                QTabWidget#ProfileConfigurationTabs QTabBar::tab:selected {
                    background: {theme.SURFACE};
                    color: {theme.TEXT};
                    font-weight: 650;
                }
                QWidget#ProfileStagePage {
                    background: {theme.SURFACE};
                }
                QFrame#RegionModelRow {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                QLabel#AssetPath {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                    padding: 4px 6px;
                }
                QPushButton#DeleteProfileButton:hover {
                    border-color: {theme.STATUS_ERROR};
                    color: {theme.STATUS_ERROR};
                }
                QPushButton#SmallProfileButton {
                    min-height: 16px;
                    padding: 4px 7px;
                    font-size: 11px;
                }
                QPushButton#OpenProfileConfigurationButton {
                    background: {theme.PRIMARY};
                    border-color: {theme.PRIMARY};
                    color: {theme.PRIMARY_TEXT};
                    font-weight: 650;
                }
                QPushButton#OpenProfileConfigurationButton:hover {
                    background: {theme.SOFT};
                    border-color: {theme.TEXT};
                    color: {theme.TEXT};
                }
                QPushButton#BackToAutomationButton {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    color: {theme.TEXT};
                    font-weight: 650;
                }
                QWidget#MainAutomationPage, QWidget#ProfileConfigurationPage,
                QStackedWidget#AutomationWorkspaceStack {
                    background: {theme.BACKGROUND};
                }
                """
            )
        )


class AutomationVideoPreviewDialog(QDialog):
    def __init__(
        self,
        path: Path,
        parent: QWidget | None = None,
        *,
        subtitle: str | None = None,
    ):
        if cv2 is None:
            raise OSError("OpenCV is not available for video preview.")
        super().__init__(parent)
        self._path = path.expanduser().resolve()
        self._capture = cv2.VideoCapture(str(self._path))
        if not self._capture.isOpened():
            self._capture.release()
            raise ValueError(f"Could not open video: {self._path.name}")
        frame_count_value = self._capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps_value = self._capture.get(cv2.CAP_PROP_FPS)
        self._frame_count = max(1, int(frame_count_value)) if frame_count_value > 0 else 1
        self._fps = float(fps_value) if fps_value > 0 else 0.0
        self._source_pixmap = QPixmap()

        self.setWindowTitle(f"Video preview — {self._path.name}")
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel(self._path.name)
        title.setObjectName("LargeVideoPreviewTitle")
        title.setWordWrap(True)
        root.addWidget(title)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("LargeVideoPreviewSubtitle")
            subtitle_label.setWordWrap(True)
            root.addWidget(subtitle_label)
        self.preview = QLabel("Loading preview…")
        self.preview.setObjectName("LargeVideoPreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(680, 380)
        root.addWidget(self.preview, 1)

        slider_row = QHBoxLayout()
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.setObjectName("VideoPreviewSlider")
        self.frame_slider.setRange(0, self._frame_count - 1)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(max(1, self._frame_count // 20))
        self.frame_label = QLabel()
        self.frame_label.setObjectName("VideoPreviewFrameLabel")
        self.frame_label.setMinimumWidth(150)
        self.frame_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        slider_row.addWidget(self.frame_slider, 1)
        slider_row.addWidget(self.frame_label)
        root.addLayout(slider_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.frame_slider.valueChanged.connect(self._load_frame)
        self.setStyleSheet(
            theme.stylesheet(
                """
                QLabel#LargeVideoPreviewTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                }
                QLabel#LargeVideoPreviewSubtitle {
                    color: {theme.CONNECTOR};
                    font-size: 11px;
                }
                QLabel#LargeVideoPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                }
                QLabel#VideoPreviewFrameLabel {
                    color: {theme.CONNECTOR};
                    font-size: 11px;
                }
                """
            )
        )
        self._load_frame(0)

    def _load_frame(self, frame_index: int) -> None:
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        success, frame = self._capture.read()
        if not success or frame is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Could not read this frame")
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channels = rgb.shape
        image = QImage(rgb.data, width, height, channels * width, QImage.Format_RGB888).copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._render_frame()
        seconds = frame_index / self._fps if self._fps > 0 else 0.0
        self.frame_label.setText(
            f"{frame_index + 1:,} / {self._frame_count:,}   {seconds:.2f} s"
        )

    def _render_frame(self) -> None:
        if self._source_pixmap.isNull():
            return
        self.preview.setText("")
        self.preview.setPixmap(
            self._source_pixmap.scaled(
                self.preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_frame()

    def closeEvent(self, event) -> None:
        self._capture.release()
        super().closeEvent(event)


class DoubleClickLabel(QLabel):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        event.accept()


class PipelineImagePreviewDialog(QDialog):
    def __init__(self, title: str, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self._source_pixmap = pixmap
        self.setWindowTitle(title)
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("LargeVideoPreview")
        layout.addWidget(self.preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            theme.stylesheet(
                """
                QLabel#LargeVideoPreviewTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                }
                QLabel#LargeVideoPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                }
                """
            )
        )
        self._render_preview()

    def _render_preview(self) -> None:
        self.preview.setPixmap(
            self._source_pixmap.scaled(
                self.preview.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_preview()


class PipelineTextPreviewDialog(QDialog):
    def __init__(self, title: str, details: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 360)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("LargeVideoPreviewTitle")
        layout.addWidget(heading)
        preview = QLabel(details)
        preview.setObjectName("LargeVideoPreview")
        preview.setAlignment(Qt.AlignCenter)
        preview.setWordWrap(True)
        layout.addWidget(preview, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setStyleSheet(
            theme.stylesheet(
                """
                QLabel#LargeVideoPreviewTitle {
                    color: {theme.TEXT};
                    font-size: 14px;
                    font-weight: 650;
                }
                QLabel#LargeVideoPreview {
                    background: {theme.CANVAS};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CANVAS_TEXT};
                    padding: 24px;
                }
                """
            )
        )


def _demo_stickplot_pixmap(width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("white"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    margin = max(18, width // 28)
    baseline = height - margin * 2
    painter.setPen(QPen(QColor("#b9b2a8"), max(1, width // 600)))
    painter.drawLine(margin, baseline, width - margin, baseline)
    painter.setPen(QPen(QColor(theme.PRIMARY), max(2, width // 300)))
    pose_count = 6
    spacing = (width - margin * 2) / pose_count
    scale = max(0.7, min(width / 900, height / 420))
    for pose in range(pose_count):
        x = int(margin + spacing * (pose + 0.5))
        phase = (pose - 2.5) / 2.5
        hip = (x, int(baseline - 115 * scale))
        knee = (int(x + phase * 24 * scale), int(baseline - 70 * scale))
        ankle = (int(x - phase * 30 * scale), int(baseline - 24 * scale))
        toe = (int(ankle[0] + 25 * scale), baseline)
        crest = (int(x - 8 * scale), int(baseline - 155 * scale))
        shoulder = (int(x + 12 * scale), int(baseline - 195 * scale))
        joints = (shoulder, crest, hip, knee, ankle, toe)
        for start, end in zip(joints, joints[1:]):
            painter.drawLine(start[0], start[1], end[0], end[1])
        radius = max(2, int(4 * scale))
        for joint_x, joint_y in joints:
            painter.drawEllipse(joint_x - radius, joint_y - radius, radius * 2, radius * 2)
    painter.setPen(QColor("#5f5a54"))
    painter.drawText(margin, margin, "Demo stickplot preview — double-click for large view")
    painter.end()
    return pixmap


class VideoDropList(QListWidget):
    paths_dropped = Signal(object)
    pointer_left = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setMouseTracking(True)

    def leaveEvent(self, event) -> None:
        self.pointer_left.emit()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        if self.itemAt(event.position().toPoint()) is None:
            self.pointer_left.emit()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._video_paths(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._video_paths(event.mimeData().urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = self._video_paths(event.mimeData().urls())
        if not paths:
            event.ignore()
            return
        self.paths_dropped.emit(paths)
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.count():
            return
        painter = QPainter(self.viewport())
        painter.setPen(self.palette().color(QPalette.ColorRole.PlaceholderText))
        painter.drawText(
            self.viewport().rect().adjusted(20, 20, -20, -20),
            Qt.AlignCenter | Qt.TextWordWrap,
            "Drop videos here",
        )

    @staticmethod
    def _video_paths(urls) -> list[Path]:
        paths = []
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile()).expanduser().resolve()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                paths.append(path)
        return paths
