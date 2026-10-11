"""Read Ladder coordinate tables and inspect body-part labels in DLC CSV headers."""

from __future__ import annotations

from pathlib import Path


def read_dlc_bodyparts(csv_path: Path) -> list[str]:
    """Read body-part labels without importing the scientific runtime."""
    import csv

    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.reader(handle)
        next(rows, None)
        bodypart_row = next(rows, None)
        coordinate_row = next(rows, None)
    if bodypart_row is None or coordinate_row is None:
        raise ValueError("Expected a three-row DeepLabCut CSV header.")
    bodyparts: list[str] = []
    for bodypart, coordinate in zip(bodypart_row, coordinate_row, strict=False):
        label = bodypart.strip()
        if coordinate.strip().lower() == "y" and label and (label not in bodyparts):
            bodyparts.append(label)
    if not bodyparts:
        raise ValueError("No body-part y coordinates were found in the CSV header.")
    return bodyparts


def read_coordinate_dataframe(csv_file: Path, pd):
    dataframe = pd.read_csv(csv_file, header=[1, 2])
    flattened: list[str] = []
    bodyparts: list[str] = []
    for bodypart, coordinate in dataframe.columns:
        bodypart = str(bodypart).strip()
        coordinate = str(coordinate).strip().lower()
        flattened.append(f"{bodypart} {coordinate}")
        if coordinate == "y" and bodypart != "bodyparts" and (bodypart not in bodyparts):
            bodyparts.append(bodypart)
    dataframe.columns = flattened
    return (dataframe, bodyparts)


class LadderCoordinateReader:
    @staticmethod
    def bodyparts(path: Path) -> list[str]:
        return read_dlc_bodyparts(path)

    def read(self, path):
        import pandas as pd

        return read_coordinate_dataframe(path, pd)
