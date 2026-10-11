"""The stick plot must visualize the chosen detector, on the same source frames."""

import re
from io import BytesIO

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine import calculate_alma_recording
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_continuous_sequences import (
    prepare_continuous_stickplot,
    prepare_full_recording_stickplot,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.gait_stride_detection import (
    BOTTOM_METHODS,
    STRIDE_METHODS,
    bottom_detection,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
    render_prepared_stickplot,
    stickplot_phase_codes,
)


@pytest.mark.parametrize("method", STRIDE_METHODS)
def test_stickplot_phases_boundaries_and_title_match_actual_detector(method, alma_fixtures_dir):
    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    settings = AlmaSettings(
        analysis_type="Spontaneous walking",
        stride_detection_method=method,
        likelihood_threshold=0.0,
        pixels_per_cm=50.0,
        no_outlier_filter=True,
        stance_speed_threshold_px_frame=0.6,
    )
    detection, trace = None, {}
    if method in BOTTOM_METHODS:
        frames = np.arange(len(raw))
        bottom = pd.DataFrame(
            {
                ("lhpaw", "x"): frames * 0.25 + 8 * np.cos(frames * 2 * np.pi / 40),
                ("lhpaw", "y"): 100 - 5 * np.sin(frames * 2 * np.pi / 40),
                ("lhpaw", "likelihood"): np.ones(len(raw)),
            }
        )
        detection = bottom_detection(bottom, "left", settings, diagnostics=trace)
    parameters, coords, stance, bodyparts, masks, starts, _ = calculate_alma_recording(
        raw, settings, cycle_detection=detection, detection_diagnostics=trace
    )
    if detection is not None:
        np.testing.assert_array_equal(stance, detection[0])
    prepared = prepare_full_recording_stickplot(parameters, coords, bodyparts, stance)
    assert prepared is not None
    assert (prepared.start_frame, prepared.end_frame) == (0, len(raw) - 1)
    assert prepared.method == method
    expected = stickplot_phase_codes(
        stance, len(coords), prepared.trusted, prepared.dragging, prepared.phase_confidence
    )
    buffer = BytesIO()
    render_prepared_stickplot(prepared, buffer)
    svg = buffer.getvalue().decode()
    assert method in svg and prepared.timing_source in svg
    assert "Stance" in svg and "Swing" in svg
    strip = np.full(len(coords), "", dtype=object)
    for start, end, phase in re.findall(r'id="phase-(\d+)-(\d+)-(\w+)"', svg):
        strip[int(start) : int(end) + 1] = phase
    visible = slice(prepared.start_frame, prepared.end_frame + 1)
    np.testing.assert_array_equal(strip[visible], expected[visible])
    for frame, phase in re.findall(r'id="stick-frame-(\d+)-(\w+)-segment-\d+"', svg):
        assert phase == expected[int(frame)]
    # Include the final frame, even if it is odd, and retain actual cycle starts.
    assert f'id="stick-frame-{prepared.end_frame}-' in svg
    for start in prepared.parameters["stride_start (frame)"]:
        assert f'id="stride-start-{int(float(start))}"' in svg
    if detection is not None:
        assert "Bottom left hind paw" in svg


def test_preview_does_not_span_a_missing_cycle(alma_fixtures_dir):
    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    settings = AlmaSettings(analysis_type="Spontaneous walking", pixels_per_cm=50.0, likelihood_threshold=0.0)
    _, coords, stance, bodyparts, _, _, _ = calculate_alma_recording(raw, settings)
    parameters = pd.DataFrame(
        {
            "stride_start (frame)": [0, 100, 110],
            "stride_end (frame)": [9, 109, 119],
            "cycle duration (s)": [0.1, 0.1, 0.1],
        }
    )
    prepared = prepare_continuous_stickplot(parameters, coords, bodyparts, stance, 10)
    assert (prepared.start_frame, prepared.end_frame) == (100, 119)
    assert len(prepared.parameters) == 2


def test_missing_phase_is_not_silently_drawn_as_swing():
    assert stickplot_phase_codes([1, 0, 1], 5, [True, False, True, True, True]).tolist() == [
        "stance",
        "unknown",
        "stance",
        "unknown",
        "unknown",
    ]


def test_spontaneous_stick_geometry_matches_measurement_filter(alma_fixtures_dir):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import fix_column_names

    raw = pd.read_csv(alma_fixtures_dir / "alma_edge_cases_filtered.csv", header=[1, 2])
    settings = AlmaSettings(analysis_type="Spontaneous walking", pixels_per_cm=50.0, likelihood_threshold=0.0)
    normalized, _, _ = fix_column_names(raw.copy(), None)
    _, coords, _, bodyparts, _, _, _ = calculate_alma_recording(raw, settings)
    for marker in bodyparts:
        np.testing.assert_allclose(
            coords[f"{marker} x"],
            butterworth_filter(normalized[f"{marker} x"], settings.frame_rate, settings.filter_cutoff),
        )


def test_method_description_and_selection_invalidate_previous_stickplot():
    from PySide6.QtWidgets import QApplication
    from dlc_gait_assembly.app.app_bootstrap import create_gait_analysis_operations, create_gait_preview
    from dlc_gait_assembly.runway.manual.gait_analysis.client.gait_analysis_view import AlmaKinematicsWidget
    from dlc_gait_assembly.shared.infrastructure.workspace_path_resolver import resolve_workspace

    app = QApplication.instance() or QApplication([])
    view = AlmaKinematicsWidget(
        preview=create_gait_preview(), analysis=create_gait_analysis_operations(), workspace=resolve_workspace()
    )
    view.analysis_type_combo.setCurrentText("Spontaneous walking")
    view.state.preview_validity.complete()
    view.stride_method_combo.setCurrentText("Bottom paw speed")
    assert not view.state.preview_validity.ready
    assert "lhpaw sets left timing" in view.stride_method_description.text()
    assert view.setup._collect_settings().stride_detection_method == "Bottom paw speed"
    view.close()
    app.processEvents()
