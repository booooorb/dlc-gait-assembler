"""Compatibility facade for automated-profile APIs.

New code should import from :mod:`dlc_gait_assembly.services.profiles`.
"""

from dlc_gait_assembly.services.profiles import (
    AutomatedPipelineProfile,
    AutomatedProfileStore,
    ProfileDraft,
    regions_from_processing_manifest,
    validate_profile_draft,
)

__all__ = [
    "AutomatedPipelineProfile",
    "AutomatedProfileStore",
    "ProfileDraft",
    "regions_from_processing_manifest",
    "validate_profile_draft",
]
