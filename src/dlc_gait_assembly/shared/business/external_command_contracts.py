"""Command arguments, completion, and interactive process contracts without an event loop."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ExternalCommand:
    arguments: tuple[str, ...]
    cwd: Path | None = None
    environment: Mapping[str, str] | None = None


@dataclass(frozen=True)
class ExternalCommandResult:
    returncode: int
    output: str


class CommandSessionPort(Protocol):
    def run(
        self,
        command: ExternalCommand,
        output: Callable[[str], None] | None = None,
        *,
        cancelled: Callable[[], bool] | None = None,
        checkpoint: Callable[[], None] | None = None,
    ) -> ExternalCommandResult: ...
    def write(self, text: str) -> None: ...
    def cancel(self) -> None: ...
