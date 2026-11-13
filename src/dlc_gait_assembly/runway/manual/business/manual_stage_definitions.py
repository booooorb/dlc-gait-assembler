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


MANUAL_STAGE_DEFINITIONS = (
    ManualStageDefinition(
        "manual_calibration",
        "Calibration",
        "Set the camera scale",
        "Calibration",
        "Calibration",
        "paw-calibration",
    ),
    ManualStageDefinition(
        "video_processing",
        "Video Processing",
        "Crop and trim recordings",
        "Video prep",
        "Video prep",
        "paw-video-prep",
    ),
    ManualStageDefinition(
        "deeplabcut",
        "DeepLabCut",
        "Track keypoints with DeepLabCut",
        "Pose tracking",
        "Pose tracking",
        "paw-pose-tracking",
    ),
    ManualStageDefinition(
        "knee_correction",
        "Knee Correction",
        "Refine tracked knee positions",
        "Knee correction",
        "Knee correction",
        "paw-knee",
    ),
    ManualStageDefinition(
        "gait_parameter_analysis",
        "Gait Analysis",
        "Measure stride, stance, and swing",
        "Gait analysis",
        "Gait analysis",
        "paw-gait",
    ),
    ManualStageDefinition(
        "pca_random_forest",
        "PCA and Random Forest Analysis",
        "Explore gait features and classify movement",
        "PCA + classification",
        "PCA + classification",
        "paw-classification",
    ),
)
MANUAL_STAGE_DISPLAY_LABELS = {stage.id: stage.display_label for stage in MANUAL_STAGE_DEFINITIONS}
HEADER_STAGE_LABELS = {stage.id: stage.header_label for stage in MANUAL_STAGE_DEFINITIONS}
MANUAL_STAGE_ICONS = {stage.id: stage.icon for stage in MANUAL_STAGE_DEFINITIONS}
