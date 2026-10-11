"""Scientific and presentation contracts for full-recording stick-plot comparisons."""

import re
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.app.app_bootstrap import create_gait_preview
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    RUSTLAB1_METHOD,
    STRIDE_METHODS,
    bottom_detection,
    detect_strides,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import AlmaViewCsvSet
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
    prepare_alma_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
    RustLab1StandaloneSettings,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_stride_detection import (
    detect_rustlab1_strides,
    rustlab1_stance_mask,
)


@pytest.fixture
def paired_recording(tmp_path, alma_fixtures_dir):
    side = alma_fixtures_dir / "alma_edge_cases_filtered.csv"
    frame = np.arange(len(pd.read_csv(side, header=[1, 2])))
    bottom = pd.DataFrame(
        {
            ("DLC", paw, axis): np.ones(len(frame))
            if axis == "likelihood"
            else frame * 0.5 + 80 * np.cos(frame * 2 * np.pi / 40 + shift)
            if axis == "x"
            else 100 + 5 * np.sin(frame * 2 * np.pi / 40 + shift)
            for paw, shift in (("lhpaw", 0), ("rhpaw", np.pi), ("lfpaw", 0), ("rfpaw", np.pi))
            for axis in ("x", "y", "likelihood")
        }
    )
    bottom_path = tmp_path / "bottom.csv"
    bottom.to_csv(bottom_path, index=False)
    return (("Left", side), ("Right", side), ("Bottom", bottom_path))


def skeleton_geometry(svg):
    from xml.etree import ElementTree as ET

    root = ET.fromstring(svg)
    result = {}
    for group in root.iter("{http://www.w3.org/2000/svg}g"):
        match = re.fullmatch(r"stick-frame-(\d+)-\w+-segment-(\d+)", group.get("id", ""))
        if match:
            result[tuple(map(int, match.groups()))] = tuple(
                path.get("d") for path in group.iter("{http://www.w3.org/2000/svg}path")
            )
    return result


def test_all_methods_draw_identical_full_recording_geometry(paired_recording):
    cfg = AlmaSettings(
        analysis_type="Spontaneous walking", pixels_per_cm=50.0, likelihood_threshold=0.0, n_continuous_strides=1
    )
    preview = create_gait_preview()
    results = preview.compare(paired_recording, cfg)
    assert len(STRIDE_METHODS) >= 10
    assert tuple(row[0] for row in results) == STRIDE_METHODS
    expected, sizes, counts = {}, set(), set()
    frame_count = len(pd.read_csv(dict(paired_recording)["Left"], header=[1, 2]))
    for method, plots, message in results:
        assert len(plots) == 2, (method, message)
        for label, svg in plots:
            text = svg.decode()
            geometry = skeleton_geometry(svg)
            assert set(frame for frame, _ in geometry) == set(range(frame_count))
            assert geometry == expected.setdefault(label, geometry), method
            assert f"frames 0–{frame_count - 1}" in text
            sizes.add(re.search(r'viewBox="([^"]+)"', text)[1])
            counts.add(len(re.findall(r'id="stride-start-\d+"', text)))
    assert len(sizes) == 1
    assert max(counts) > 1  # The obsolete display limit is ignored.
    # The standalone preview must use exactly the same coordinates and axes too.
    for label, svg in preview.prepare(paired_recording, cfg)[0]:
        assert skeleton_geometry(svg) == expected[label]


def test_standalone_rustlab_preview_also_shows_two_stickplots(paired_recording):
    paths = dict(paired_recording)
    item = AlmaViewCsvSet("test", paths["Left"], paths["Right"], paths["Bottom"])
    cfg = RustLab1StandaloneSettings(frame_rate=120.0, likelihood_threshold=0.0, n_continuous_strides=2)
    plots, _, _ = create_gait_preview().prepare_rustlab1(item, cfg)
    assert len(plots) == 2
    boundaries = []
    for label, svg in plots:
        text = svg.decode()
        assert label.endswith("stick plot") and "stick-frame-" in text
        assert "Full recording" in text
        frames = [int(f) for f in re.findall(r'id="stick-frame-(\d+)-', text)]
        assert min(frames) == 0 and max(frames) == len(pd.read_csv(paths["Left"], header=[1, 2])) - 1
        boundaries.append(re.findall(r'id="stride-start-(\d+)"', text))
    assert boundaries[0] == boundaries[1]


