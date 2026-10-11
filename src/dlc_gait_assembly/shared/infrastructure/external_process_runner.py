"""Execute commands, stream merged output, and terminate owned process groups on cancellation."""

from __future__ import annotations

import os
import signal
import subprocess
from queue import Empty, Queue
from threading import Event, Lock, Thread

from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionCancelled
from dlc_gait_assembly.shared.business.external_command_contracts import ExternalCommand, ExternalCommandResult


class ExternalProcessSession:
    def __init__(self):
        self._process = None
        self._cancelled = Event()
        self._lock = Lock()

    def run(self, command: ExternalCommand, output=None, *, cancelled=None, checkpoint=None) -> ExternalCommandResult:
        if self._cancelled.is_set():
            raise ExecutionCancelled("Command cancelled before it started.")
        process = subprocess.Popen(
            list(command.arguments),
            cwd=command.cwd,
            env=command.environment,
            text=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=os.name != "nt",
        )
        with self._lock:
            self._process = process
        queue = Queue()

        def read_output():
            try:
                for line in process.stdout:
                    queue.put(line)
            finally:
                queue.put(None)

        reader = Thread(target=read_output, daemon=True)
        reader.start()
        lines = []
        try:
            while True:
                if checkpoint is not None:
                    checkpoint()
                if self._cancelled.is_set() or (cancelled is not None and cancelled()):
                    raise ExecutionCancelled("Command cancelled.")
                try:
                    line = queue.get(timeout=0.1)
                except Empty:
                    continue
                if line is None:
                    break
                lines.append(line)
                if output is not None:
                    output(line)
            return ExternalCommandResult(process.wait(), "".join(lines))
        except BaseException:
            self.cancel()
            raise
        finally:
            if process.poll() is None:
                self._stop(process)
            reader.join(timeout=2)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    stream.close()
            with self._lock:
                self._process = None

    def write(self, text: str) -> None:
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None and process.stdin is not None:
                process.stdin.write(text)
                process.stdin.flush()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            process = self._process
        if process is not None:
            self._stop(process)

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return
        try:
            if os.name == "nt":
                process.terminate()
            else:
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=0.75)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
        except ProcessLookupError:
            pass
