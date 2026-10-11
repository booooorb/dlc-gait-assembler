"""Define RustLab1 measurement metadata and supported limb scopes."""

from __future__ import annotations

RUSTLAB1_HINDLIMB_PARAMETER_NAMES = (
    "l-back-ankle__Average_Height",
    "l-back-ankle__Movement",
    "l-back-toe__Average_Height",
    "l-hip__Average_Height",
    "l-hip__Movement",
    "l-iliac-crest__Average_Height",
    "l-iliac-crest__Movement",
    "r-back-ankle__Average_Height",
    "r-back-ankle__Movement",
    "r-back-toe__Average_Height",
    "r-hip__Average_Height",
    "r-hip__Movement",
    "r-iliac-crest__Average_Height",
    "r-iliac-crest__Movement",
    "left__back__average",
    "left__back__median",
    "left__back__protraction",
    "left__back__retraction",
    "right__back__average",
    "right__back__median",
    "right__back__protraction",
    "right__back__retraction",
    "left__back__movement_per_step",
    "right__back__movement_per_step",
)
RUSTLAB1_FORELIMB_PARAMETER_NAMES = (
    "l-front-toe-tip__Average_Height",
    "l-front-toe-tip__Movement",
    "l-wrist__Average_Height",
    "l-wrist__Movement",
    "l-elbow__Average_Height",
    "l-elbow__Movement",
    "l-shoulder__Average_Height",
    "l-shoulder__Movement",
    "r-front-toe-tip__Average_Height",
    "r-front-toe-tip__Movement",
    "r-wrist__Average_Height",
    "r-wrist__Movement",
    "r-elbow__Average_Height",
    "r-elbow__Movement",
    "r-shoulder__Average_Height",
    "r-shoulder__Movement",
    "left__front__average",
    "left__front__median",
    "left__front__protraction",
    "left__front__retraction",
    "right__front__average",
    "right__front__median",
    "right__front__protraction",
    "right__front__retraction",
    "avg_Angle__left__front__shoulder_ellbow_wrist",
    "max_Angle__left__front__shoulder_ellbow_wrist",
    "min_Angle__left__front__shoulder_ellbow_wrist",
    "avg_Angle__left__front__ellbow_wrist_toetip",
    "max_Angle__left__front__ellbow_wrist_toetip",
    "min_Angle__left__front__ellbow_wrist_toetip",
    "avg_Angle__right__front__shoulder_ellbow_wrist",
    "max_Angle__right__front__shoulder_ellbow_wrist",
    "min_Angle__right__front__shoulder_ellbow_wrist",
    "avg_Angle__right__front__ellbow_wrist_toetip",
    "max_Angle__right__front__ellbow_wrist_toetip",
    "min_Angle__right__front__ellbow_wrist_toetip",
    "left__front__seconds",
    "right__front__seconds",
    "FLBR_RATIO",
    "FRBL_RATIO",
)
RUSTLAB1_PARAMETER_NAMES = RUSTLAB1_HINDLIMB_PARAMETER_NAMES + RUSTLAB1_FORELIMB_PARAMETER_NAMES
RUSTLAB1_HINDLIMB_MARKERS = (
    "d-back-left",
    "d-back-right",
    "l-back-ankle",
    "l-back-toe",
    "l-hip",
    "l-iliac-crest",
    "r-back-ankle",
    "r-back-toe",
    "r-hip",
    "r-iliac-crest",
)
RUSTLAB1_FORELIMB_MARKERS = (
    "d-front-left",
    "d-front-right",
    "l-front-toe-tip",
    "l-wrist",
    "l-elbow",
    "l-shoulder",
    "r-front-toe-tip",
    "r-wrist",
    "r-elbow",
    "r-shoulder",
)
RUSTLAB1_MARKERS = RUSTLAB1_HINDLIMB_MARKERS + RUSTLAB1_FORELIMB_MARKERS
RUSTLAB1_FIGURE_FILENAMES = (
    "1_PLOT_bar_all_videos.svg",
    "2_PLOT_Donut_Summary_Validation.svg",
    "3_1_PLOT_control_for_outliers_before.svg",
    "3_2_PLOT_control_for_outliers_after.svg",
    "4_1_PLOT_Overview_Distribution_X.svg",
    "4_2_PLOT_Overview_Distribution_Y.svg",
    "5_PLOT_overview_steps.svg",
    "6_1_PLOT_DOWN_Analysis_Speed_QC.svg",
    "6_2_sync_plots.svg",
    "7_1_PLOT_FIRST_OVERVIEW_VERTICAL_BARPLOT.svg",
    "7.2_PLOT_SECOND_OVERVIEW_Vertical_TIMECOURSE.svg",
    "8_1_PLOT_Horizontal_Analysis_QC.svg",
    "8.2_PLOT_Protraction_Retraction.svg",
    "8_3_PLOT_Protraction_Retraction_line.svg",
    "9_1_PLOT_DURATION_of_STEPE.svg",
    "9_2_PLOT_Distance_covered_per_step.svg",
    "10_1_PLOT_selected_horizontal_Angle.svg",
    "10_2_PLOT_horizontal_Angle_line.svg",
)


def rustlab1_parameter_names_for_scope(limb_scope: str) -> tuple[str, ...]:
    if str(limb_scope).strip().casefold() == "hindlimb + forelimb".casefold():
        return RUSTLAB1_PARAMETER_NAMES
    return RUSTLAB1_HINDLIMB_PARAMETER_NAMES


def rustlab1_markers_for_scope(limb_scope: str) -> tuple[str, ...]:
    if str(limb_scope).strip().casefold() == "hindlimb + forelimb".casefold():
        return RUSTLAB1_MARKERS
    return RUSTLAB1_HINDLIMB_MARKERS