def test_rustlab_option_is_the_same_rule_as_standalone(paired_recording):
    raw = pd.read_csv(dict(paired_recording)["Bottom"], header=[1, 2])
    aligned = align_multiview_coordinates({"bottom": raw}, pd)
    cfg = AlmaSettings(
        analysis_type="Spontaneous walking", stride_detection_method=RUSTLAB1_METHOD, likelihood_threshold=0.0
    )
    standalone = RustLab1StandaloneSettings(frame_rate=cfg.frame_rate, likelihood_threshold=0.0)
    preprocessed = prepare_alma_coordinates(aligned, standalone, alma_signal_filter)
    expected = detect_rustlab1_strides(preprocessed, standalone, pd, np)
    mask, _ = rustlab1_stance_mask(preprocessed.series["d-back-left"]["x"], standalone, np)
    actual, starts, ends, _ = bottom_detection(raw, "left", cfg)
    np.testing.assert_array_equal(actual, mask)
    assert starts == expected["stride_start (frame)"].tolist()
    assert ends == expected["stride_end (frame)"].tolist()
    # Changes to speed and phase settings must affect the algorithm, not just the UI.
    changed = bottom_detection(raw, "left", replace(cfg, stance_speed_threshold_px_frame=3.0))
    assert changed[1] != starts


@pytest.mark.parametrize("method", STRIDE_METHODS)
def test_preview_and_export_use_identical_candidate_boundaries(paired_recording, method):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import calculate_recording_table
    from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_result_writer import GaitResultWriter

    paths = dict(paired_recording)
    cfg = AlmaSettings(
        analysis_type="Spontaneous walking",
        stride_detection_method=method,
        likelihood_threshold=0.0,
        pixels_per_cm=50.0,
        n_continuous_strides=1,
    )
    preview = create_gait_preview()
    recordings = preview._recordings(paired_recording, cfg)
    item = AlmaViewCsvSet("test", paths["Left"], paths["Right"], paths["Bottom"])
    table, _ = calculate_recording_table(item, cfg, GaitResultWriter(), pd)
    for label, recording in recordings:
        actual = set(pd.to_numeric(table[f"{label.lower()}__stride_start (frame)"]).dropna())
        assert actual == set(pd.to_numeric(recording[0]["stride_start (frame)"]))
        if method == RUSTLAB1_METHOD:
            assert len(actual) > 1  # The old display count never truncates exported analysis.


def test_no_cycles_keeps_a_skeleton_without_fabricated_stride_labels(tmp_path, alma_fixtures_dir):
    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[0, 1, 2])
    for column in raw:
        if column[-1] in ("x", "y"):
            raw[column] = raw[column].iloc[0]
    path = tmp_path / "stationary.csv"
    raw.to_csv(path, index=False)
    cfg = AlmaSettings(
        analysis_type="Spontaneous walking",
        pixels_per_cm=50.0,
        likelihood_threshold=0.0,
        stride_detection_method="Adaptive paw speed",
    )
    plots, _, _ = create_gait_preview().prepare((("Left", path),), cfg)
    svg = plots[0][1].decode()
    assert "Full recording" in svg and "0 strides" in svg
    assert "stick-frame-" in svg and "stride-start-" not in svg


def test_legacy_mask_is_aligned_and_cycles_never_cross_long_tracking_gaps():
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_spontaneous_cycles import (
        robust_stance_segments_from_toe,
    )

    frame = np.arange(400)
    x = frame * 0.3 + 10 * np.cos(frame * 2 * np.pi / 40)
    y = 100 - 8 * np.sin(frame * 2 * np.pi / 40)
    confidence = np.ones(len(frame))
    confidence[170:195] = 0.1
    raw_mask, _, _, _ = robust_stance_segments_from_toe(x, y, confidence, 120)
    mask, starts, ends, _ = detect_strides(x, y, confidence, 120, method="ALMA (legacy)")
    assert len(mask) == len(frame)
    np.testing.assert_array_equal(mask[1:170], raw_mask[:169])
    assert all(not (start <= 194 and end >= 170) for start, end in zip(starts, ends, strict=True))
    assert all(end < len(frame) - 1 for end in ends)
