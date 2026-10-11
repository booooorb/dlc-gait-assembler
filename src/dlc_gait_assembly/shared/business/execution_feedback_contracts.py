"""Progress reporting and cooperative cancellation independent of an event loop."""

from collections.abc import Callable
from dataclasses import dataclass


class ExecutionCancelled(Exception):
    """The user requested cancellation before the next unit of work."""


@dataclass(frozen=True)
class ExecutionFeedback:
    progress: Callable[[int, int, str], None] = lambda current, total, message: None
    cancelled: Callable[[], bool] = lambda: False

    cancellation_check: Callable[[], None] = lambda: None

    def checkpoint(self):
        self.cancellation_check()
        if self.cancelled():
            raise ExecutionCancelled("Execution was cancelled.")


@dataclass(frozen=True)
class ExecutionProgress:
    """A callable progress reporter with an explicit cancellation checkpoint for idle processes."""

    report: Callable[[int, int, str], None]
    checkpoint: Callable[[], None]

    def __call__(self, current, total, message):
        self.checkpoint()
        self.report(current, total, message)
