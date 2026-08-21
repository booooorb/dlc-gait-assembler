"""Presentation metadata for the automated pipeline workspace."""

from dlc_gait_assembly.services.pipeline.automated import AUTOMATED_STAGE_SPECS

PIPELINE_STAGES = tuple(spec.completion_label for spec in AUTOMATED_STAGE_SPECS)
PIPELINE_STAGE_LABELS = tuple(spec.short_label for spec in AUTOMATED_STAGE_SPECS)
PIPELINE_PREVIEW_MESSAGES = tuple(spec.preview_message for spec in AUTOMATED_STAGE_SPECS)
PIPELINE_STAGE_ACTIVITY = tuple(spec.activity for spec in AUTOMATED_STAGE_SPECS)
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
    3: {
        "title": "Review DLC overlays",
        "description": "Verify the knee-corrected tracking overlays. Double-click to enlarge.",
        "preview": "DeepLabCut overlay-video previews appear here.",
        "setting": "region model configuration",
        "tab": 1,
        "replay_stage": 3,
    },
    4: {
        "title": "Review stickplot",
        "description": "Verify the stickplot. Click to enlarge.",
        "preview": "The generated stickplot preview appears here.",
        "setting": "gait analysis manifest",
        "tab": 2,
        "replay_stage": 4,
    },
}
