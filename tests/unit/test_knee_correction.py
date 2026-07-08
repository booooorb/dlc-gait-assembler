from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dlc_gait_assembly.services.knee_correction import (
    KneeCorrectionSettings,
    correct_knee_dataframe,
    correct_knee_pair,
    pair_coordinate_files,
    read_dlc_bodyparts,
    read_dlc_csv,
    read_dlc_h5,
)


def _coordinates() -> pd.DataFrame:
    columns = pd.MultiIndex.from_product(
        [["DLC_test"], ["hip", "knee", "ankle"], ["x", "y", "likelihood"]],
        names=["scorer", "bodyparts", "coords"],
    )
    rows = []
    for offset in (0.0, 0.25, 0.5):
        rows.append(
            [
                offset,
                0.0,
                0.98,
                2.0 + offset,
                1.0,
                0.4,
                4.0 + offset,
                0.0,
                0.95,
            ]
        )
    return pd.DataFrame(rows, columns=columns)


def test_pair_coordinate_files_marks_missing_counterparts(tmp_path):
    paired_csv = tmp_path / "mouse.csv"
    paired_h5 = tmp_path / "mouse.h5"
    paired_video = tmp_path / "mouse.mp4"
    missing_video_csv = tmp_path / "other.csv"
    missing_video_h5 = tmp_path / "other.h5"
    for path in (paired_csv, paired_h5, paired_video, missing_video_csv, missing_video_h5):
        path.touch()

    pairs = pair_coordinate_files(
        [paired_csv, paired_h5, paired_video, missing_video_csv, missing_video_h5]
    )

    assert [(pair.stem, pair.status) for pair in pairs] == [
        ("mouse", "Paired"),
        ("other", "Missing Video"),
    ]
    assert pairs[0].video_path == paired_video.resolve()


def test_pair_coordinate_files_matches_common_deeplabcut_label_stems(tmp_path):
    csv_path = tmp_path / "trialDLC_resnet50_projectshuffle1_100000.csv"
    h5_path = tmp_path / "trialDLC_resnet50_projectshuffle1_100000.h5"
    video_path = tmp_path / "trial.mp4"
    for path in (csv_path, h5_path, video_path):
        path.touch()

    pairs = pair_coordinate_files([csv_path, h5_path, video_path])

    assert len(pairs) == 1
    assert pairs[0].is_paired
    assert pairs[0].csv_path == csv_path.resolve()
    assert pairs[0].video_path == video_path.resolve()


def test_triangulation_replaces_knee_and_endpoint_likelihood():
    corrected, reports = correct_knee_dataframe(
        _coordinates(),
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
        ),
    )

    knee_y = corrected.loc[:, ("DLC_test", "knee", "y")].to_numpy()
    knee_likelihood = corrected.loc[:, ("DLC_test", "knee", "likelihood")].to_numpy()
    assert np.allclose(knee_y, np.sqrt(5.0))
    assert np.allclose(knee_likelihood, 0.95)
    assert reports[0].corrected_frames == 3
    assert reports[0].retained_frames == 0


def test_triangulation_handles_integer_coordinate_columns():
    dataframe = _coordinates().round().astype(int)

    corrected, reports = correct_knee_dataframe(
        dataframe,
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
        ),
    )

    assert reports[0].corrected_frames == 3
    assert corrected.loc[:, ("DLC_test", "knee", "y")].dtype.kind == "f"
    assert np.allclose(corrected.loc[:, ("DLC_test", "knee", "y")], np.sqrt(5.0))


def test_selected_nonstandard_label_can_be_treated_as_knee():
    dataframe = _coordinates()
    dataframe.columns = pd.MultiIndex.from_tuples(
        [
            (
                scorer,
                {
                    "hip": "pelvis_marker",
                    "knee": "patella_marker",
                    "ankle": "hock_marker",
                }[bodypart],
                coordinate,
            )
            for scorer, bodypart, coordinate in dataframe.columns
        ],
        names=dataframe.columns.names,
    )

    corrected, reports = correct_knee_dataframe(
        dataframe,
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
            knee_bodyparts=("patella_marker",),
            hip_bodypart="pelvis_marker",
            ankle_bodypart="hock_marker",
        ),
    )

    assert reports[0].knee == "patella_marker"
    assert reports[0].hip == "pelvis_marker"
    assert reports[0].ankle == "hock_marker"
    assert np.allclose(
        corrected.loc[:, ("DLC_test", "patella_marker", "y")],
        np.sqrt(5.0),
    )


