"""Verify DeepLabCut bridge failures surface subprocess diagnostics."""

import sys

import pytest

from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure import deeplabcut_bridge_client


@pytest.mark.parametrize("exit_code", [0, 2])
def test_bridge_reports_process_output_when_the_result_is_missing(monkeypatch, exit_code):
    script = f'import sys; print("DeepLabCut could not load the model", file=sys.stderr); sys.exit({exit_code})'
    monkeypatch.setattr(
        deeplabcut_bridge_client, "deeplabcut_analysis_arguments", lambda *_: (sys.executable, "-c", script)
    )
    progress = []

    with pytest.raises(RuntimeError, match=rf"code {exit_code}\b") as error:
        deeplabcut_bridge_client.run_bridge_request(
            {"operation": "analyze"},
            1,
            "analysis",
            "Initializing DeepLabCut model",
            "DeepLabCut analysis",
            lambda value, *_: progress.append(value),
        )

    if exit_code == 0:
        assert "without returning an output manifest" in str(error.value)
    assert "DeepLabCut could not load the model" in str(error.value)
    assert progress == [0]
