"""ALMA runway-analysis models, configuration, and execution."""

from dlc_gait_assembly.services.pipeline.alma.calibration import pixels_per_cm_from_calibration_map
from dlc_gait_assembly.services.pipeline.alma.config import (
    default_alma_root,
    load_alma_config_defaults,
    settings_from_alma_config,
)
from dlc_gait_assembly.services.pipeline.alma.models import (
    ALMA_BODYPARTS,
    AlmaRunResult,
    AlmaSettings,
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.services.pipeline.alma.multiview import (
    filter_low_confidence_coordinates,
    hide_low_confidence_stickplot_frames,
    merge_multiview_rustlab1_dataframe,
)
from dlc_gait_assembly.services.pipeline.alma.runner import (
    load_kinematics_functions,
    run_alma_gait_analysis,
)

# Private compatibility aliases for callers written before the package split.
_filter_low_confidence_coordinates = filter_low_confidence_coordinates
_hide_low_confidence_stickplot_frames = hide_low_confidence_stickplot_frames
_merge_multiview_rustlab1_dataframe = merge_multiview_rustlab1_dataframe
_load_kinematics_functions = load_kinematics_functions

__all__ = [
    "ALMA_BODYPARTS",
    "AlmaRunResult",
    "AlmaSettings",
    "AlmaViewCsvSet",
    "StrokeStudyMetadata",
    "default_alma_root",
    "filter_low_confidence_coordinates",
    "hide_low_confidence_stickplot_frames",
    "load_alma_config_defaults",
    "load_kinematics_functions",
    "merge_multiview_rustlab1_dataframe",
    "pixels_per_cm_from_calibration_map",
    "run_alma_gait_analysis",
    "settings_from_alma_config",
]
