"""Calculate signed left/right asymmetry measurements."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import (
    ALMA_ASYMMETRY_COLUMNS as _ALMA_ASYMMETRY_COLUMNS,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_feature_calculations import (
    column_difference as _column_difference,
)


def add_asymmetry_features(dataframe, lesion_hemisphere: str, np):
    result = dataframe.copy()
    if lesion_hemisphere == "right":
        (contralesional, ipsilesional) = ("left", "right")
    elif lesion_hemisphere == "left":
        (contralesional, ipsilesional) = ("right", "left")
    else:
        contralesional = ipsilesional = None
    for output_name, base_name in _ALMA_ASYMMETRY_COLUMNS.items():
        if contralesional is None:
            result[output_name] = np.nan
            continue
        result[output_name] = normalized_asymmetry(
            result.get(f"{contralesional}__{base_name}"), result.get(f"{ipsilesional}__{base_name}"), np
        )
    left_excursion = _column_difference(result, "left__back__protraction", "left__back__retraction", np)
    right_excursion = _column_difference(result, "right__back__protraction", "right__back__retraction", np)
    if contralesional == "left":
        (contra_excursion, ipsi_excursion) = (left_excursion, right_excursion)
    elif contralesional == "right":
        (contra_excursion, ipsi_excursion) = (right_excursion, left_excursion)
    else:
        contra_excursion = ipsi_excursion = None
    result["protraction_retraction_excursion_asymmetry"] = normalized_asymmetry(contra_excursion, ipsi_excursion, np)
    return result


def normalized_asymmetry(contralesional, ipsilesional, np):
    if contralesional is None or ipsilesional is None:
        return np.nan
    denominator = 0.5 * (contralesional.abs() + ipsilesional.abs())
    return (contralesional - ipsilesional) / denominator.replace(0, np.nan)
