from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
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
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.automated_pipeline.worker import AutomatedPipelineWorker
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
    "Run the selected profile on the queued videos. With no complete profile or videos, "
    "this button opens the visual pipeline preview."
)
STOP_PREVIEW_TOOLTIP = (
    "Stop the pipeline walkthrough and return to the video queue. No files have been changed."
)
PIPELINE_REVIEW_GATES = {
    0: {
        "title": "Review processed videos",
        "description": "Verify each crop. Double-click a video to enlarge it.",
        "preview": "Processed region-video previews appear here.",
        "setting": "video processing manifest",
        "tab": 0,
        "replay_stage": 0,
    },
    1: {
        "title": "Review DLC overlays",
        "description": "Verify tracking and model assignment. Double-click to enlarge.",
        "preview": "DeepLabCut overlay-video previews appear here.",
        "setting": "region model configuration",
        "tab": 1,
        "replay_stage": 1,
    },
    3: {
        "title": "Review stickplot",
        "description": "Verify the stickplot. Double-click to enlarge.",
        "preview": "The generated stickplot preview appears here.",
        "setting": "gait analysis manifest",
        "tab": 2,
        "replay_stage": 3,
    },
}


@dataclass(frozen=True)
class ReviewVideoSource:
    path: Path
    title: str
    details: str
    view_name: str


