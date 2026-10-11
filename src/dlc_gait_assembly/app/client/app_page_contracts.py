"""Define page factories, typed manual snapshots, and public page lifecycle contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtWidgets import QWidget

from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_from_manual import ManualProfileSnapshot


@dataclass(frozen=True)
class ToolSpec:
    id: str
    label: str
    widget_factory: Callable[[], QWidget] | None = None
    enabled: bool = False
    description: str = ""
    snapshot_provider: Callable[[QWidget], ManualProfileSnapshot] | None = None
    connect_back: Callable[[QWidget, Callable[[], None]], None] | None = None


class ApplicationPage(Protocol):
    """The shell uses these operations without inspecting feature internals."""

    def can_close(self, parent=None) -> bool: ...

    def release_resources(self) -> None: ...

    def apply_theme(self) -> None: ...
