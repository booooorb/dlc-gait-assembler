"""Define manual stage identities, order, labels, descriptions, and presentation asset identifiers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ManualStageDefinition:
    id: str
    label: str
    description: str
    display_label: str
    header_label: str
    icon: str
    menu_asset: str


MANUAL_STAGE_DEFINITIONS = (
    ManualStageDefinition(
        "manual_calibration",
        "Calibration",
        "Set measurement references and check spatial scale.",
        "Calibration",
        "Calibration",
        "calibration-grid",
        "stage-calibration",
    ),
    ManualStageDefinition(
        "video_processing",
        "Video Processing",
        "Prepare videos, regions, trims, enhancements, and H.264 export.",
        "Video\nprocessing",
        "Video processing",
        "film",
        "stage-video",
    ),
    ManualStageDefinition(
        "deeplabcut",
        "DeepLabCut",
        "Train, evaluate, and analyze pose estimation projects.",
        "DeepLabCut",
        "DeepLabCut",
        "joints",
        "stage-deeplabcut",
    ),
    ManualStageDefinition(
        "knee_correction",
        "Knee Correction",
        "Correct knee coordinates in paired DeepLabCut CSV and H5 labels.",
        "Knee\ncorrection",
        "Knee correction",
        "knee",
        "stage-knee",
    ),
    ManualStageDefinition(
        "gait_parameter_analysis",
        "Gait Parameter Analysis",
        "Assemble stride, stance, swing, and gait outputs.",
        "Gait\nanalysis",
        "Gait analysis",
        "gait",
        "stage-gait",
    ),
    ManualStageDefinition(
        "pca_random_forest",
        "PCA and Random Forest Analysis",
        "Reduce gait features and build classification models.",
        "PCA + random\nforest",
        "PCA + random forest",
        "chart",
        "stage-analysis",
    ),
)
MANUAL_STAGE_DISPLAY_LABELS = {stage.id: stage.display_label for stage in MANUAL_STAGE_DEFINITIONS}
HEADER_STAGE_LABELS = {stage.id: stage.header_label for stage in MANUAL_STAGE_DEFINITIONS}
MANUAL_STAGE_ICONS = {stage.id: stage.icon for stage in MANUAL_STAGE_DEFINITIONS}
MANUAL_STAGE_MENU_ASSETS = {stage.id: stage.menu_asset for stage in MANUAL_STAGE_DEFINITIONS}
