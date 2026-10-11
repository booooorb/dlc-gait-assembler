"""Create the Qt application and inject concrete adapters, use cases, page factories, and typed snapshot providers."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.infrastructure.app_preferences_store import AppPreferencesStore
from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_asset_store import (
    AutomaticProfileAssetReader,
)
from dlc_gait_assembly.runway.manual.business.manual_stage_definitions import MANUAL_STAGE_DEFINITIONS
from dlc_gait_assembly.shared.client.theme.theme_application_styles import (
    application_stylesheet as _dependency_theme_application_stylesheet,
)
from dlc_gait_assembly.shared.client.theme.theme_control_painter import FastToolTipStyle
from dlc_gait_assembly.shared.client.theme.theme_font_loader import interface_font as _dependency_theme_interface_font
from dlc_gait_assembly.shared.client.theme.theme_qt_palette import (
    application_palette as _dependency_theme_application_palette,
)
from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace

THEME_MODES = {"light", "dark"}


def resolved_theme_mode(preferences: AppPreferencesStore, system_scheme: Qt.ColorScheme) -> str:
    saved_mode = preferences.theme()
    if saved_mode in THEME_MODES:
        return saved_mode
    return "dark" if system_scheme == Qt.ColorScheme.Dark else "light"


def apply_theme_mode(app: QApplication, window: QMainWindow | None, mode: str) -> None:
    if mode not in THEME_MODES:
        raise ValueError(f"Unknown theme mode: {mode}")
    theme.set_dark_mode(mode == "dark")
    app.setFont(_dependency_theme_interface_font())
    app.setPalette(_dependency_theme_application_palette())
    app.setStyleSheet(_dependency_theme_application_stylesheet())
    if window is not None:
        window.set_theme_mode(mode)
        window.apply_theme()


def main() -> int:
    app = QApplication(sys.argv)
    fast_tooltip_style = FastToolTipStyle(app.style())
    app.setStyle(fast_tooltip_style)
    app._fast_tooltip_style = fast_tooltip_style
    preferences = AppPreferencesStore()
    initial_theme_mode = resolved_theme_mode(preferences, app.styleHints().colorScheme())
    apply_theme_mode(app, None, initial_theme_mode)
    window = create_main_window(initial_theme_mode=initial_theme_mode)
    geometry = preferences.geometry()
    if geometry is not None:
        window.restoreGeometry(geometry)

    def select_theme_mode(mode: str) -> None:
        preferences.save_theme(mode)
        apply_theme_mode(app, window, mode)

    window.theme_mode_requested.connect(select_theme_mode)
    app.aboutToQuit.connect(lambda: preferences.save_geometry(window.saveGeometry()))
    window.show()
    return app.exec()


def create_video_processing_use_cases():
    from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_use_cases import (
        VideoProcessingUseCases,
    )
    from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_ffmpeg_exporter import (
        VideoFFmpegExporter,
    )
    from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_session_document_writer import (
        VideoSessionDocumentWriter,
    )
    from dlc_gait_assembly.runway.manual.video_processing.infrastructure.video_settings_manifest_store import (
        VideoSettingsManifestStore,
    )

    return VideoProcessingUseCases(VideoFFmpegExporter(), VideoSettingsManifestStore(), VideoSessionDocumentWriter())


def create_knee_correction_use_cases():
    from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_use_cases import (
        KneeCorrectionUseCases,
    )
    from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_coordinate_repository import (
        KneeCoordinateRepository,
    )
    from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_result_document_writer import (
        KneeResultDocumentWriter,
    )
    from dlc_gait_assembly.runway.manual.knee_correction.infrastructure.knee_settings_manifest_store import (
        KneeSettingsManifestStore,
    )

    return KneeCorrectionUseCases(KneeCoordinateRepository(), KneeResultDocumentWriter(), KneeSettingsManifestStore())


def create_cohort_writer():
    from dlc_gait_assembly.runway.manual.pca_random_forest.infrastructure.cohort_result_writer import CohortResultWriter

    return CohortResultWriter()


def build_tool_specs():
    from dlc_gait_assembly.app.client.app_page_contracts import ToolSpec
    from dlc_gait_assembly.ladder.client.ladder_analysis_view import LadderAnalysisWidget
    from dlc_gait_assembly.runway.manual.calibration.client.calibration_view import ManualCalibrationWidget
    from dlc_gait_assembly.runway.manual.deeplabcut.client.deeplabcut_view import DeepLabCutWidget
    from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import GaitAnalysisWidget
    from dlc_gait_assembly.runway.manual.knee_correction.client.knee_correction_view import KneeCorrectionWidget
    from dlc_gait_assembly.runway.manual.pca_random_forest.client.cohort_analysis_view import PcaRandomForestWidget
    from dlc_gait_assembly.runway.manual.video_processing.client.video_processing_view import VideoEditorWidget

    widget_factories = {
        "manual_calibration": lambda: ManualCalibrationWidget(
            media_access=create_media_access(), workspace=resolve_workspace(), use_cases=create_calibration_use_cases()
        ),
        "video_processing": lambda: VideoEditorWidget(
            use_cases=create_video_processing_use_cases(),
            media_access=create_media_access(),
            workspace=resolve_workspace(),
        ),
        "deeplabcut": lambda: DeepLabCutWidget(environment=create_deeplabcut_environment()),
        "knee_correction": lambda: KneeCorrectionWidget(
            use_cases=create_knee_correction_use_cases(),
            media_access=create_media_access(),
            workspace=resolve_workspace(),
        ),
        "gait_parameter_analysis": lambda: GaitAnalysisWidget(
            preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
        ),
        "pca_random_forest": lambda: PcaRandomForestWidget(
            outputs=create_cohort_writer(), workspace=resolve_workspace()
        ),
    }
    TOOL_SPECS = [
        ToolSpec(stage.id, stage.label, widget_factories[stage.id], True, stage.description)
        for stage in MANUAL_STAGE_DEFINITIONS
    ]
    LADDER_TOOL_SPEC = ToolSpec(
        "ladder_analysis",
        "Ladder Analysis",
        lambda: LadderAnalysisWidget(
            use_cases=create_ladder_use_cases(), media_access=create_media_access(), workspace=resolve_workspace()
        ),
        True,
        description="Detect, review, and export ladder-rung footfall events.",
    )
    from dataclasses import replace

    from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_from_manual import ManualProfileSnapshot

    snapshot_providers = {
        "manual_calibration": lambda page: ManualProfileSnapshot(
            calibration=page.settings_snapshot(), calibration_map=page.profile_calibration_map_path()
        ),
        "video_processing": lambda page: ManualProfileSnapshot(
            video=page.settings_snapshot(), processing_manifest=page.profile_manifest_path()
        ),
        "gait_parameter_analysis": lambda page: ManualProfileSnapshot(
            gait=page.settings_snapshot(),
            analysis_manifest=page.profile_analysis_manifest_path(),
            calibration_map=page.profile_calibration_map_path(),
        ),
        "knee_correction": lambda page: ManualProfileSnapshot(
            knee=page.settings_snapshot(),
            knee_manifest=page.profile_knee_manifest_path(),
            calibration_map=page.profile_calibration_map_path(),
        ),
    }
    TOOL_SPECS = [replace(spec, snapshot_provider=snapshot_providers.get(spec.id)) for spec in TOOL_SPECS]
    LADDER_TOOL_SPEC = replace(
        LADDER_TOOL_SPEC, connect_back=lambda page, callback: page.back_requested.connect(callback)
    )
    return (TOOL_SPECS, LADDER_TOOL_SPEC)


def create_main_window(**options):
    from dlc_gait_assembly.app.client.app_shell_window import MainWindow

    (tools, ladder) = build_tool_specs()
    return MainWindow(tool_specs=tools, ladder_spec=ladder, menu_factory=create_main_menu, **options)


def create_gait_preview():
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_preview_use_cases import GaitPreviewUseCases
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
        GaitStickplotRenderer,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter

    return GaitPreviewUseCases(GaitResultWriter(), GaitStickplotRenderer())


def create_ladder_use_cases():
    from dlc_gait_assembly.ladder.business.ladder_analysis_use_cases import LadderAnalysisUseCases
    from dlc_gait_assembly.ladder.business.ladder_marker_selection import ladder_settings_from_alma_config
    from dlc_gait_assembly.ladder.infrastructure.ladder_coordinate_reader import LadderCoordinateReader
    from dlc_gait_assembly.ladder.infrastructure.ladder_event_exporter import LadderEventExporter
    from dlc_gait_assembly.ladder.infrastructure.ladder_runtime_executor import run_ladder_analysis
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_default_settings_reader import (
        load_alma_config_defaults,
    )

    return LadderAnalysisUseCases(
        LadderCoordinateReader(),
        LadderEventExporter(),
        ladder_settings_from_alma_config(load_alma_config_defaults()),
        execution=run_ladder_analysis,
    )


def create_automatic_run(profile, videos, project_root, output_root=None, **options):
    from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_coordinator import AutomatedPipelineRun
    from dlc_gait_assembly.runway.automatic.runs.business.automatic_run_ports import AutomaticStageOperations
    from dlc_gait_assembly.runway.automatic.runs.infrastructure.automatic_run_storage import AutomaticRunStorage
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_preview_writer import (
        write_gait_stickplot_previews,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
        run_alma_gait_analysis,
    )

    operations = options.pop("operations", None) or AutomaticStageOperations(
        create_video_processing_use_cases(),
        create_knee_correction_use_cases(),
        run_alma_gait_analysis,
        create_deeplabcut_analysis().analyze,
        create_deeplabcut_analysis().create_labeled_videos,
        write_gait_stickplot_previews,
    )
    storage = options.pop("storage", None) or AutomaticRunStorage()
    return AutomatedPipelineRun(
        profile, videos, project_root, output_root, operations=operations, storage=storage, **options
    )


def create_automatic_workspace(store=None):
    from dlc_gait_assembly.runway.automatic.client.automatic_workspace_view import AutomatedPipelineProfilesWidget

    return AutomatedPipelineProfilesWidget(
        review_artifacts=create_review_artifact_reader(),
        profile_use_cases=create_profile_use_cases(store),
        run_factory=create_automatic_run,
        media_access=create_media_access(),
        workspace=resolve_workspace(),
    )


def create_media_access():
    from dlc_gait_assembly.shared.infrastructure.media_frame_reader import MediaFrameReader

    return MediaFrameReader()


def create_profile_use_cases(store=None):
    from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_use_cases import (
        AutomaticProfileUseCases,
    )
    from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_asset_store import (
        AutomaticManualAssetWriter,
    )
    from dlc_gait_assembly.runway.automatic.profiles.infrastructure.automatic_profile_repository import (
        AutomatedProfileStore,
    )
    from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace

    return AutomaticProfileUseCases(
        store or AutomatedProfileStore(resolve_workspace().automatic_profiles),
        AutomaticManualAssetWriter(),
        AutomaticProfileAssetReader(),
    )


def create_review_artifact_reader():
    from dlc_gait_assembly.runway.automatic.review.infrastructure.automatic_review_artifact_reader import (
        AutomaticReviewArtifactReader,
    )

    return AutomaticReviewArtifactReader()


def create_rustlab1_use_cases():
    from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_standalone_engine import (
        RustLab1StandaloneUseCases,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.rustlab1_recording_writer import (
        RustLab1RecordingWriter,
    )

    return RustLab1StandaloneUseCases(RustLab1RecordingWriter())


def create_gait_analysis_operations():
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import (
        settings_from_alma_config,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_ports import GaitAnalysisOperations
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_coordinate_repository import GaitInputReader
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_default_settings_reader import (
        load_alma_config_defaults,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_scientific_runtime_executor import (
        run_alma_gait_analysis,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_settings_manifest_store import (
        GaitSettingsManifestStore,
    )

    return GaitAnalysisOperations(
        run_alma_gait_analysis,
        create_rustlab1_use_cases().run,
        GaitSettingsManifestStore(),
        GaitInputReader(),
        create_gait_result_reader(),
        settings_from_alma_config(load_alma_config_defaults()),
    )


def create_deeplabcut_environment():
    from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_environment_use_cases import (
        DeepLabCutEnvironmentUseCases,
    )
    from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_environment_adapter import (
        DeepLabCutEnvironmentAdapter,
    )

    return DeepLabCutEnvironmentUseCases(DeepLabCutEnvironmentAdapter())


def create_deeplabcut_analysis():
    from dlc_gait_assembly.runway.manual.deeplabcut.business.deeplabcut_analysis_use_cases import (
        DeepLabCutAnalysisUseCases,
    )
    from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_bridge_client import (
        DeepLabCutBridgeClient,
    )
    from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_output_organizer import (
        DeepLabCutArtifactStore,
    )
    from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_project_reader import (
        DeepLabCutProjectReader,
    )

    return DeepLabCutAnalysisUseCases(DeepLabCutProjectReader(), DeepLabCutBridgeClient(), DeepLabCutArtifactStore())


def create_calibration_use_cases():
    from dlc_gait_assembly.runway.manual.calibration.business.calibration_use_cases import CalibrationUseCases
    from dlc_gait_assembly.runway.manual.calibration.infrastructure.calibration_export_writer import (
        CalibrationExportWriter,
    )

    return CalibrationUseCases(CalibrationExportWriter())


def create_gait_result_reader():
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_reader import GaitResultReader

    return GaitResultReader()


def create_main_menu(tools):
    """Connect navigation surfaces without coupling the shell to workflow widgets."""
    from dlc_gait_assembly.app.client.app_home_view import MainMenuWidget
    from dlc_gait_assembly.runway.client.runway_home_view import build_runway_home
    from dlc_gait_assembly.runway.manual.client.manual_stage_directory import build_manual_stage_directory

    return MainMenuWidget(
        tools,
        automatic_factory=create_automatic_workspace,
        runway_builder=build_runway_home,
        manual_builder=build_manual_stage_directory,
    )
