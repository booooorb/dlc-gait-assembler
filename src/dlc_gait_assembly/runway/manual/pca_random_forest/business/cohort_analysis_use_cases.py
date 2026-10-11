"""Coordinate cohort preparation, numerical analyses, and output generation through ports."""

from __future__ import annotations

from pathlib import Path

from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_contracts import CohortAnalysisResult
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_analysis_ports import CohortResultExportPort
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_feature_audit import audit_and_select_features
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_feature_audit import coerce_bool as _coerce_bool
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_mixed_effects_analysis import (
    run_mixed_effects as _run_mixed_effects,
)
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_pca_analysis import run_pca as _run_pca
from dlc_gait_assembly.runway.manual.pca_random_forest.business.cohort_random_forest_analysis import (
    run_grouped_random_forest as _run_grouped_random_forest,
)


def run_stroke_cohort_analysis(
    session_summary_paths,
    output_folder: Path,
    *,
    run_pca: bool = True,
    run_random_forest: bool = True,
    run_mixed_effects: bool = True,
    outputs: CohortResultExportPort,
) -> CohortAnalysisResult:
    """Run leakage-safe cohort analyses and write portable CSV/SVG results."""
    import numpy as np

    outputs.prepare(output_folder)
    import pandas as pd

    data = outputs.read_summaries(session_summary_paths, pd)
    combined_path = output_folder / "stroke_session_summaries.csv"
    outputs.write_table(data, combined_path, index=False)
    output_files = [combined_path]
    messages = [f"Loaded {len(data)} animal-session row(s) from {len(session_summary_paths)} file(s)."]
    if "session_usable" in data:
        usable = data["session_usable"].map(_coerce_bool)
        unusable_fraction = float((~usable).mean()) if len(usable) else float("nan")
        acceptance = pd.DataFrame(
            [
                {
                    "criterion": "unusable animal-sessions",
                    "target": "< 20%",
                    "observed": unusable_fraction,
                    "passed": bool(unusable_fraction < 0.2),
                    "notes": "Other pilot criteria require manual-event and test-retest annotation inputs.",
                }
            ]
        )
        acceptance_path = output_folder / "pilot_acceptance_summary.csv"
        outputs.write_table(acceptance, acceptance_path, index=False)
        output_files.append(acceptance_path)
        messages.append(
            f"Pilot usability: {unusable_fraction:.1%} unusable animal-session(s) ({('pass' if unusable_fraction < 0.2 else 'review required')}; target <20%)."
        )
    (features, redundancy) = audit_and_select_features(data, pd, np)
    redundancy_path = output_folder / "feature_redundancy_report.csv"
    outputs.write_table(redundancy, redundancy_path, index=False)
    output_files.append(redundancy_path)
    messages.append(f"Retained {len(features)} model-ready features after non-outcome-based redundancy control.")
    if run_pca:
        (paths, detail) = outputs.export_calculation(_run_pca(data, features, pd, np), output_folder)
        output_files.extend(paths)
        messages.append(detail)
    if run_random_forest:
        (paths, detail) = outputs.export_calculation(_run_grouped_random_forest(data, features, pd, np), output_folder)
        output_files.extend(paths)
        messages.append(detail)
    if run_mixed_effects:
        (paths, detail) = outputs.export_calculation(_run_mixed_effects(data, pd, np), output_folder)
        output_files.extend(paths)
        messages.append(detail)
    return CohortAnalysisResult(tuple(output_files), tuple(messages))
