import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    gait_parameter_catalog, selected_combined_output,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.retired_custom_parameters import RETIRED_CUSTOM_NAMES
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.synchronized_parameter_definitions import build_feature_dictionary


def test_retired_custom_selections_cannot_restore_parameters_or_dictionary_rows():
    assert not any(item.source == "Custom SOP" for item in gait_parameter_catalog())
    assert not RETIRED_CUSTOM_NAMES.intersection(item.name for item in gait_parameter_catalog())
    table = pd.DataFrame({"gait_cycle": [1], "stride length (cm)": [2.0],
                          **dict.fromkeys(RETIRED_CUSTOM_NAMES, [123.0]),
                          "left__left_mtp_average_height__sd": [4.0]})
    settings = AlmaSettings(enabled_parameter_names=(*RETIRED_CUSTOM_NAMES, "stride length (cm)"))
    result = selected_combined_output(table, settings)
    assert list(result) == ["gait_cycle", "stride length (cm)"]
    dictionary = build_feature_dictionary(table, pd)
    assert not RETIRED_CUSTOM_NAMES.intersection(dictionary["feature"])
    assert "left__left_mtp_average_height__sd" not in set(dictionary["feature"])
