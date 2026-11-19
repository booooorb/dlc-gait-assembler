"""Execute pose analysis or labeled-video requests inside the separately installed DeepLabCut environment."""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shutil
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile


def run_request(request_path: Path) -> None:
    bridge_folder = Path(__file__).resolve().parent
    sys.path = [entry for entry in sys.path if Path(entry or os.curdir).resolve() != bridge_folder]
    import deeplabcut

    request = json.loads(request_path.read_text(encoding="utf-8"))
    operation = request.get("operation")
    if operation == "analyze":
        results = run_analysis_jobs(request["jobs"], deeplabcut)
    elif operation == "create_labeled_videos":
        results = run_labeled_video_jobs(request["jobs"], deeplabcut)
    else:
        raise ValueError(f"Unsupported DeepLabCut bridge operation: {operation}")
    Path(request["result_path"]).write_text(json.dumps({"results": results}), encoding="utf-8")


def run_analysis_jobs(jobs: list[dict], deeplabcut) -> list[dict]:
    results = []
    for job in jobs:
        config_path = Path(job["config_path"])
        video_paths = [Path(path) for path in job["video_paths"]]
        analysis_folder = Path(job["analysis_folder"])
        analysis_folder.mkdir(parents=True, exist_ok=True)
        before = {path.resolve() for path in analysis_folder.iterdir() if path.is_file()}
        deeplabcut.analyze_videos(
            str(config_path), [str(path) for path in video_paths], destfolder=str(analysis_folder), save_as_csv=True
        )
        produced = sorted(
            path.resolve() for path in analysis_folder.iterdir() if path.is_file() and path.resolve() not in before
        )
        csv_paths = [path for path in produced if path.suffix.casefold() == ".csv"]
        h5_paths = [path for path in produced if path.suffix.casefold() in {".h5", ".hdf5"}]
        if len(csv_paths) < len(video_paths) or len(h5_paths) < len(video_paths):
            raise RuntimeError(f'''DeepLabCut did not create CSV and H5 coordinates for region "{job["region"]}".''')
        results.append(
            {
                "region": job["region"],
                "video_paths": [str(path) for path in video_paths],
                "csv_paths": [str(path) for path in csv_paths],
                "h5_paths": [str(path) for path in h5_paths],
                "labeled_video_paths": [],
            }
        )
    return results


def render_labeled_videos(render, config_path, video_paths, analysis_folder, pcutoff):
    videos = [str(path) for path in video_paths]
    if pcutoff is None:
        render(str(config_path), videos, destfolder=str(analysis_folder))
        return
    if "pcutoff" in inspect.signature(render).parameters:
        render(str(config_path), videos, destfolder=str(analysis_folder), pcutoff=pcutoff)
        return

    # Older DeepLabCut versions read the cutoff exclusively from the project YAML.
    # Keep the temporary config beside the original so project-relative paths still work.
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["pcutoff"] = pcutoff
    with NamedTemporaryFile(dir=config_path.parent, suffix=".yaml", delete=False) as temporary:
        temporary_config = Path(temporary.name)
    try:
        temporary_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        render(str(temporary_config), videos, destfolder=str(analysis_folder))
    finally:
        temporary_config.unlink(missing_ok=True)


def run_labeled_video_jobs(jobs: list[dict], deeplabcut) -> list[dict]:
    results = []
    for job in jobs:
        config_path = Path(job["config_path"])
        video_paths = [Path(path) for path in job["video_paths"]]
        analysis_folder = Path(job["analysis_folder"])
        labeled_videos_folder = Path(job["labeled_videos_folder"])
        analysis_folder.mkdir(parents=True, exist_ok=True)
        labeled_videos_folder.mkdir(parents=True, exist_ok=True)
        before = {path.resolve() for path in analysis_folder.iterdir() if path.is_file()}
        render_labeled_videos(
            deeplabcut.create_labeled_video, config_path, video_paths, analysis_folder, job.get("pcutoff")
        )
        produced = sorted(
            path.resolve() for path in analysis_folder.iterdir() if path.is_file() and path.resolve() not in before
        )
        csv_paths = [Path(path).resolve() for path in job["csv_paths"]]
        h5_paths = [Path(path).resolve() for path in job["h5_paths"]]
        labeled_paths = [
            path
            for path in produced
            if path.suffix.casefold() in {".mp4", ".avi", ".mov", ".mkv"} and "label" in path.stem.casefold()
        ]
        organized_labeled_paths = []
        for labeled_path in labeled_paths:
            destination = labeled_videos_folder / labeled_path.name
            shutil.move(str(labeled_path), str(destination))
            organized_labeled_paths.append(destination.resolve())
        labeled_paths = organized_labeled_paths
        if len(labeled_paths) < len(video_paths):
            raise RuntimeError(f'''DeepLabCut did not create labeled review videos for region "{job["region"]}".''')
        results.append(
            {
                "region": job["region"],
                "video_paths": [str(path) for path in video_paths],
                "csv_paths": [str(path) for path in csv_paths],
                "h5_paths": [str(path) for path in h5_paths],
                "labeled_video_paths": [str(path) for path in labeled_paths],
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-request", type=Path)
    args = parser.parse_args()
    if args.run_request is None:
        parser.error("--run-request is required")
    run_request(args.run_request)


if __name__ == "__main__":
    main()
