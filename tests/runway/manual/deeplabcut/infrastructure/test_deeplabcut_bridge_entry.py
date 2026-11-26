"""Exercise the analysis and label handoff with long DeepLabCut filenames."""

import os
import sys
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure import deeplabcut_bridge_client, deeplabcut_bridge_entry
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommandResult


@pytest.mark.parametrize(
    ("extended", "expected"),
    [
        (r"\\?\C:\Run\Right\videoDLC.h5", r"C:\Run\Right\videoDLC.h5"),
        (r"\\?\UNC\server\share\videoDLC.h5", r"\\server\share\videoDLC.h5"),
        ("\\\\?\\C:\\Run\\" + "r" * 250 + ".csv", "\\\\?\\C:\\Run\\" + "r" * 250 + ".csv"),
    ],
)
def test_decode_windows_artifacts_retains_prefix_only_for_long_paths(monkeypatch, extended, expected):
    monkeypatch.setattr(deeplabcut_bridge_client, "Path", PureWindowsPath)
    result = deeplabcut_bridge_client.result_from_json({"region": "Right", "h5_paths": [extended]})
    assert result.h5_paths == (PureWindowsPath(expected),)


def test_analysis_and_label_jobs_keep_long_outputs_accessible(tmp_path, monkeypatch):
    scorer = "DLC_Resnet50_right (mirror)Sep6shuffle1_snapshot_best-230"
    video = tmp_path / "GX012345- Trial 5 runway-00.01.02.541-00.01.03.642-seg4_processed.mp4"
    run = tmp_path / "workspace" / "runway" / "automatic" / "runs" / "20261126-110551_Right_Only_Long_Names"
    analysis_dir = run / "02_deeplabcut" / "analyzed_videos" / "Right"
    labeled_dir = run / "02_deeplabcut" / "labeled_videos" / "Right"
    prefix = video.stem + scorer
    coordinates = pd.DataFrame({"likelihood": [0.95]})
    assert len(str(analysis_dir / f"{prefix}.h5")) >= 260

    class DeepLabCut:
        def analyze_videos(self, config, videos, *, destfolder, save_as_csv):
            assert videos == [str(video)]
            assert save_as_csv
            if os.name == "nt":
                assert destfolder.startswith("\\\\?\\")
            folder = Path(destfolder)
            (folder / f"{prefix}_meta.pickle").write_bytes(b"metadata")
            coordinates.to_hdf(folder / f"{prefix}.h5", key="df_with_missing")
            coordinates.to_csv(folder / f"{prefix}.csv")

        def create_labeled_video(self, config, videos, *, destfolder, pcutoff):
            assert videos == [str(video)]
            assert pcutoff == 0.8
            folder = Path(destfolder)
            assert (folder / f"{prefix}_meta.pickle").is_file()
            pd.testing.assert_frame_equal(pd.read_hdf(folder / f"{prefix}.h5"), coordinates)
            (folder / f"{prefix}_p80_labeled.mp4").write_bytes(b"labeled video")

    job = {
        "region": "Right",
        "config_path": str(tmp_path / "config.yaml"),
        "video_paths": [str(video)],
        "analysis_folder": str(analysis_dir),
    }
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "deeplabcut", DeepLabCut())
    monkeypatch.setattr(deeplabcut_bridge_client, "deeplabcut_analysis_arguments", lambda _, path: (str(path),))

    def run_process(command, *_args, **_kwargs):
        deeplabcut_bridge_entry.run_request(Path(command.arguments[0]))
        return ExternalCommandResult(0, "")

    monkeypatch.setattr(deeplabcut_bridge_client, "ExternalProcessSession", lambda: SimpleNamespace(run=run_process))

    def request(operation, job):
        result = deeplabcut_bridge_client.run_bridge_request(
            {"operation": operation, "jobs": [job]}, 1, "analysis", "Starting", "Failed", None
        )
        (item,) = result["results"]
        return deeplabcut_bridge_client.result_from_json(item)

    analysis = request("analyze", job)
    (csv,) = analysis.csv_paths
    (h5,) = analysis.h5_paths
    assert csv.name == f"{prefix}.csv"
    assert csv.is_file()
    pd.testing.assert_frame_equal(pd.read_hdf(h5), coordinates)

    labeled = request(
        "create_labeled_videos",
        {
            **job,
            "labeled_videos_folder": str(labeled_dir),
            "pcutoff": 0.8,
            "csv_paths": [str(csv)],
            "h5_paths": [str(h5)],
        },
    )

    assert labeled.csv_paths == analysis.csv_paths
    assert labeled.h5_paths == analysis.h5_paths
    (label,) = labeled.labeled_video_paths
    assert label.name == f"{prefix}_p80_labeled.mp4"
    assert label.parent.samefile(labeled_dir)
    assert label.read_bytes() == b"labeled video"
