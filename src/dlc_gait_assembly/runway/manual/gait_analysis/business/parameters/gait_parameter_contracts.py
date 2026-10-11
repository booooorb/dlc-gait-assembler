"""Define parameter metadata, source categories, and limb-scope selection contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GaitParameterDefinition:
    name: str
    source: str
    view_mode: str
    views: str
    markers: str
    calculation: str
    display_name: str = ""
