"""Features publish operations through named use cases rather than import facades."""

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_use_cases import VideoProcessingUseCases
from dlc_gait_assembly.runway.manual.knee_correction.business.knee_correction_use_cases import KneeCorrectionUseCases
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_analysis_use_cases import GaitAnalysisUseCases
from dlc_gait_assembly.ladder.business.ladder_analysis_use_cases import LadderAnalysisUseCases


def test_public_use_cases_accept_explicit_io_contracts():
    (exporter, coordinates, results) = (object(), object(), object())
    assert VideoProcessingUseCases(exporter).exporter is exporter
    knee = KneeCorrectionUseCases(coordinates, results)
    assert knee.coordinates is coordinates
    assert knee.results is results
    assert GaitAnalysisUseCases(results).outputs is results
    ladder = LadderAnalysisUseCases(coordinates, results)
    assert ladder.coordinates is coordinates
    assert ladder.events is results


def test_manual_stage_definitions_preserve_application_order():
    from dlc_gait_assembly.runway.manual.business.manual_stage_definitions import MANUAL_STAGE_DEFINITIONS
    from dlc_gait_assembly.app.app_bootstrap import build_tool_specs

    expected = (
        "manual_calibration",
        "video_processing",
        "deeplabcut",
        "knee_correction",
        "gait_parameter_analysis",
        "pca_random_forest",
    )
    assert tuple(stage.id for stage in MANUAL_STAGE_DEFINITIONS) == expected
    tools, _ = build_tool_specs()
    assert tuple(spec.id for spec in tools) == expected
    assert tuple(spec.label for spec in tools) == tuple(stage.label for stage in MANUAL_STAGE_DEFINITIONS)


def test_ladder_execution_and_review_use_injected_ports(tmp_path):
    import pytest
    from dataclasses import replace
    from dlc_gait_assembly.ladder.business.ladder_analysis_contracts import LadderEvent, LadderSettings

    exported = []

    class Events:
        def write(self, events, destination, combined=False):
            exported.append((events, destination, combined))
            return destination

    calls = []
    result = object()

    def execute(*args):
        calls.append(args)
        return result

    use_cases = LadderAnalysisUseCases(object(), Events(), execution=execute)
    source, output = tmp_path / "source.csv", tmp_path / "results"
    settings = LadderSettings()
    assert use_cases.run(source, output, settings, ["paw"]) is result
    assert calls == [(source, output, settings, ["paw"])]
    event = LadderEvent("paw", 5, 3, 7, 12.0, 2.0, 0.04, classification="slip")
    destination = tmp_path / "reviewed.csv"
    assert use_cases.export_reviewed([event], destination) == destination
    assert exported == [([event], destination, False)]
    with pytest.raises(ValueError, match="classification"):
        use_cases.export_reviewed([replace(event, classification="invalid")], destination)
    assert len(exported) == 1