def test_missing_knee_label_is_generated_with_manual_direction():
    dataframe = _coordinates()
    dataframe = dataframe.drop(
        columns=[column for column in dataframe.columns if column[1] == "knee"]
    )

    positive, positive_reports = correct_knee_dataframe(
        dataframe,
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
            hip_bodypart="hip",
            ankle_bodypart="ankle",
            output_knee_bodypart="generated_knee",
            knee_direction="positive",
        ),
    )
    negative, _negative_reports = correct_knee_dataframe(
        dataframe,
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
            hip_bodypart="hip",
            ankle_bodypart="ankle",
            output_knee_bodypart="generated_knee",
            knee_direction="negative",
        ),
    )

    assert positive_reports[0].knee == "generated_knee"
    assert np.allclose(
        positive.loc[:, ("DLC_test", "generated_knee", "y")],
        np.sqrt(5.0),
    )
    assert np.allclose(
        negative.loc[:, ("DLC_test", "generated_knee", "y")],
        -np.sqrt(5.0),
    )
    assert np.allclose(
        positive.loc[:, ("DLC_test", "generated_knee", "likelihood")],
        0.95,
    )


def test_manual_direction_overrides_existing_old_knee_side():
    dataframe = _coordinates()
    dataframe.loc[:, ("DLC_test", "knee", "y")] = -1.0

    corrected, _reports = correct_knee_dataframe(
        dataframe,
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
            knee_direction="positive",
        ),
    )

    assert np.allclose(
        corrected.loc[:, ("DLC_test", "knee", "y")],
        np.sqrt(5.0),
    )


def test_retained_frames_report_specific_correction_failure():
    dataframe = pd.concat([_coordinates(), _coordinates().iloc[[0]]], ignore_index=True)
    dataframe.loc[0, ("DLC_test", "hip", "x")] = float("nan")
    dataframe.loc[1, ("DLC_test", "ankle", "likelihood")] = 0.1
    dataframe.loc[2, ("DLC_test", "ankle", "x")] = dataframe.loc[
        2, ("DLC_test", "hip", "x")
    ]
    dataframe.loc[2, ("DLC_test", "ankle", "y")] = dataframe.loc[
        2, ("DLC_test", "hip", "y")
    ]
    dataframe.loc[3, ("DLC_test", "ankle", "x")] = 10.0

    corrected, reports = correct_knee_dataframe(
        dataframe,
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
            likelihood_threshold=0.5,
        ),
    )

    assert reports[0].frame_statuses == (
        "Missing hip coordinates",
        "Low-confidence ankle",
        "Zero hip–ankle distance",
        "Segment lengths cannot form a triangle",
    )
    assert reports[0].corrected_frames == 0


def test_paired_csv_and_h5_exports_have_identical_corrected_labels(tmp_path):
    dataframe = _coordinates()
    csv_path = tmp_path / "mouse.csv"
    h5_path = tmp_path / "mouse.h5"
    video_path = tmp_path / "mouse.mp4"
    dataframe.to_csv(csv_path)
    dataframe.to_hdf(h5_path, key="df_with_missing", mode="w", format="table")
    video_path.touch()
    assert read_dlc_bodyparts(csv_path) == ("hip", "knee", "ankle")
    pair = pair_coordinate_files([csv_path, h5_path, video_path])[0]

    result = correct_knee_pair(
        pair,
        tmp_path / "corrected",
        KneeCorrectionSettings(
            hip_knee_length_cm=1.5,
            knee_ankle_length_cm=1.5,
            pixels_per_cm=2.0,
        ),
    )

    output_csv = read_dlc_csv(result.output_csv)
    output_h5, key = read_dlc_h5(result.output_h5)
    assert key == "/df_with_missing"
    assert result.source_video == video_path.resolve()
    pd.testing.assert_frame_equal(output_csv, output_h5)
    assert result.output_csv.name == "mouse_knee_corrected.csv"
    assert result.output_h5.name == "mouse_knee_corrected.h5"
