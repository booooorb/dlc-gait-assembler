"""Load the editable overlay and preserve original tracking when applying human labels."""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import yaml

from dlc_gait_assembly.runway.automatic.review.business.automatic_label_correction import marker_columns
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_project_reader import (
    resolve_deeplabcut_config,
)
from dlc_gait_assembly.shared.infrastructure.coordinate_csv_codec import write_dlc_csv
from dlc_gait_assembly.shared.infrastructure.coordinate_h5_codec import read_dlc_h5, write_dlc_h5
from dlc_gait_assembly.shared.infrastructure.windows_filesystem_paths import windows_filesystem_path


def raw_tracking_path(path):
    return windows_filesystem_path(path.parent / ".raw_tracking" / path.name)


def preserve_raw_tracking(path):
    backup = raw_tracking_path(path)
    if not backup.is_file():
        backup.parent.mkdir(exist_ok=True)
        temporary = backup.with_suffix(".tmp")
        shutil.copy2(path, temporary)
        temporary.replace(backup)


def load_label_artifacts(source):
    # The batch writes identical coordinates to CSV and H5. H5 also preserves multi-animal headers.
    table, _ = read_dlc_h5(source.h5)
    raw_path = raw_tracking_path(source.h5)
    raw = read_dlc_h5(raw_path)[0] if raw_path.is_file() else table
    if not table.index.equals(pd.RangeIndex(len(table))) or not raw.index.equals(pd.RangeIndex(len(raw))):
        raise ValueError(f"{source.csv.name} does not have one ordered row per video frame.")
    config = yaml.safe_load(resolve_deeplabcut_config(source.model).read_text(encoding="utf-8"))
    offset = (int(config["x1"]), int(config["y1"])) if config.get("cropping", False) else (0, 0)
    return table, raw, offset


def apply_label_edits(sources, edits, progress):
    grouped = defaultdict(list)
    for edit in edits:
        grouped[edit.region, edit.video].append(edit)
    matched = {(source.region, source.video): source for source in sources}
    for index, (key, updates) in enumerate(grouped.items(), start=1):
        source = matched[key]
        preserve_raw_tracking(source.h5)
        table, hdf_key = read_dlc_h5(source.h5)
        columns = marker_columns(table)
        table = table.astype(float)
        for edit in updates:
            if not 0 <= edit.frame < len(table) or edit.marker not in columns:
                raise ValueError(f"Corrected marker {edit.marker[-1]} could not be matched in {source.video.name}.")
            cols = columns[edit.marker]
            x, y = edit.point if edit.point is not None else (np.nan, np.nan)
            for coordinate, value in (("x", x), ("y", y), ("likelihood", float(edit.point is not None))):
                if coordinate in cols:
                    table.iat[edit.frame, table.columns.get_loc(cols[coordinate])] = value
        # Prepare both files before replacing them. Reapplying the same edits on retry is idempotent.
        with TemporaryDirectory(dir=windows_filesystem_path(source.h5.parent)) as staging:
            csv, h5 = Path(staging) / source.csv.name, Path(staging) / source.h5.name
            write_dlc_csv(table, csv)
            write_dlc_h5(table, h5, hdf_key, source_path=source.h5)
            h5.replace(source.h5)
            csv.replace(source.csv)
        if progress is not None:
            progress(index, len(grouped), f"Applied corrected labels to {source.video.name}")
