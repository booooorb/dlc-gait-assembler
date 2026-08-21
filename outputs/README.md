# Runtime outputs

This directory contains generated user data and application state. Its contents are
ignored by Git except for this guide and placeholder files.

## Structure

- `automated_pipeline/<run>/` — self-contained automated runs with numbered stage folders.
- `manual_pipeline/processed_videos/` — videos prepared by the manual video editor.
- `manual_pipeline/analyzed_videos/` — DeepLabCut coordinate tables and data files.
- `manual_pipeline/labeled_videos/` — DeepLabCut labeled preview videos.
- `manual_pipeline/knee_correction/` — corrected coordinate tables.
- `manual_pipeline/gait_analysis/` — ALMA/RustLab1 tables, stickplots, and figures.
- `calibration/` — exported conversion maps and calibration reports.
- `automated_profiles/` — saved automated-workflow profiles.
- `stroke_cohort_analysis/` — PCA, random-forest, and repeated-measures results.

Legacy manual results are preserved below the corresponding
`manual_pipeline/<stage>/legacy_migrated/` directory. Preview assets required by the
application do not belong here; they live under `assets/analysis_previews/`.
