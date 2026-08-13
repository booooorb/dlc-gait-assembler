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
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.gui import theme
from dlc_gait_assembly.gui.automated_pipeline.constants import (
    PIPELINE_STAGE_LABELS,
    RUN_PREVIEW_TOOLTIP,
)
from dlc_gait_assembly.gui.automated_pipeline.previews import (
    AutomationVideoPreviewDialog,
    DoubleClickLabel,
    VideoDropList,
)
from dlc_gait_assembly.gui.automated_pipeline.profile_editor import (
    ProfileEditorMixin,
    ProfileEditorPage,
)
from dlc_gait_assembly.gui.automated_pipeline.review import PipelineReviewMixin
from dlc_gait_assembly.gui.automated_pipeline.run_workspace import (
    RunWorkspaceMixin,
    RunWorkspacePage,
)
from dlc_gait_assembly.gui.automated_pipeline.styles import automated_pipeline_stylesheet
from dlc_gait_assembly.gui.automated_pipeline.worker import AutomatedPipelineWorker
from dlc_gait_assembly.gui.shared.icons import interface_icon
from dlc_gait_assembly.gui.shared.progress import CircularProgressIndicator, DynamicProgressBar
from dlc_gait_assembly.gui.shared.widgets import install_sliding_tab_bar
from dlc_gait_assembly.services.automated_profiles import (
    AutomatedPipelineProfile,
    AutomatedProfileStore,
)
from dlc_gait_assembly.services.pipeline.automated import (
    StageReview,
)
from dlc_gait_assembly.services.project_paths import find_project_root

try:
    import cv2
except ImportError:
    cv2 = None


class AutomatedPipelineProfilesWidget(
    ProfileEditorMixin, RunWorkspaceMixin, PipelineReviewMixin, QWidget
):
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
        self._pipeline_stage_emphasis_timer = QTimer(self)
        self._pipeline_stage_emphasis_timer.setInterval(33)
        self._pipeline_stage_emphasis_timer.timeout.connect(
            self._advance_pipeline_stage_emphasis
        )
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
            "Choose the saved setup this run will use. A profile contains the video "
            "processing manifest, region-specific DeepLabCut models, and any analysis "
            "stages enabled when the profile was created."
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
        automation_page = RunWorkspacePage()
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
        video_panel = QFrame()
        video_panel.setObjectName("VideoDropPanel")
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(14, 12, 14, 14)
        video_layout.setSpacing(10)
        video_toolbar = QHBoxLayout()
        video_toolbar.setSpacing(8)
        videos_title = QLabel("Videos")
        videos_title.setObjectName("AutomationPanelTitle")
        video_toolbar.addWidget(videos_title)
        self.video_count_label = QLabel("0 videos")
        self.video_count_label.setObjectName("VideoCountLabel")
        video_toolbar.addWidget(self.video_count_label)
        video_toolbar.addStretch(1)
        self.remove_videos_button = QPushButton("Remove")
        self.remove_videos_button.setObjectName("RemoveButton")
        self.remove_videos_button.setEnabled(False)
        self.remove_videos_button.setToolTip(
            "Remove the selected videos from this queue. Files on disk are not deleted."
        )
        video_toolbar.addWidget(self.remove_videos_button)
        self.clear_videos_button = QPushButton("Clear")
        self.clear_videos_button.setObjectName("ClearButton")
        self.clear_videos_button.setEnabled(False)
        self.clear_videos_button.setToolTip(
            "Remove every video from this queue. Files on disk are not deleted."
        )
        video_toolbar.addWidget(self.clear_videos_button)
        video_layout.addLayout(video_toolbar)
        self.video_list = VideoDropList()
        self.video_list.setObjectName("AutomationVideoDropList")
        self.upload_videos_button = self.video_list.add_videos_button
        self.video_list.setAccessibleDescription(
            "Drop source videos here or choose Add videos. Hover over a queued video to "
            "play a preview, or double-click to open the expanded preview."
        )
        self.video_list.setToolTip(
            "Queued source videos. Hover over a row for a quick preview, double-click it "
            "for a larger viewer, or select rows before choosing Remove."
        )
        self.video_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.video_list.setMinimumHeight(280)
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
        console_layout.setContentsMargins(14, 12, 14, 14)
        console_layout.setSpacing(10)
        console_header = QHBoxLayout()
        console_header.setSpacing(8)
        console_title = QLabel("Activity")
        console_title.setObjectName("AutomationPanelTitle")
        console_header.addWidget(console_title)
        console_header.addStretch(1)
        self.pipeline_log_state = QLabel("●  Ready")
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
        self.automation_console.setPlainText("[Ready]")
        console_layout.addWidget(self.automation_console, 1)
        automation_content.addWidget(console_panel, 2)
        self.automation_console_panel = console_panel
        self._automation_input_default_minimum_height = self.automation_input_stack.minimumHeight()
        self._automation_input_default_maximum_height = self.automation_input_stack.maximumHeight()
        self._automation_console_default_minimum_height = console_panel.minimumHeight()
        self._automation_console_default_maximum_height = console_panel.maximumHeight()
        automation_layout.addLayout(automation_content, 1)

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

        configuration_page = ProfileEditorPage()
        configuration_page.setObjectName("ProfileConfigurationPage")
        configuration_layout = QVBoxLayout(configuration_page)
        configuration_layout.setContentsMargins(0, 0, 0, 0)
        configuration_layout.setSpacing(8)

        configuration_toolbar = QFrame()
        configuration_toolbar.setObjectName("ProfileConfigurationToolbar")
        toolbar_layout = QHBoxLayout(configuration_toolbar)
        toolbar_layout.setContentsMargins(12, 10, 12, 10)
        self.back_to_automation_button = QPushButton("Back to automation")
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
        self.new_profile_button.setObjectName("NewProfileButton")
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
        self.duplicate_profile_button = QPushButton("Duplicate profile")
        self.duplicate_profile_button.setObjectName("DuplicateProfileButton")
        self.duplicate_profile_button.setToolTip(
            "Copy the selected profile under a new name. The original profile and all "
            "of its saved input files remain unchanged."
        )
        management_layout.addWidget(self.duplicate_profile_button)
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
        install_sliding_tab_bar(self.configuration_tabs, theme.TOOL_2)
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
        readiness_panel.setMaximumHeight(440)
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
        self.configuration_tabs.setMaximumHeight(440)
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
        install_sliding_tab_bar(self.pipeline_component_tabs, theme.TOOL_1)
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
        self.video_list.itemSelectionChanged.connect(self._sync_video_actions)
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

    def _apply_style(self) -> None:
        self.setStyleSheet(automated_pipeline_stylesheet())
        surface_names = {
            "ProfileHeader",
            "MainAutomationMenu",
            "ProfileConfigurationToolbar",
            "ProfileManagementPanel",
            "ProfileReadinessPanel",
        }
        for surface in (
            frame for frame in self.findChildren(QFrame) if frame.objectName() in surface_names
        ):
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
