"""Describe available application updates and the injected update operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

REPOSITORY = "booooorb/dlc-gait-assembler"
PROJECT_URL = f"https://github.com/{REPOSITORY}"


class AppUpdateError(RuntimeError):
    """An update could not be checked or installed safely."""


@dataclass(frozen=True)
class AppUpdateInfo:
    current_version: str
    available: bool = False
    current_revision: str = ""
    latest_revision: str = ""
    latest_version: str = ""
    branch: str = "main"
    checkout: Path | None = None
    blocked_reason: str = ""
    local_branch: str = ""

    @property
    def current_label(self) -> str:
        revision = f" ({self.current_revision[:8]})" if self.current_revision else ""
        return f"{self.current_version}{revision}"

    @property
    def latest_label(self) -> str:
        return self.latest_version or f"{self.branch} ({self.latest_revision[:8]})"


class AppUpdateOperations(Protocol):
    def check(self) -> AppUpdateInfo: ...

    def install(self, update: AppUpdateInfo, progress: Callable[[str], None]) -> None: ...

    def restart(self) -> None: ...
