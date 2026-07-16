from __future__ import annotations

from dlc_gait_assembly.services.manual_outputs import organize_manual_deeplabcut_outputs
from dlc_gait_assembly.services.project_paths import manual_pipeline_output_folders


def test_manual_deeplabcut_outputs_are_separated_and_keep_session_paths(tmp_path):
    folders = manual_pipeline_output_folders(tmp_path)
    session = folders.processed_videos / "session_01" / "Bottom"
    session.mkdir(parents=True)
    source_video = session / "mouse_processed.mp4"
    analyzed_csv = session / "mouse_processedDLC_fixture.csv"
    analyzed_h5 = session / "mouse_processedDLC_fixture.h5"
    labeled_video = session / "mouse_processedDLC_fixture_labeled.mp4"
    source_video.write_bytes(b"source")
    analyzed_csv.write_text("csv", encoding="utf-8")
    analyzed_h5.write_bytes(b"h5")
    labeled_video.write_bytes(b"labeled")

    result = organize_manual_deeplabcut_outputs(folders)

    analyzed_destination = folders.analyzed_videos / "session_01" / "Bottom"
    labeled_destination = folders.labeled_videos / "session_01" / "Bottom"
    assert source_video.is_file()
    assert (analyzed_destination / analyzed_csv.name).is_file()
    assert (analyzed_destination / analyzed_h5.name).is_file()
    assert (labeled_destination / labeled_video.name).is_file()
    assert len(result.analyzed_files) == 2
    assert len(result.labeled_videos) == 1
