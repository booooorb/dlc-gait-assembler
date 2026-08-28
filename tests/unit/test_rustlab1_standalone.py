from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.services.pipeline.rustlab1 import (
    AlmaPreprocessedCoordinates,
    RustLab1StandaloneSettings,
    detect_rustlab1_strides,
    generate_rustlab1_stride_preview,
    run_rustlab1_analysis,
)
from dlc_gait_assembly.services.pipeline.alma import AlmaViewCsvSet


def _preprocessed_reference_paw(x_values) -> AlmaPreprocessedCoordinates:
    x = np.asarray(x_values, dtype=float)
    return AlmaPreprocessedCoordinates(
        columns={("d-back-left", "x"): ("d-back-left", "x")},
        series={"d-back-left": {"x": x, "y": np.zeros(len(x))}},
        frame_count=len(x),
        likelihood_threshold=0.95,
        frame_rate=60.0,
        filter_cutoff=6.0,
    )


def test_standalone_rustlab1_detects_strides_from_bottom_paw_stance_onsets():
    preprocessed = _preprocessed_reference_paw(
        [0, 0, 0, 0, 20, 40, 40, 40, 40, 40, 60, 80, 80, 80, 80, 80]
    )
    settings = RustLab1StandaloneSettings(
        frame_rate=60.0,
        stance_speed_threshold_px_frame=7.0,
        pixels_per_cm=20.0,
    )

    strides = detect_rustlab1_strides(preprocessed, settings, pd, np)

    assert strides["stride_start (frame)"].tolist() == [0, 6]
    assert strides["stride_end (frame)"].tolist() == [5, 11]
    assert strides["stance_end (frame)"].tolist() == [3, 9]
    assert strides["swing_start (frame)"].tolist() == [4, 10]
    assert strides["cycle duration (s)"].tolist() == pytest.approx([0.1, 0.1])
    assert strides["stride length (cm)"].tolist() == pytest.approx([2.0, 2.0])


def test_standalone_rustlab1_requires_two_detected_stance_onsets():
    preprocessed = _preprocessed_reference_paw([0, 0, 0, 0, 0])

    with pytest.raises(ValueError, match="did not detect two stance onsets"):
        detect_rustlab1_strides(
            preprocessed,
            RustLab1StandaloneSettings(),
            pd,
            np,
        )


def test_standalone_rustlab1_does_not_invent_frame_zero_stance_during_swing():
    preprocessed = _preprocessed_reference_paw(
        [0, 20, 40, 40, 40, 60, 80, 80, 80, 100, 120, 120, 120]
    )

    strides = detect_rustlab1_strides(
        preprocessed,
        RustLab1StandaloneSettings(),
        pd,
        np,
    )

    assert strides["stride_start (frame)"].tolist() == [3, 7]
    assert 0 not in strides["stride_start (frame)"].tolist()


def test_standalone_stride_preview_marks_detected_windows(tmp_path):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    preprocessed = _preprocessed_reference_paw(
        [0, 0, 0, 0, 20, 40, 40, 40, 40, 40, 60, 80, 80, 80, 80, 80]
    )
    settings = RustLab1StandaloneSettings()
    strides = detect_rustlab1_strides(preprocessed, settings, pd, np)
    destination = tmp_path / "preview.svg"

    result = generate_rustlab1_stride_preview(
        preprocessed,
        strides,
        destination,
        settings,
        plt,
        np,
    )

    assert result == destination
    assert "RustLab1 stride detection" in destination.read_text(encoding="utf-8")
    assert plt.get_fignums() == []


def test_standalone_settings_are_compatible_with_shared_coordinate_filtering():
    settings = RustLab1StandaloneSettings(
        likelihood_threshold=0.8,
        frame_rate=100.0,
        filter_cutoff=5.0,
    )
    assert SimpleNamespace(**settings.__dict__).stance_speed_threshold_px_frame == 7.0


def test_standalone_runner_writes_only_rustlab1_outputs(tmp_path, monkeypatch):
    frames = 16
    reference_x = np.asarray(
        [0, 0, 0, 0, 20, 40, 40, 40, 40, 40, 60, 80, 80, 80, 80, 80],
        dtype=float,
    )
    marker_values = {
        "d-back-left": (reference_x, np.full(frames, 10.0)),
        "d-back-right": (reference_x + 5.0, np.full(frames, 30.0)),
        "d-center-back": (reference_x, np.full(frames, 20.0)),
    }
    for prefix, offset in (("l", 0.0), ("r", 8.0)):
        for marker_index, marker in enumerate(
            ("back-ankle", "back-toe", "hip", "iliac-crest")
        ):
            marker_values[f"{prefix}-{marker}"] = (
                np.arange(frames, dtype=float) + offset + marker_index,
                np.linspace(10.0 + marker_index, 14.0 + marker_index, frames),
            )
    columns = {}
    for marker, (x, y) in marker_values.items():
        columns[(marker, "x")] = x
        columns[(marker, "y")] = y
        columns[(marker, "likelihood")] = np.ones(frames)
    merged = pd.DataFrame(columns)
    merged.columns = pd.MultiIndex.from_tuples(merged.columns)

    monkeypatch.setattr(
        "dlc_gait_assembly.services.pipeline.rustlab1.standalone.merge_multiview_rustlab1_dataframe",
        lambda *_args, **_kwargs: merged,
    )
    monkeypatch.setattr(
        "dlc_gait_assembly.services.pipeline.alma.runner.load_kinematics_functions",
        lambda _root: SimpleNamespace(
            butterworth_filter=lambda values, _frame_rate, _cutoff: values
        ),
    )
    view_set = AlmaViewCsvSet(
        "mouse_trial",
        tmp_path / "mouse_trial_left.csv",
        tmp_path / "mouse_trial_right.csv",
        tmp_path / "mouse_trial_bottom.csv",
    )
    progress = []

    results = run_rustlab1_analysis(
        [view_set],
        tmp_path / "outputs",
        RustLab1StandaloneSettings(
            likelihood_threshold=0.0,
            limb_scope="Hindlimb",
            pixels_per_cm=20.0,
            enabled_parameter_names=("LB__avg_Angle", "left__back__average"),
            generate_figures=False,
        ),
        tmp_path / "ALMA",
        progress_callback=lambda *args: progress.append(args),
    )

    assert len(results) == 1
    assert progress == [(1, 1, "RustLab1: processing mouse_trial")]
    names = {path.name for path in results[0].output_files}
    assert names == {
        "mouse_trial_rustlab1_strides.csv",
        "mouse_trial_rustlab1_parameters.csv",
        "mouse_trial_rustlab1_summary.csv",
        "mouse_trial_rustlab1_stride_preview.svg",
    }
    assert not any("alma" in name.casefold() or "custom" in name.casefold() for name in names)
    strides = pd.read_csv(tmp_path / "outputs" / "mouse_trial_rustlab1_strides.csv")
    parameters = pd.read_csv(tmp_path / "outputs" / "mouse_trial_rustlab1_parameters.csv")
    assert strides["stride_start (frame)"].tolist() == [0, 6]
    assert parameters["stride_start (frame)"].tolist() == [0, 6]
    assert "LB__avg_Angle" in parameters
    assert "left__back__average" in parameters
