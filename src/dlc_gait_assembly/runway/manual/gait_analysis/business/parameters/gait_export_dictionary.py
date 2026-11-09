"""Describe exported scientific columns using the same typed definitions as the UI."""

import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_contracts import (
    GaitParameterDefinition,
    ParameterExtractionType,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    gait_parameter_catalog,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.stroke_recovery_parameter_definitions import (
    RECOVERY_OUTCOMES,
    SOURCE,
)


def summary_definition(name):
    if name in {f"{side}__median_cycle_velocity (cm/s)" for side in ("left", "right")}:
        side = name.split("__", 1)[0]
        return GaitParameterDefinition(
            name,
            "ALMA",
            "Multi-view",
            f"{side.title()} side view",
            "Toe",
            "median ALMA cycle velocity over complete accepted same-side strides in the common camera interval",
            extraction_type=ParameterExtractionType.SPATIOTEMPORAL,
            unit="cm/s",
            output_level="recording",
            method_note="Retained as gait-speed context. Independent medians do not establish speed matching between sides or sessions.",
        )
    for outcome in RECOVERY_OUTCOMES:
        for side in ("left", "right"):
            if name == f"{side}__{outcome.key}_median ({outcome.unit})":
                return GaitParameterDefinition(
                    name,
                    SOURCE,
                    "Multi-view",
                    f"{side.title()} side view",
                    outcome.markers,
                    "median of complete accepted same-side strides inside the common camera interval",
                    f"{side.title()} {outcome.label.lower()} median",
                    extraction_type=ParameterExtractionType.SPATIOTEMPORAL
                    if outcome.key.endswith("duration") or outcome.key == "stride_length"
                    else ParameterExtractionType.KINEMATICS,
                    unit=outcome.unit,
                    output_level="recording",
                    reference=outcome.reference,
                    method_note="Independent side summary; not baseline-normalized. Counts are reported separately. RustLab1 mm measurements are converted to cm where applicable.",
                )
            if name == f"{side}__{outcome.key}_valid_strides":
                return GaitParameterDefinition(
                    name,
                    SOURCE,
                    "Multi-view",
                    f"{side.title()} side view",
                    outcome.markers,
                    "count of finite nonnegative outcome values from complete accepted strides inside the common interval",
                    extraction_type=ParameterExtractionType.QUALITY_CONTROL,
                    unit="strides",
                    output_level="recording",
                )
    return None


def parameter_dictionary(tables):
    """Only list scientific measurements that actually occur in these outputs."""
    catalog = {definition.name: definition for definition in gait_parameter_catalog()}
    rows = []
    for table_name, table in tables.items():
        for column in table:
            definition = catalog.get(f"{table_name}__{column}") or catalog.get(column)
            if definition is None and table_name == "general":
                definition = summary_definition(column)
            if definition is None:
                continue
            rows.append(
                {
                    "table": table_name,
                    "column": column,
                    "display_name": definition.display_name or column,
                    "extraction_type": definition.extraction_type.value,
                    "unit": definition.unit,
                    "output_level": "recording" if table_name == "general" else "stride",
                    "source": definition.source,
                    "formula": definition.calculation,
                    "required_markers": definition.markers,
                    "reference": definition.reference,
                    "method_note": definition.method_note,
                }
            )
    return pd.DataFrame(
        rows,
        columns=(
            "table",
            "column",
            "display_name",
            "extraction_type",
            "unit",
            "output_level",
            "source",
            "formula",
            "required_markers",
            "reference",
            "method_note",
        ),
    )
