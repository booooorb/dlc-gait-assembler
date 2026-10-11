"""External commands can be stopped even when they emit no process output."""

import sys
from threading import Timer
from time import monotonic

import pytest

from dlc_gait_assembly.runway.automatic.runs.business.automatic_execution_control import (
    AutomaticExecutionControl,
    AutomaticRunCancelled,
)
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand
from dlc_gait_assembly.shared.infrastructure.external_process_runner import ExternalProcessSession


def test_quiet_command_obeys_automatic_cancellation():
    control = AutomaticExecutionControl()
    session = ExternalProcessSession()
    timer = Timer(0.2, control.request_cancel)
    timer.start()
    started = monotonic()
    try:
        with pytest.raises(AutomaticRunCancelled):
            session.run(
                ExternalCommand((sys.executable, "-c", "import time; time.sleep(60)")),
                checkpoint=control.check_cancelled,
            )
    finally:
        timer.cancel()
        session.cancel()
    assert monotonic() - started < 4


def test_commands_stream_output_and_preserve_failure_status():
    lines = []
    result = ExternalProcessSession().run(
        ExternalCommand((sys.executable, "-c", 'print("message", flush=True); raise SystemExit(9)')), lines.append
    )
    assert result.returncode == 9
    assert "".join(lines) == result.output == "message\n"
