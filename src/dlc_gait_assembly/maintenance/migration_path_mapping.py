"""Map historical output containers to the workflow and stage that owns their contents."""

from pathlib import PurePosixPath

_PATH_PREFIXES = (
    ("outputs/per-video-stride-validation", "development/ui_reviews/gait_analysis/per-video-stride-validation"),
    ("outputs/per-stride-validation", "development/ui_reviews/gait_analysis/per-stride-validation"),
    ("outputs/nearby-confidence-validation", "development/ui_reviews/gait_analysis/nearby-confidence-validation"),
    ("outputs/manual_pipeline/gait_analysis/ladder", "ladder/analyses"),
    ("outputs/manual_pipeline/gait_analysis/legacy_migrated/ladder", "ladder/analyses"),
    ("outputs/ladder", "ladder/analyses"),
    ("outputs/calibration", "runway/manual/calibration"),
    ("outputs/manual_pipeline/processed_videos", "runway/manual/video_processing"),
    ("outputs/manual_pipeline/analyzed_videos", "runway/manual/deeplabcut/analyzed_videos"),
    ("outputs/manual_pipeline/labeled_videos", "runway/manual/deeplabcut/labeled_videos"),
    ("outputs/manual_pipeline/knee_correction", "runway/manual/knee_correction"),
    ("outputs/manual_pipeline/gait_analysis", "runway/manual/gait_analysis"),
    ("outputs/stroke_cohort_analysis", "runway/manual/pca_random_forest"),
    ("outputs/automated_profiles", "runway/automatic/profiles"),
    ("outputs/automated_pipeline", "runway/automatic/runs"),
    ("outputs/ui-review", "development/ui_reviews"),
)


def owning_relative_path(relative):
    source = PurePosixPath(relative)
    for old, new in _PATH_PREFIXES:
        prefix = PurePosixPath(old)
        if source.is_relative_to(prefix):
            remainder = [part for part in source.relative_to(prefix).parts if part != "legacy_migrated"]
            return PurePosixPath(new).joinpath(*remainder)
    return PurePosixPath("migrations/preserved_output_context").joinpath(*source.parts[1:])


def recording_bundle(relative):
    """Keep paired recordings together when a containing legacy session collides."""
    source = PurePosixPath(relative)
    if source.is_relative_to("outputs/automated_profiles") and len(source.parts) > 2:
        return PurePosixPath(*source.parts[:3])
    return source.parent
