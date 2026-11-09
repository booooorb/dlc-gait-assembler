"""Define parameter metadata, source categories, and limb-scope selection contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ParameterExtractionType(str, Enum):
    SPATIOTEMPORAL = "Spatiotemporal"
    KINEMATICS = "Limb kinematics"
    SWING = "Swing-phase kinematics"
    COORDINATION = "Interlimb coordination"
    ASYMMETRY = "Bilateral asymmetry"
    VARIABILITY = "Stride variability"
    QUALITY_CONTROL = "Quality control"


@dataclass(frozen=True)
class GaitParameterDefinition:
    name: str
    source: str
    view_mode: str
    views: str
    markers: str
    calculation: str
    display_name: str = ""
    extraction_type: ParameterExtractionType = ParameterExtractionType.KINEMATICS
    unit: str = ""
    output_level: str = "stride"
    reference: str = ""
    method_note: str = ""
    forelimb: bool = False