class AutomatedPipelineProfilesWidget(QWidget):
    """Switchable automation workspace and profile-configuration workspace."""

    workspace_changed = Signal(str)
    manual_tool_requested = Signal(str)

    def __init__(self, store: AutomatedProfileStore | None = None):
        super().__init__()
        self.setObjectName("AutomatedPipelineProfilesWidget")
        project_root = find_project_root(__file__)
        self._project_root = project_root
        self._automated_output_root = project_root / "outputs" / "automated_pipeline"
        self._automated_output_root.mkdir(parents=True, exist_ok=True)
        stable_profile_root = project_root / "outputs" / "automated_profiles"
        launch_root = find_project_root(Path.cwd())
        legacy_profile_root = launch_root / "outputs" / "automated_profiles"
        profile_root = stable_profile_root
        if (
            legacy_profile_root != stable_profile_root
            and legacy_profile_root.exists()
            and not any(stable_profile_root.glob("*/profile.json"))
        ):
            profile_root = legacy_profile_root
        self._store = store or AutomatedProfileStore(profile_root)
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
        self._pipeline_worker: AutomatedPipelineWorker | None = None
        self._pipeline_output_folder: Path | None = None
        self._pipeline_real_complete = False
        self._pipeline_real_waiting_for_review: int | None = None
        self._pipeline_review_artifacts: dict[str, object] | None = None
        self._pipeline_stickplot_path: Path | None = None
        self._pipeline_stickplot_pixmap: QPixmap | None = None
        self._pipeline_skipped_stages: set[int] = set()
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
            "processing manifest, region-specific DeepLabCut models, and any analysis "
            "stages enabled when the profile was created."
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
        console_header = QHBoxLayout()
        console_header.setSpacing(8)
        console_title = QLabel("Log")
        console_title.setObjectName("AutomationPanelTitle")
        console_header.addWidget(console_title)
        console_header.addStretch(1)
        self.pipeline_log_state = QLabel("Ready")
        self.pipeline_log_state.setObjectName("PipelineLogState")
        self.pipeline_log_state.setProperty("logState", "ready")
        console_header.addWidget(self.pipeline_log_state)
        console_layout.addLayout(console_header)
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
        self.automation_console.setPlainText("Ready")
        console_layout.addWidget(self.automation_console, 1)
        automation_content.addWidget(console_panel, 2)
        self.automation_console_panel = console_panel
        self._automation_input_default_minimum_height = self.automation_input_stack.minimumHeight()
        self._automation_input_default_maximum_height = self.automation_input_stack.maximumHeight()
        self._automation_console_default_minimum_height = console_panel.minimumHeight()
        self._automation_console_default_maximum_height = console_panel.maximumHeight()
        automation_layout.addLayout(automation_content, 1)

        run_row = QHBoxLayout()
        self.run_readiness_label = QLabel("Ready")
        self.run_readiness_label.setObjectName("ProfileStatusLabel")
        run_row.addWidget(self.run_readiness_label, 1)
        self.skip_knee_correction_button = QPushButton("Skip knee correction")
        self.skip_knee_correction_button.setObjectName("PipelineOptionButton")
        self.skip_knee_correction_button.setCheckable(True)
        self.skip_knee_correction_button.setAccessibleName(
            "Exclude knee correction from this run"
        )
        self.skip_knee_correction_button.setToolTip(
            "Use the DeepLabCut coordinates directly, even when the profile has a knee manifest."
        )
        run_row.addWidget(self.skip_knee_correction_button)
        self.skip_gait_analysis_button = QPushButton("Skip gait analysis")
        self.skip_gait_analysis_button.setObjectName("PipelineOptionButton")
        self.skip_gait_analysis_button.setCheckable(True)
        self.skip_gait_analysis_button.setAccessibleName(
            "Exclude gait analysis from this run"
        )
        self.skip_gait_analysis_button.setToolTip(
            "Finish after DeepLabCut or knee correction without stickplots or gait parameters."
        )
        run_row.addWidget(self.skip_gait_analysis_button)
        self.open_pipeline_output_button = QPushButton("Open outputs")
        self.open_pipeline_output_button.setObjectName("OpenPipelineOutputButton")
        self.open_pipeline_output_button.setToolTip(str(self._automated_output_root))
        run_row.addWidget(self.open_pipeline_output_button)
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
        self.open_video_settings_button = QPushButton("Open Video tool")
        self.open_video_settings_button.setObjectName("OpenManualToolButton")
        self.open_video_settings_button.setToolTip(
            "Open Video Processing to create or update the video settings manifest."
        )
        manifest_row.addWidget(self.open_video_settings_button)
        self.manifest_upload_button = QPushButton("Upload manifest")
        self.manifest_upload_button.setObjectName("ProfileUploadButton")
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
        self.configuration_tabs.addTab(manifest_page, "1  Video settings")
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
        self.models_scroll = QScrollArea()
        self.models_scroll.setObjectName("ProfileModelsScroll")
        self.models_scroll.setWidgetResizable(True)
        self.models_scroll.setFrameShape(QFrame.NoFrame)
        self.models_scroll.setWidget(self.models_container)
        models_content.addWidget(self.models_scroll, 1)
        self.configuration_tabs.addTab(models_page, "2  DLC models")
        self.configuration_tabs.setTabToolTip(
            1,
            "Assign one trained DeepLabCut model file or model folder to each region "
            "detected in step 1.",
        )

        calibration_page, calibration_content = self._stage_page()
        calibration_content.addWidget(self._field_label("Included analysis stages"))
        analysis_stage_row = QHBoxLayout()
        self.include_gait_analysis_button = QPushButton("Gait analysis")
        self.include_gait_analysis_button.setObjectName("ProfileStageToggle")
        self.include_gait_analysis_button.setCheckable(True)
        self.include_gait_analysis_button.setChecked(True)
        self.include_gait_analysis_button.setToolTip(
            "Include stickplot generation and final gait parameter extraction in this profile."
        )
        analysis_stage_row.addWidget(self.include_gait_analysis_button)
        self.include_knee_correction_button = QPushButton("Knee correction")
        self.include_knee_correction_button.setObjectName("ProfileStageToggle")
        self.include_knee_correction_button.setCheckable(True)
        self.include_knee_correction_button.setChecked(False)
        self.include_knee_correction_button.setToolTip(
            "Include knee-coordinate correction before stickplot or gait analysis."
        )
        analysis_stage_row.addWidget(self.include_knee_correction_button)
        analysis_stage_row.addStretch(1)
        calibration_content.addLayout(analysis_stage_row)

        calibration_content.addSpacing(10)
        calibration_content.addWidget(self._field_label("Calibration map"))
        calibration_row = QHBoxLayout()
        self.calibration_path_label = self._path_label()
        calibration_row.addWidget(self.calibration_path_label, 1)
        self.open_calibration_settings_button = QPushButton("Open Calibration tool")
        self.open_calibration_settings_button.setObjectName("OpenManualToolButton")
        self.open_calibration_settings_button.setToolTip(
            "Open Calibration to create or update the calibration map."
        )
        calibration_row.addWidget(self.open_calibration_settings_button)
        self.calibration_upload_button = QPushButton("Upload calibration map")
        self.calibration_upload_button.setObjectName("ProfileUploadButton")
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
        self.open_gait_settings_button = QPushButton("Open Gait tool")
        self.open_gait_settings_button.setObjectName("OpenManualToolButton")
        self.open_gait_settings_button.setToolTip(
            "Open Gait Parameter Analysis to create or update its analysis manifest."
        )
        analysis_row.addWidget(self.open_gait_settings_button)
        self.analysis_manifest_upload_button = QPushButton("Upload analysis manifest")
        self.analysis_manifest_upload_button.setObjectName("ProfileUploadButton")
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
        self.open_knee_settings_button = QPushButton("Open Knee tool")
        self.open_knee_settings_button.setObjectName("OpenManualToolButton")
        self.open_knee_settings_button.setToolTip(
            "Open Knee Correction to create or update its knee-analysis manifest."
        )
        knee_row.addWidget(self.open_knee_settings_button)
        self.knee_manifest_upload_button = QPushButton("Upload knee manifest")
        self.knee_manifest_upload_button.setObjectName("ProfileUploadButton")
        self.knee_manifest_upload_button.setToolTip(
            "Choose the knee-analysis manifest exported by the Knee tool. It stores "
            "the knee lengths, label choices, confidence cutoff, and correction direction."
        )
        knee_row.addWidget(self.knee_manifest_upload_button)
        calibration_content.addLayout(knee_row)
        calibration_content.addStretch(1)
        self.configuration_tabs.addTab(calibration_page, "3  Analysis settings")
        self.configuration_tabs.setTabToolTip(
            2,
            "Choose which analysis stages to include, then supply only their required files.",
        )

        readiness_panel = QFrame()
        readiness_panel.setObjectName("ProfileReadinessPanel")
        readiness_panel.setMinimumWidth(250)
        readiness_panel.setMaximumWidth(300)
        readiness_panel.setMinimumHeight(230)
        readiness_panel.setMaximumHeight(360)
        readiness_layout = QVBoxLayout(readiness_panel)
        readiness_layout.setContentsMargins(12, 12, 12, 12)
        readiness_layout.setSpacing(8)
        readiness_title = QLabel("Profile readiness")
        readiness_title.setObjectName("ProfileReadinessTitle")
        readiness_layout.addWidget(readiness_title)
        self.profile_readiness_values: dict[str, QLabel] = {}
        for key, label_text in (
            ("manifest", "Video settings"),
            ("models", "DLC models"),
            ("calibration", "Calibration"),
            ("analysis", "Gait settings"),
            ("knee", "Knee settings"),
        ):
            row = QHBoxLayout()
            row.setSpacing(6)
            label = QLabel(label_text)
            label.setObjectName("ProfileReadinessLabel")
            row.addWidget(label)
            value = QLabel()
            value.setObjectName("ProfileReadinessValue")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(value, 1)
            readiness_layout.addLayout(row)
            self.profile_readiness_values[key] = value
        readiness_layout.addStretch(1)

        self.status_label = QLabel("Start with the video processing manifest in step 1.")
        self.status_label.setObjectName("ProfileStatusLabel")
        self.status_label.setWordWrap(True)
        readiness_layout.addWidget(self.status_label)
        self.save_profile_button = QPushButton("Save new profile")
        self.save_profile_button.setObjectName("PrimaryButton")
        self.save_profile_button.setToolTip(
            "Validate the required inputs and save them together as a reusable profile. "
            "Saving a profile does not start the pipeline."
        )
        readiness_layout.addWidget(self.save_profile_button)

        setup_layout = QHBoxLayout()
        setup_layout.setSpacing(10)
        setup_layout.addWidget(self.configuration_tabs, 1)
        setup_layout.addWidget(readiness_panel)
        self.configuration_tabs.setMinimumHeight(230)
        self.configuration_tabs.setMaximumHeight(360)
        configuration_layout.addLayout(setup_layout)
        configuration_layout.addStretch(1)
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
            stage_row.addWidget(card, 1)
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
        layout.addWidget(self.pipeline_review_panel, 1)
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
        self.manifest_upload_button.clicked.connect(self._choose_processing_manifest)
        self.calibration_upload_button.clicked.connect(self._choose_calibration_map)
        self.analysis_manifest_upload_button.clicked.connect(self._choose_analysis_manifest)
        self.knee_manifest_upload_button.clicked.connect(self._choose_knee_manifest)
        self.include_gait_analysis_button.toggled.connect(
            self._profile_stage_options_changed
        )
        self.include_knee_correction_button.toggled.connect(
            self._profile_stage_options_changed
        )
        self.save_profile_button.clicked.connect(self._save_profile)
        self.upload_videos_button.clicked.connect(self._choose_videos)
        self.remove_videos_button.clicked.connect(self._remove_selected_videos)
        self.clear_videos_button.clicked.connect(self._clear_videos)
        self.video_list.paths_dropped.connect(self._add_video_paths)
        self.video_list.itemEntered.connect(self._start_hover_preview)
        self.video_list.pointer_left.connect(self._stop_hover_preview)
        self.video_list.itemDoubleClicked.connect(self._open_large_video_preview)
        self.run_pipeline_button.clicked.connect(self._toggle_pipeline_run)
        self.open_pipeline_output_button.clicked.connect(self._open_pipeline_output)
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
                gait_analysis_enabled=source.gait_analysis_enabled,
                knee_correction_enabled=source.knee_correction_enabled,
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
        blockers = (
            QSignalBlocker(self.include_gait_analysis_button),
            QSignalBlocker(self.include_knee_correction_button),
        )
        self.include_gait_analysis_button.setChecked(True)
        self.include_knee_correction_button.setChecked(False)
        del blockers
        self._apply_profile_stage_option_state()
        self._sync_run_options_to_profile(None)
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
        blockers = (
            QSignalBlocker(self.include_gait_analysis_button),
            QSignalBlocker(self.include_knee_correction_button),
        )
        self.include_gait_analysis_button.setChecked(profile.gait_analysis_enabled)
        self.include_knee_correction_button.setChecked(profile.knee_correction_enabled)
        del blockers
        self._apply_profile_stage_option_state()
        self._sync_run_options_to_profile(profile)
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
            str(self._project_root / "outputs" / "manual_pipeline" / "processed_videos"),
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
            str(self._project_root / "outputs" / "calibration"),
            "Calibration map (conversion_factor_map.json);;JSON files (*.json);;All files (*)",
        )
        if path:
            self._calibration_source = Path(path).expanduser().resolve()
            self._refresh_paths()
            self.status_label.setText("Calibration selected. Add the gait manifest and optional knee manifest below it.")

    def _profile_stage_options_changed(self, _checked: bool = False) -> None:
        self._apply_profile_stage_option_state()
        self._refresh_profile_readiness()
        included = []
        if self.include_gait_analysis_button.isChecked():
            included.append("gait analysis")
        if self.include_knee_correction_button.isChecked():
            included.append("knee correction")
        self.status_label.setText(
            "Included: " + (", ".join(included) if included else "video processing and DLC only")
        )

    def _apply_profile_stage_option_state(self) -> None:
        gait_enabled = self.include_gait_analysis_button.isChecked()
        knee_enabled = self.include_knee_correction_button.isChecked()
        for widget in (
            self.calibration_path_label,
            self.open_calibration_settings_button,
            self.calibration_upload_button,
            self.analysis_manifest_path_label,
            self.open_gait_settings_button,
            self.analysis_manifest_upload_button,
        ):
            widget.setEnabled(gait_enabled)
        for widget in (
            self.knee_manifest_path_label,
            self.open_knee_settings_button,
            self.knee_manifest_upload_button,
        ):
            widget.setEnabled(knee_enabled)

    def _sync_run_options_to_profile(
        self,
        profile: AutomatedPipelineProfile | None,
    ) -> None:
        blockers = (
            QSignalBlocker(self.skip_knee_correction_button),
            QSignalBlocker(self.skip_gait_analysis_button),
        )
        if profile is None:
            self.skip_knee_correction_button.setChecked(False)
            self.skip_gait_analysis_button.setChecked(False)
        else:
            self.skip_knee_correction_button.setChecked(
                not profile.knee_correction_enabled
            )
            self.skip_gait_analysis_button.setChecked(not profile.gait_analysis_enabled)
        del blockers
        self._refresh_run_option_enabled_state(profile)

    def _refresh_run_option_enabled_state(
        self,
        profile: AutomatedPipelineProfile | None = None,
    ) -> None:
        if profile is None:
            profile = self._profiles.get(self._current_profile_id or "")
        profile_knee_enabled = profile is None or profile.knee_correction_enabled
        profile_gait_enabled = profile is None or profile.gait_analysis_enabled
        self.skip_knee_correction_button.setEnabled(
            not self._pipeline_running and profile_knee_enabled
        )
        self.skip_gait_analysis_button.setEnabled(
            not self._pipeline_running and profile_gait_enabled
        )

    def _choose_analysis_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose gait analysis manifest",
            str(self._project_root / "outputs" / "manual_pipeline" / "gait_analysis"),
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
        self.include_gait_analysis_button.setChecked(True)
        self._refresh_paths()
        self.status_label.setText("Gait analysis settings selected. Save the profile when ready.")
        return True

    def _choose_knee_manifest(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose knee analysis manifest",
            str(self._project_root / "outputs" / "manual_pipeline" / "knee_correction"),
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
        self.include_knee_correction_button.setChecked(True)
        self._refresh_paths()
        self.status_label.setText("Knee analysis settings selected. Save the profile when ready.")
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
        lowered = message.lower()
        if any(token in lowered for token in ("error", "failed", "changes required")):
            accent = theme.STATUS_ERROR
        elif any(token in lowered for token in ("complete", "confirmed", "ready")):
            accent = theme.STATUS_READY
        elif any(token in lowered for token in ("review", "manual check", "resume")):
            accent = theme.STATUS_RUNNING
        else:
            accent = theme.TEXT

        cursor = self.automation_console.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        prefix_end = message.find("]") + 1
        if prefix_end > 0:
            prefix_format = QTextCharFormat()
            prefix_format.setForeground(QColor(accent))
            cursor.insertText(message[:prefix_end], prefix_format)
            body_format = QTextCharFormat()
            body_format.setForeground(QColor(theme.TEXT))
            cursor.insertText(message[prefix_end:], body_format)
        else:
            line_format = QTextCharFormat()
            line_format.setForeground(QColor(accent))
            cursor.insertText(message, line_format)
        self.automation_console.setTextCursor(cursor)
        self.automation_console.ensureCursorVisible()

    def _set_pipeline_log_state(self, text: str, state: str) -> None:
        self.pipeline_log_state.setText(text)
        self.pipeline_log_state.setProperty("logState", state)
        self.pipeline_log_state.style().unpolish(self.pipeline_log_state)
        self.pipeline_log_state.style().polish(self.pipeline_log_state)

    def _toggle_pipeline_run(self) -> None:
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.request_cancel()
            self.run_pipeline_button.setText("Stopping")
            self.run_pipeline_button.setEnabled(False)
            self.run_readiness_label.setText("Stopping after current operation")
            self._append_console("[Pipeline] Stop requested; waiting for the current operation.")
            return
        if self._pipeline_real_complete:
            self._pipeline_real_complete = False
            self._pipeline_demo_blocked_stage = None
            self._pipeline_demo_waiting_for_review = None
            self.set_pipeline_running(False)
            self.run_pipeline_button.setText("RUN pipeline")
            self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
            self.run_pipeline_button.setEnabled(True)
            self.run_readiness_label.setText("Ready")
            return

        profile = self._profiles.get(self._current_profile_id or "")
        if profile is None or not self._video_paths:
            self._toggle_pipeline_demo()
            return
        self._start_pipeline(profile)

    def _start_pipeline(self, profile: AutomatedPipelineProfile) -> None:
        self._pipeline_real_complete = False
        self._pipeline_real_waiting_for_review = None
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_demo_blocked_stage = None
        self._pipeline_review_artifacts = None
        self._pipeline_stickplot_path = None
        self._pipeline_stickplot_pixmap = None
        self._pipeline_output_folder = None
        self.open_pipeline_output_button.setText("Open outputs")
        self.open_pipeline_output_button.setToolTip(str(self._automated_output_root))
        self._pipeline_skipped_stages.clear()
        self.pipeline_review_panel.hide()
        self.automation_console.clear()
        self.set_pipeline_running(True)
        self.run_pipeline_button.setText("Stop pipeline")
        self.run_pipeline_button.setToolTip(
            "Stop after the currently running external operation finishes."
        )
        self.run_pipeline_button.setEnabled(True)
        self.run_readiness_label.setText("Running")
        self._append_console(
            f'[Pipeline] Running profile "{profile.name}" on {len(self._video_paths)} video(s).'
        )
        excluded = []
        if self.skip_knee_correction_button.isChecked():
            excluded.append("knee correction")
        if self.skip_gait_analysis_button.isChecked():
            excluded.append("gait analysis")
        if excluded:
            self._append_console(f"[Pipeline] Excluding {', '.join(excluded)} from this run.")

        worker = AutomatedPipelineWorker(
            profile,
            list(self._video_paths),
            self._project_root,
            enable_knee_correction=not self.skip_knee_correction_button.isChecked(),
            enable_gait_analysis=not self.skip_gait_analysis_button.isChecked(),
            parent=self,
        )
        self._pipeline_worker = worker
        worker.stage_started.connect(self._pipeline_stage_started)
        worker.output_folder_ready.connect(self._pipeline_output_folder_ready)
        worker.stage_progress.connect(self._pipeline_stage_progressed)
        worker.stage_skipped.connect(self._pipeline_stage_skipped)
        worker.log_message.connect(lambda message: self._append_console(f"[Pipeline] {message}."))
        worker.review_requested.connect(self._pipeline_review_requested)
        worker.run_completed.connect(self._pipeline_run_completed)
        worker.run_failed.connect(self._pipeline_run_failed)
        worker.run_cancelled.connect(self._pipeline_run_cancelled)
        worker.finished.connect(lambda: self._pipeline_worker_finished(worker))
        worker.start()

    def _pipeline_output_folder_ready(self, output_folder: object) -> None:
        self._pipeline_output_folder = Path(output_folder).expanduser().resolve()
        self.open_pipeline_output_button.setText("Open run output")
        self.open_pipeline_output_button.setToolTip(str(self._pipeline_output_folder))
        self.pipeline_current_stage_label.setToolTip(str(self._pipeline_output_folder))

    def _open_pipeline_output(self) -> None:
        output_folder = self._pipeline_output_folder or self._automated_output_root
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_folder)))

    def _pipeline_stage_started(self, stage_index: int, label: str) -> None:
        activity = PIPELINE_STAGE_ACTIVITY[stage_index]
        self.set_pipeline_stage(
            stage_index,
            progress=0,
            processed_videos=0 if stage_index == 0 else None,
            total_videos=len(self._video_paths) if stage_index == 0 else None,
            status_text=activity,
        )
        self.pipeline_current_stage_label.setText(activity)
        self.pipeline_current_stage_label.setToolTip("")
        self.run_readiness_label.setText(label)

    def _pipeline_stage_progressed(
        self,
        stage_index: int,
        current: int,
        total: int,
        message: str,
    ) -> None:
        progress = None if total <= 0 else (max(0, current) / max(1, total)) * 100.0
        activity = message or PIPELINE_STAGE_ACTIVITY[stage_index]
        compact_activity = activity
        if stage_index == 1 and ":" in compact_activity:
            compact_activity = compact_activity.split(":", 1)[0]
        self.set_pipeline_stage(
            stage_index,
            progress=progress,
            processed_videos=current if stage_index == 0 else None,
            total_videos=total if stage_index == 0 else None,
            status_text=compact_activity,
        )
        self.pipeline_current_stage_label.setText(activity)
        self.pipeline_current_stage_label.setToolTip(activity)
        if message and stage_index != 1:
            self._append_console(f"[{PIPELINE_STAGE_LABELS[stage_index]}] {message}.")

    def _pipeline_stage_skipped(self, stage_index: int, reason: str) -> None:
        self._pipeline_skipped_stages.add(stage_index)
        card = self.pipeline_stage_cards[stage_index]
        card.setProperty("pipelineState", "skipped")
        card.style().unpolish(card)
        card.style().polish(card)
        self.pipeline_stage_status_labels[stage_index].setText("Skipped")
        if stage_index in PIPELINE_REVIEW_GATES:
            self.pipeline_stage_review_labels[stage_index].setText("Not included")
        self._set_pipeline_stage_progress(stage_index, 0, False, "primary")
        self._append_console(f"[Skipped] {reason}.")

    def _pipeline_review_requested(self, stage_index: int, artifacts: object) -> None:
        self._pipeline_real_waiting_for_review = stage_index
        self._pipeline_review_artifacts = artifacts if isinstance(artifacts, dict) else None
        self._pause_for_pipeline_review(stage_index, self._pipeline_review_artifacts)

    def _pipeline_run_completed(self, result: object) -> None:
        self._pipeline_real_waiting_for_review = None
        self._pipeline_real_complete = True
        self.complete_pipeline("Pipeline complete")
        self.run_pipeline_button.setText("Back to videos")
        self.run_pipeline_button.setToolTip("Return to the video queue.")
        self.run_pipeline_button.setEnabled(True)
        self.run_readiness_label.setText("Complete")
        output_folder = getattr(result, "output_folder", None)
        if output_folder is not None:
            self._pipeline_output_folder_ready(output_folder)
            self._append_console(f"[Complete] Results saved to {output_folder}.")
        output_manifest = getattr(result, "output_manifest", None)
        if output_manifest is not None:
            self._append_console(f"[Complete] Run manifest: {output_manifest}.")

    def _pipeline_run_failed(self, stage_index: int, message: str) -> None:
        self._pipeline_real_waiting_for_review = None
        self._pipeline_real_complete = True
        self.pipeline_review_panel.hide()
        self.pipeline_activity_panel.show()
        self.pipeline_progress_bar.set_active(False)
        self.pipeline_progress_bar.set_accent_role("error")
        self._set_pipeline_log_state("Failed", "error")
        if 0 <= stage_index < len(self.pipeline_stage_cards):
            card = self.pipeline_stage_cards[stage_index]
            card.setProperty("pipelineState", "blocked")
            card.style().unpolish(card)
            card.style().polish(card)
            self.pipeline_stage_status_labels[stage_index].setText("Failed")
            self._set_pipeline_stage_progress(stage_index, 100, False, "error")
        self.run_pipeline_button.setText("Back to videos")
        self.run_pipeline_button.setToolTip("Return to the queue, correct the profile, and run again.")
        self.run_pipeline_button.setEnabled(True)
        self.run_readiness_label.setText("Failed")
        self._append_console(f"[Failed] {message}")

    def _pipeline_run_cancelled(self) -> None:
        if self._pipeline_demo_blocked_stage is not None:
            return
        self._pipeline_real_waiting_for_review = None
        self._pipeline_real_complete = False
        self.pipeline_review_panel.hide()
        self.set_pipeline_running(False)
        self.run_pipeline_button.setText("RUN pipeline")
        self.run_pipeline_button.setToolTip(RUN_PREVIEW_TOOLTIP)
        self.run_pipeline_button.setEnabled(True)
        self.run_readiness_label.setText("Stopped")
        self._append_console("[Pipeline] Stopped.")

    def _pipeline_worker_finished(self, worker: AutomatedPipelineWorker) -> None:
        if self._pipeline_worker is worker:
            self._pipeline_worker = None
        worker.deleteLater()

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
        self.pipeline_activity_panel.show()
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

    def _pause_for_pipeline_review(
        self,
        stage_index: int,
        artifacts: dict[str, object] | None = None,
    ) -> None:
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._pipeline_demo_timer.stop()
        self._pipeline_demo_waiting_for_review = stage_index
        self._set_pipeline_overview_compact(True)
        self.pipeline_review_title.setText(str(gate["title"]))
        self.pipeline_review_description.setText(str(gate["description"]))
        self._populate_pipeline_review_preview(stage_index, artifacts)
        self.pipeline_change_settings_button.hide()
        self.pipeline_needs_changes_button.show()
        self.pipeline_approve_button.show()
        self.pipeline_activity_panel.hide()
        self.pipeline_review_panel.show()
        self._set_pipeline_log_state("Review", "review")
        self.pipeline_stage_status_labels[stage_index].setText("Awaiting confirmation")
        self.pipeline_stage_review_labels[stage_index].setText("Awaiting review")
        self.pipeline_progress_bar.set_active(False)
        self._set_pipeline_stage_progress(stage_index, 100, False, "ready")
        self.run_pipeline_button.setText("Awaiting confirmation")
        self.run_pipeline_button.setEnabled(False)
        self.run_pipeline_button.setToolTip(
            "The walkthrough is paused. Use Confirm and continue or Needs changes in the review panel."
        )
        self.run_readiness_label.setText("Review required")
        self._append_console(f"[Manual check] {gate['title']}. Pipeline paused.")

    def _populate_pipeline_review_preview(
        self,
        stage_index: int,
        artifacts: dict[str, object] | None = None,
    ) -> None:
        if artifacts is not None:
            self._populate_real_pipeline_review_preview(stage_index, artifacts)
            return
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
                item.setData(Qt.UserRole + 4, "All regions")
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
                    item.setData(Qt.UserRole + 4, component)
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

    def _populate_real_pipeline_review_preview(
        self,
        stage_index: int,
        artifacts: dict[str, object],
    ) -> None:
        raw_items = artifacts.get("items", [])
        items = raw_items if isinstance(raw_items, list) else []
        if stage_index == 3:
            image_paths = [Path(path) for path in items if Path(path).is_file()]
            self._pipeline_stickplot_path = image_paths[0] if image_paths else None
            pixmap = (
                _pixmap_from_image_file(self._pipeline_stickplot_path, 640, 240)
                if self._pipeline_stickplot_path is not None
                else None
            )
            self._pipeline_stickplot_pixmap = pixmap
            if pixmap is None or pixmap.isNull():
                self.pipeline_stickplot_preview.setPixmap(QPixmap())
                self.pipeline_stickplot_preview.setText("No stickplot image was produced")
            else:
                self.pipeline_stickplot_preview.setText("")
                self.pipeline_stickplot_preview.setPixmap(pixmap)
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_stickplot_preview
            )
            return

        normalized = [item for item in items if isinstance(item, dict)]
        if stage_index == 0:
            self.pipeline_review_video_list.clear()
            for item_data in normalized:
                self._add_real_review_video_item(self.pipeline_review_video_list, item_data)
            self.pipeline_review_preview_stack.setCurrentWidget(
                self.pipeline_review_video_list
            )
            return

        self.pipeline_component_video_lists.clear()
        while self.pipeline_component_tabs.count():
            page = self.pipeline_component_tabs.widget(0)
            self.pipeline_component_tabs.removeTab(0)
            page.deleteLater()
        views = []
        for item_data in normalized:
            view = str(item_data.get("view", "Full frame"))
            if view not in views:
                views.append(view)
        for view in views:
            component_list = QListWidget()
            component_list.setObjectName("PipelineReviewVideoList")
            component_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            component_list.itemDoubleClicked.connect(self._open_pipeline_review_video)
            self.pipeline_component_tabs.addTab(component_list, view)
            self.pipeline_component_video_lists[view] = component_list
            for item_data in normalized:
                if str(item_data.get("view", "Full frame")) == view:
                    self._add_real_review_video_item(component_list, item_data)
        self.pipeline_review_preview_stack.setCurrentWidget(self.pipeline_component_tabs)

    def _add_real_review_video_item(
        self,
        target: QListWidget,
        item_data: dict,
    ) -> None:
        path = Path(item_data.get("path", ""))
        title = str(item_data.get("title") or path.name)
        view = str(item_data.get("view") or "Full frame")
        details = f"View: {view}"
        item = QListWidgetItem(f"{title}  —  {details}")
        item.setData(Qt.UserRole, str(path))
        item.setData(Qt.UserRole + 1, details)
        item.setData(Qt.UserRole + 2, title)
        item.setData(Qt.UserRole + 4, view)
        item.setToolTip("Double-click to inspect this generated video.")
        target.addItem(item)

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
        title = str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0])
        details = str(item.data(Qt.UserRole + 1) or "")
        review_sources, selected_index = self._pipeline_review_sources(item)
        try:
            if review_sources:
                dialog: QDialog = AutomationVideoPreviewDialog(
                    review_sources[selected_index].path,
                    self,
                    review_sources=review_sources,
                    initial_source_index=selected_index,
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

    def _pipeline_review_sources(
        self,
        selected_item: QListWidgetItem,
    ) -> tuple[tuple[ReviewVideoSource, ...], int]:
        selected_list = selected_item.listWidget()
        if selected_list is self.pipeline_review_video_list:
            review_lists = (("All regions", self.pipeline_review_video_list),)
        else:
            review_lists = tuple(self.pipeline_component_video_lists.items())

        sources: list[ReviewVideoSource] = []
        selected_index = 0
        for fallback_view, review_list in review_lists:
            for row in range(review_list.count()):
                item = review_list.item(row)
                if item.data(Qt.UserRole + 3) == "component_header":
                    continue
                path_text = str(item.data(Qt.UserRole) or "")
                path = Path(path_text) if path_text else None
                if path is None or not path.is_file():
                    continue
                source = ReviewVideoSource(
                    path=path,
                    title=str(item.data(Qt.UserRole + 2) or item.text().splitlines()[0]),
                    details=str(item.data(Qt.UserRole + 1) or ""),
                    view_name=str(item.data(Qt.UserRole + 4) or fallback_view),
                )
                if item is selected_item:
                    selected_index = len(sources)
                sources.append(source)
        return tuple(sources), selected_index

    def _open_large_stickplot_preview(self) -> None:
        pixmap = None
        if self._pipeline_stickplot_path is not None:
            pixmap = _pixmap_from_image_file(self._pipeline_stickplot_path, 1200, 700)
        if pixmap is None or pixmap.isNull():
            pixmap = _demo_stickplot_pixmap(1200, 700)
        self._show_large_review_dialog(
            PipelineImagePreviewDialog(
                "Generated stickplot preview",
                pixmap,
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
        real_review = self._pipeline_real_waiting_for_review == stage_index
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_real_waiting_for_review = None
        self.pipeline_review_panel.hide()
        self.run_pipeline_button.setEnabled(True)
        if real_review and self._pipeline_worker is not None:
            self.run_pipeline_button.setText("Stop pipeline")
            self.run_pipeline_button.setToolTip(
                "Stop after the currently running external operation finishes."
            )
            self.run_readiness_label.setText("Continuing")
            self._append_console(f"[Confirmed] {PIPELINE_STAGES[stage_index]}.")
            self._pipeline_worker.approve_review()
            return
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
        real_review = self._pipeline_real_waiting_for_review == stage_index
        gate = PIPELINE_REVIEW_GATES[stage_index]
        self._pipeline_demo_waiting_for_review = None
        self._pipeline_real_waiting_for_review = None
        self._pipeline_demo_blocked_stage = stage_index
        self._set_pipeline_log_state("Paused", "paused")
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
        self.run_pipeline_button.setEnabled(True)
        if real_review:
            self._pipeline_real_complete = True
            self.run_pipeline_button.setText("Back to videos")
            self.run_pipeline_button.setToolTip(
                "Return to the queue. The next run will use the corrected profile."
            )
            if self._pipeline_worker is not None:
                self._pipeline_worker.reject_review()
        else:
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
        self._refresh_run_option_enabled_state()
        if running:
            self._set_pipeline_overview_compact(True)
            self._stop_hover_preview()
            self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
            if self._pipeline_demo_waiting_for_review is None:
                self.pipeline_activity_panel.show()
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
            self._pipeline_skipped_stages.clear()
            self._set_pipeline_overview_compact(False)
            self.automation_input_stack.setCurrentWidget(self.video_panel)
            self.pipeline_progress_bar.set_active(False)
            self._set_pipeline_log_state("Ready", "ready")

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
        self._set_pipeline_overview_compact(True)
        if self._pipeline_demo_waiting_for_review is None:
            self.pipeline_review_panel.hide()
            self.pipeline_activity_panel.show()
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        self._set_pipeline_log_state("Running", "running")
        active_status = status_text or "In progress"
        stage_progress = None if progress is None else max(0.0, min(100.0, float(progress)))
        for index, (card, label, review_label) in enumerate(
            zip(
                self.pipeline_stage_cards,
                self.pipeline_stage_status_labels,
                self.pipeline_stage_review_labels,
            )
        ):
            if index < stage_index and index in self._pipeline_skipped_stages:
                state, text = "skipped", "Skipped"
                self._set_pipeline_stage_progress(index, 0, False, "primary")
            elif index < stage_index:
                state, text = "complete", "Complete"
                self._set_pipeline_stage_progress(index, 100, False, "ready")
            elif index == stage_index:
                text = active_status
                if stage_progress is not None:
                    text = f"{active_status} {stage_progress:g}%"
                state = "active"
                self._set_pipeline_stage_progress(index, stage_progress, True, "running")
            else:
                state, text = "pending", "Waiting"
                self._set_pipeline_stage_progress(index, 0, False, "primary")
            card.setProperty("pipelineState", state)
            label.setText(text)
            if index in PIPELINE_REVIEW_GATES:
                if index in self._pipeline_skipped_stages:
                    review_label.setText("Not included")
                else:
                    review_label.setText(
                        "Reviewed" if index < stage_index else "Review required"
                    )
            card.style().unpolish(card)
            card.style().polish(card)

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
            self.pipeline_progress_bar.setFormat("Working")
            return

        overall = round(((stage_index + stage_progress / 100.0) / len(PIPELINE_STAGES)) * 100)
        self.pipeline_progress_bar.set_accent_role("running")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(overall)
        self.pipeline_progress_bar.set_active(True)
        self.pipeline_progress_bar.setFormat("%p%")

    def _set_pipeline_overview_compact(self, compact: bool) -> None:
        if compact:
            target_height = max(380, min(760, self.height() - 160))
            self.automation_input_stack.setMinimumHeight(target_height)
            self.automation_input_stack.setMaximumHeight(target_height)
            self.automation_console_panel.setMinimumHeight(target_height)
            self.automation_console_panel.setMaximumHeight(target_height)
            return
        self.automation_input_stack.setMinimumHeight(
            self._automation_input_default_minimum_height
        )
        self.automation_input_stack.setMaximumHeight(
            self._automation_input_default_maximum_height
        )
        self.automation_console_panel.setMinimumHeight(
            self._automation_console_default_minimum_height
        )
        self.automation_console_panel.setMaximumHeight(
            self._automation_console_default_maximum_height
        )

    def complete_pipeline(self, status_text: str = "Pipeline complete") -> None:
        self._pipeline_running = False
        self.automation_input_stack.setCurrentWidget(self.pipeline_status_panel)
        self.pipeline_review_panel.hide()
        self.pipeline_activity_panel.show()
        for index, (card, label, review_label) in enumerate(zip(
            self.pipeline_stage_cards,
            self.pipeline_stage_status_labels,
            self.pipeline_stage_review_labels,
        )):
            skipped = index in self._pipeline_skipped_stages
            card.setProperty("pipelineState", "skipped" if skipped else "complete")
            label.setText("Skipped" if skipped else "Complete")
            if review_label.text():
                review_label.setText("Not included" if skipped else "Reviewed")
            self._set_pipeline_stage_progress(
                index,
                0 if skipped else 100,
                False,
                "primary" if skipped else "ready",
            )
            card.style().unpolish(card)
            card.style().polish(card)
        self.pipeline_progress_bar.set_accent_role("ready")
        self.pipeline_progress_bar.setRange(0, 100)
        self.pipeline_progress_bar.setValue(100)
        self.pipeline_progress_bar.set_active(False)
        self.pipeline_progress_bar.setFormat("%p%")
        self._set_pipeline_log_state("Complete", "complete")

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
        if self._pipeline_worker is not None and self._pipeline_worker.isRunning():
            self._pipeline_worker.request_cancel()
            self._pipeline_worker.wait()
        self._release_hover_capture()
        if self._large_preview_dialog is not None:
            self._large_preview_dialog.close()
        if self._large_review_dialog is not None:
            self._large_review_dialog.close()
        super().closeEvent(event)

    def _choose_model_file(self, region: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose DeepLabCut config for {region}",
            str(Path.home()),
            "DeepLabCut config (config.yaml);;YAML files (*.yaml);;All files (*)",
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
        self._refresh_profile_readiness()
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
            file_button = QPushButton("Choose config")
            file_button.setToolTip(
                f"Choose config.yaml from the trained DeepLabCut project for {region}."
            )
            file_button.clicked.connect(lambda _checked=False, name=region: self._choose_model_file(name))
            layout.addWidget(file_button)
            folder_button = QPushButton("Choose project")
            folder_button.setToolTip(
                f"Choose the complete trained DeepLabCut project folder for {region}."
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
        self._refresh_profile_readiness()

    def _refresh_profile_readiness(self) -> None:
        gait_enabled = self.include_gait_analysis_button.isChecked()
        knee_enabled = self.include_knee_correction_button.isChecked()
        selected_models = sum(path is not None for path in self._model_sources.values())
        total_models = len(self._regions)
        model_state = "ready" if total_models and selected_models == total_models else "missing"
        model_text = (
            f"{selected_models} / {total_models} selected"
            if total_models
            else "Needs manifest"
        )
        self._set_profile_readiness_value(
            "manifest",
            "Selected" if self._manifest_source is not None else "Required",
            "ready" if self._manifest_source is not None else "missing",
        )
        self._set_profile_readiness_value("models", model_text, model_state)
        self._set_profile_readiness_value(
            "calibration",
            (
                "Selected"
                if gait_enabled and self._calibration_source is not None
                else "Required" if gait_enabled else "Excluded"
            ),
            (
                "ready"
                if gait_enabled and self._calibration_source is not None
                else "missing" if gait_enabled else "optional"
            ),
        )
        self._set_profile_readiness_value(
            "analysis",
            (
                "Selected"
                if gait_enabled and self._analysis_manifest_source is not None
                else "Required" if gait_enabled else "Excluded"
            ),
            (
                "ready"
                if gait_enabled and self._analysis_manifest_source is not None
                else "missing" if gait_enabled else "optional"
            ),
        )
        self._set_profile_readiness_value(
            "knee",
            (
                "Selected"
                if knee_enabled and self._knee_manifest_source is not None
                else "Required" if knee_enabled else "Excluded"
            ),
            (
                "ready"
                if knee_enabled and self._knee_manifest_source is not None
                else "missing" if knee_enabled else "optional"
            ),
        )

    def _set_profile_readiness_value(self, key: str, text: str, state: str) -> None:
        label = self.profile_readiness_values[key]
        if label.text() == text and label.property("readinessState") == state:
            return
        label.setText(text)
        label.setProperty("readinessState", state)
        label.style().unpolish(label)
        label.style().polish(label)

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
        gait_enabled = self.include_gait_analysis_button.isChecked()
        knee_enabled = self.include_knee_correction_button.isChecked()
        if gait_enabled and self._calibration_source is None:
            QMessageBox.warning(self, "Calibration required", "Complete step 3 by uploading a calibration map.")
            return
        if gait_enabled and self._analysis_manifest_source is None:
            QMessageBox.warning(
                self,
                "Analysis manifest required",
                "Complete step 3 by uploading a gait analysis manifest.",
            )
            return
        if knee_enabled and self._knee_manifest_source is None:
            QMessageBox.warning(
                self,
                "Knee manifest required",
                "Upload a knee analysis manifest or turn off Knee correction.",
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
                self._calibration_source if gait_enabled else None,
                {region: path for region, path in self._model_sources.items() if path is not None},
                profile_id=self._current_profile_id,
                analysis_manifest=self._analysis_manifest_source if gait_enabled else None,
                knee_manifest=self._knee_manifest_source if knee_enabled else None,
                gait_analysis_enabled=gait_enabled,
                knee_correction_enabled=knee_enabled,
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
            "1" if self.include_gait_analysis_button.isChecked() else "0",
            "1" if self.include_knee_correction_button.isChecked() else "0",
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
                QFrame#ProfileConfigurationToolbar, QFrame#ProfileManagementPanel,
                QFrame#ProfileReadinessPanel {
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
                    font-size: 13px;
                }
                QLabel#ProfileReadinessTitle {
                    color: {theme.TEXT};
                    font-size: 15px;
                    font-weight: 650;
                }
                QLabel#ProfileReadinessLabel {
                    color: {theme.TEXT};
                    font-size: 13px;
                }
                QLabel#ProfileReadinessValue {
                    color: {theme.CONNECTOR};
                    font-size: 13px;
                    font-weight: 650;
                }
                QLabel#ProfileReadinessValue[readinessState="ready"] {
                    color: {theme.STATUS_READY};
                }
                QLabel#ProfileReadinessValue[readinessState="missing"] {
                    color: {theme.STATUS_ERROR};
                }
                QLabel#ProfileReadinessValue[readinessState="optional"] {
                    color: {theme.CONNECTOR};
                }
                QLabel#AutomationPanelTitle {
                    color: {theme.TEXT};
                    font-size: 15px;
                    font-weight: 650;
                }
                QLabel#VideoCountLabel {
                    color: {theme.CONNECTOR};
                    font-size: 13px;
                }
                QLabel#FieldLabel, QLabel#RegionName {
                    color: {theme.TEXT};
                    font-weight: 600;
                    min-width: 48px;
                }
                QFrame#VideoDropPanel {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                QFrame#AutomationConsolePanel {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 3px;
                }
                QFrame#PipelineStatusPanel {
                    background: transparent;
                    border: 0;
                }
                QFrame#PipelineActivityPanel {
                    background: transparent;
                    border: 0;
                }
                QStackedWidget#AutomationInputStack {
                    background: {theme.BACKGROUND};
                    border: 0;
                }
                QFrame#PipelineStageCard {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                }
                QFrame#PipelineStageCard[pipelineState="active"] {
                    background: {theme.PANEL};
                    border: 1px solid {theme.STATUS_RUNNING};
                }
                QFrame#PipelineStageCard[pipelineState="complete"] {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.STATUS_READY};
                }
                QFrame#PipelineStageCard[pipelineState="skipped"] {
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                }
                QFrame#PipelineStageCard[pipelineState="blocked"] {
                    background: {theme.PANEL};
                    border: 1px solid {theme.STATUS_ERROR};
                }
                QProgressBar#PipelineStageProgress {
                    background: transparent;
                    border: 0;
                    min-width: 44px;
                    max-width: 44px;
                    min-height: 44px;
                    max-height: 44px;
                }
                QLabel#PipelineStageName {
                    color: {theme.TEXT};
                    font-size: 13px;
                    font-weight: 650;
                }
                QLabel#PipelineStageStatus, QLabel#PipelineVideoProgress {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QFrame#PipelineConnector {
                    background: {theme.BORDER};
                    border: 0;
                }
                QLabel#PipelineCurrentStage {
                    color: {theme.TEXT};
                    font-size: 17px;
                    font-weight: 700;
                }
                QLabel#PipelineStagePosition {
                    color: {theme.CONNECTOR};
                    font-size: 14px;
                }
                QProgressBar#PipelineProgressBar {
                    min-height: 28px;
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
                    font-size: 15px;
                    font-weight: 700;
                }
                QLabel#PipelineReviewDescription {
                    color: {theme.CONNECTOR};
                    font-size: 13px;
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
                    background: {theme.BACKGROUND};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    color: {theme.TEXT};
                    font-size: 12px;
                    padding: 12px;
                    selection-background-color: {theme.PANEL};
                    selection-color: {theme.TEXT};
                }
                QLabel#PipelineLogState {
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                }
                QLabel#PipelineLogState[logState="running"],
                QLabel#PipelineLogState[logState="review"] {
                    color: {theme.STATUS_RUNNING};
                }
                QLabel#PipelineLogState[logState="paused"],
                QLabel#PipelineLogState[logState="error"] {
                    color: {theme.STATUS_ERROR};
                }
                QLabel#PipelineLogState[logState="complete"] {
                    color: {theme.STATUS_READY};
                }
                QPushButton#PipelineOptionButton {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    color: {theme.TEXT};
                    font-size: 12px;
                    padding: 8px 11px;
                }
                QPushButton#PipelineOptionButton:hover {
                    background: {theme.PANEL};
                    border-color: {theme.CONNECTOR};
                }
                QPushButton#PipelineOptionButton:checked {
                    background: {theme.PANEL};
                    border-color: {theme.STATUS_ERROR};
                    color: {theme.STATUS_ERROR};
                    font-weight: 650;
                }
                QPushButton#PipelineOptionButton:disabled {
                    color: {theme.CONNECTOR};
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
                QScrollArea#ProfileModelsScroll {
                    background: transparent;
                    border: 0;
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
                QLabel#AssetPath:disabled {
                    background: {theme.PANEL};
                    color: {theme.BORDER};
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
                QPushButton#OpenManualToolButton {
                    background: {theme.SOFT};
                    border-color: {theme.PRIMARY};
                    color: {theme.PRIMARY};
                    font-size: 11px;
                    font-weight: 650;
                }
                QPushButton#OpenManualToolButton:hover {
                    background: {theme.SURFACE};
                    border-color: {theme.TEXT};
                    color: {theme.TEXT};
                }
                QPushButton#ProfileUploadButton {
                    background: {theme.PRIMARY};
                    border-color: {theme.PRIMARY};
                    color: {theme.PRIMARY_TEXT};
                    font-size: 11px;
                    font-weight: 650;
                }
                QPushButton#ProfileUploadButton:hover {
                    background: {theme.SOFT};
                    border-color: {theme.TEXT};
                    color: {theme.TEXT};
                }
                QPushButton#OpenManualToolButton:disabled,
                QPushButton#ProfileUploadButton:disabled {
                    background: {theme.PANEL};
                    border-color: {theme.BORDER};
                    color: {theme.CONNECTOR};
                }
                QPushButton#ProfileStageToggle {
                    background: {theme.SURFACE};
                    border: 1px solid {theme.BORDER};
                    color: {theme.CONNECTOR};
                    font-size: 12px;
                    padding: 7px 12px;
                }
                QPushButton#ProfileStageToggle:checked {
                    background: {theme.SOFT};
                    border-color: {theme.PRIMARY};
                    color: {theme.PRIMARY};
                    font-weight: 650;
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
        review_sources: tuple[ReviewVideoSource, ...] | None = None,
        initial_source_index: int = 0,
    ):
        if cv2 is None:
            raise OSError("OpenCV is not available for video preview.")
        super().__init__(parent)
        initial_path = path.expanduser().resolve()
        self._review_sources = review_sources or (
            ReviewVideoSource(initial_path, initial_path.name, subtitle or "", ""),
        )
        if not self._review_sources:
            raise ValueError("No videos are available for preview.")
        self._source_index = max(0, min(initial_source_index, len(self._review_sources) - 1))
        self._path = initial_path
        self._capture = None
        self._frame_count = 1
        self._fps = 0.0
        self._source_pixmap = QPixmap()

        self.setWindowTitle("Video preview")
        self.setMinimumSize(720, 500)
        self.resize(960, 680)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        self.title_label = QLabel()
        self.title_label.setObjectName("LargeVideoPreviewTitle")
        self.title_label.setWordWrap(True)
        root.addWidget(self.title_label)

        source_row = QHBoxLayout()
        source_row.setSpacing(6)
        self.previous_video_button = QToolButton()
        self.previous_video_button.setObjectName("VideoPreviewNavigationButton")
        self.previous_video_button.setText("←")
        self.previous_video_button.setToolTip("Previous preview video")
        source_row.addWidget(self.previous_video_button)
        self.source_selector = QComboBox()
        self.source_selector.setObjectName("VideoPreviewSourceSelector")
        self.source_selector.setToolTip("Switch the video shown in this preview window.")
        for source in self._review_sources:
            self.source_selector.addItem(source.title)
        source_row.addWidget(self.source_selector, 1)
        self.next_video_button = QToolButton()
        self.next_video_button.setObjectName("VideoPreviewNavigationButton")
        self.next_video_button.setText("→")
        self.next_video_button.setToolTip("Next preview video")
        source_row.addWidget(self.next_video_button)
        self.view_label = QLabel()
        self.view_label.setObjectName("VideoPreviewView")
        source_row.addWidget(self.view_label)
        root.addLayout(source_row)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("LargeVideoPreviewSubtitle")
        self.subtitle_label.setWordWrap(True)
        root.addWidget(self.subtitle_label)
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
        self.source_selector.currentIndexChanged.connect(self._select_review_source)
        self.previous_video_button.clicked.connect(
            lambda _checked=False: self._select_review_source(self._source_index - 1)
        )
        self.next_video_button.clicked.connect(
            lambda _checked=False: self._select_review_source(self._source_index + 1)
        )
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
                QLabel#VideoPreviewView {
                    background: {theme.PANEL};
                    border: 1px solid {theme.BORDER};
                    border-radius: 2px;
                    color: {theme.TEXT};
                    font-size: 11px;
                    font-weight: 650;
                    padding: 3px 6px;
                }
                QComboBox#VideoPreviewSourceSelector {
                    min-width: 260px;
                }
                QToolButton#VideoPreviewNavigationButton {
                    min-width: 28px;
                    min-height: 26px;
                    font-size: 16px;
                    font-weight: 700;
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
        self._select_review_source(self._source_index)

    def _select_review_source(self, index: int) -> None:
        index = max(0, min(index, len(self._review_sources) - 1))
        source = self._review_sources[index]
        capture = cv2.VideoCapture(str(source.path))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"Could not open video: {source.path.name}")
        if self._capture is not None:
            self._capture.release()
        self._capture = capture
        self._source_index = index
        self._path = source.path
        frame_count_value = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps_value = capture.get(cv2.CAP_PROP_FPS)
        self._frame_count = max(1, int(frame_count_value)) if frame_count_value > 0 else 1
        self._fps = float(fps_value) if fps_value > 0 else 0.0
        self.setWindowTitle(f"Video preview — {source.title}")
        self.title_label.setText(source.title)
        self.subtitle_label.setText(source.details)
        self.subtitle_label.setVisible(bool(source.details))
        self.view_label.setText(f"View: {source.view_name}")
        self.view_label.setVisible(bool(source.view_name))
        self.previous_video_button.setEnabled(index > 0)
        self.next_video_button.setEnabled(index < len(self._review_sources) - 1)
        source_blocker = QSignalBlocker(self.source_selector)
        self.source_selector.setCurrentIndex(index)
        del source_blocker
        slider_blocker = QSignalBlocker(self.frame_slider)
        self.frame_slider.setRange(0, self._frame_count - 1)
        self.frame_slider.setSingleStep(1)
        self.frame_slider.setPageStep(max(1, self._frame_count // 20))
        self.frame_slider.setValue(0)
        del slider_blocker
        self._load_frame(0)

    def _load_frame(self, frame_index: int) -> None:
        if self._capture is None:
            return
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
        if self._capture is not None:
            self._capture.release()
            self._capture = None
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


def _pixmap_from_image_file(path: Path, width: int, height: int) -> QPixmap | None:
    try:
        if path.suffix.casefold() == ".svg":
            from dlc_gait_assembly.gui.gait_analysis.window import _qt_safe_svg_bytes

            data = _qt_safe_svg_bytes(path.read_bytes())
            pixmap = QPixmap()
            if not pixmap.loadFromData(data, "SVG"):
                return None
        else:
            pixmap = QPixmap(str(path))
    except OSError:
        return None
    if pixmap.isNull():
        return None
    return pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)


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
        font = painter.font()
        font.setPointSizeF(max(14.0, font.pointSizeF()))
        painter.setFont(font)
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
