"""Application route identities and selected navigation state without widget factories."""

from dataclasses import dataclass
from enum import Enum


class AppRoute(str, Enum):
    HOME = "home"
    RUNWAY = "runway"
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    PROFILES = "profiles"
    LADDER = "ladder"


@dataclass
class AppNavigationState:
    tool_id: str | None = None
    home_active: bool = True
    automatic_active: bool = False
    automatic_page: str = "run"

    @property
    def route(self):
        if self.home_active:
            return AppRoute.HOME
        if self.tool_id == "ladder_analysis":
            return AppRoute.LADDER
        if self.automatic_active:
            return AppRoute.PROFILES if self.automatic_page == "profiles" else AppRoute.AUTOMATIC
        return AppRoute.MANUAL if self.tool_id is not None else AppRoute.RUNWAY
