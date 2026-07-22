"""Compatibility facade for the automated-pipeline workspace.

New code should import from :mod:`dlc_gait_assembly.gui.automated_pipeline`.
"""

from dlc_gait_assembly.gui.automated_pipeline.workspace import (
    AutomatedPipelineProfilesWidget,
)

__all__ = ["AutomatedPipelineProfilesWidget"]
