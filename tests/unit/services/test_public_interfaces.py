from dlc_gait_assembly.services import analysis_manifests, automated_profiles
from dlc_gait_assembly.services.manifests import read_analysis_manifest
from dlc_gait_assembly.services.pipeline.alma import (
    AlmaRunResult,
    AlmaSettings,
    AlmaViewCsvSet,
)
from dlc_gait_assembly.services.pipeline.automated import (
    AUTOMATED_STAGE_SPECS,
    AutomatedStage,
    ReviewArtifact,
    StageReview,
    StageSpec,
)
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RustLab1Extraction,
    extract_rustlab1_parameters,
    generate_rustlab1_figures,
)
from dlc_gait_assembly.services.profiles import ProfileDraft


def test_compatibility_facades_reexport_public_apis():
    assert analysis_manifests.read_analysis_manifest is read_analysis_manifest
    assert automated_profiles.ProfileDraft is ProfileDraft


def test_pipeline_package_interfaces_remain_importable():
    assert all(value is not None for value in (AlmaSettings, AlmaRunResult, AlmaViewCsvSet))
    assert all(
        value is not None
        for value in (
            AutomatedStage,
            StageSpec,
            ReviewArtifact,
            StageReview,
            RustLab1Extraction,
            extract_rustlab1_parameters,
            generate_rustlab1_figures,
        )
    )
    assert tuple(spec.stage for spec in AUTOMATED_STAGE_SPECS) == tuple(AutomatedStage)
