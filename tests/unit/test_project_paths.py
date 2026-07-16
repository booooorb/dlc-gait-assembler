from __future__ import annotations

from dlc_gait_assembly.services.project_paths import manual_pipeline_output_folders


def test_manual_pipeline_output_folders_are_separated_under_one_root(tmp_path):
    folders = manual_pipeline_output_folders(tmp_path)

    assert folders.root == tmp_path / "outputs" / "manual_pipeline"
    assert folders.processed_videos == folders.root / "processed_videos"
    assert folders.analyzed_videos == folders.root / "analyzed_videos"
    assert folders.labeled_videos == folders.root / "labeled_videos"
    assert folders.knee_correction == folders.root / "knee_correction"
    assert folders.gait_analysis == folders.root / "gait_analysis"
    assert all(
        folder.is_dir()
        for folder in (
            folders.processed_videos,
            folders.analyzed_videos,
            folders.labeled_videos,
            folders.knee_correction,
            folders.gait_analysis,
        )
    )
