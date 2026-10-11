"""Four bottom paw markers must suffice without a center or tail marker."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings
from dlc_gait_assembly.runway.manual.gait_analysis.business.custom_features.custom_sop_feature_calculations import (
    extract_custom_sop_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_marker_requirements import (
    BOTTOM_VIEW_LABELS,
    auto_bodypart_label,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.bottom_paw_parameter_contract import (
    RETIRED_BOTTOM_PARAMETER_NAMES,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    gait_parameter_catalog,
    selected_combined_output,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
    align_multiview_coordinates,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_feature_extraction import (
    extract_rustlab1_parameters,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_feature_calculations import (
    bottom_trajectories,
)

PAWS = {"lhpaw": "back left", "rhpaw": "back right", "lfpaw": "front left", "rfpaw": "front right"}
BOTTOM_FEATURES = {
    "mean_hindlimb_base_support",
    "variance_hindlimb_base_support",
    "left_right_hindlimb_phase_offset",
    "hindlimb_stance_overlap_fraction",
    "left__front__seconds",
    "right__front__seconds",
    "FLBR_RATIO",
    "FRBL_RATIO",
}
IDENTITY_FILTER = SimpleNamespace(butterworth_filter=lambda values, _fps, _cutoff: values)


def four_paw_recording():
    movement = np.tile([0, 0, 0, 0, 0, 0, 10, 20, 30, 40], 6).astype(float)
    bottom = {}
    # Deliberately use a different column order from the anatomical mapping.
    for index, label in enumerate(("rfpaw", "lhpaw", "lfpaw", "rhpaw")):
        bottom[label, "x"] = movement
        bottom[label, "y"] = np.full(len(movement), index * 10.0)
        bottom[label, "likelihood"] = np.ones(len(movement))
    side = {}
    for label in ("toe", "mtp", "ankle", "knee", "hip", "iliac crest"):
        side[label, "x"] = movement
        side[label, "y"] = np.ones(len(movement))
        side[label, "likelihood"] = np.ones(len(movement))
    return align_multiview_coordinates(
        {"bottom": pd.DataFrame(bottom), "left": pd.DataFrame(side), "right": pd.DataFrame(side)},
        pd,
    )


def test_four_paw_aliases_work_independently_of_order():
    assert set(BOTTOM_VIEW_LABELS) == set(PAWS.values())
    for label, standard in PAWS.items():
        assert auto_bodypart_label(list(reversed(PAWS)), standard) == label
    raw = four_paw_recording()
    assert {marker for marker, _ in raw if marker.startswith("d-")} == {
        "d-back-left",
        "d-back-right",
        "d-front-left",
        "d-front-right",
    }


def test_supported_bottom_features_calculate_without_center_or_tail():
    raw = four_paw_recording()
    settings = AlmaSettings(limb_scope="Hindlimb + Forelimb", pixels_per_cm=10.0, calibration_method="manual")
    cycles = pd.DataFrame({"stride_start (frame)": [10], "stride_end (frame)": [49]})
    rustlab = extract_rustlab1_parameters(raw, cycles, settings, IDENTITY_FILTER)
    custom = extract_custom_sop_parameters(raw, cycles, settings, IDENTITY_FILTER)
    assert BOTTOM_FEATURES.issubset(set(rustlab.available_parameters) | set(custom.available_parameters))
    assert not RETIRED_BOTTOM_PARAMETER_NAMES.intersection(rustlab.dataframe.columns)
    assert not RETIRED_BOTTOM_PARAMETER_NAMES.intersection(custom.dataframe.columns)
    assert custom.dataframe.loc[0, "mean_hindlimb_base_support"] == pytest.approx(2.0)
    assert custom.dataframe.loc[0, "variance_hindlimb_base_support"] == pytest.approx(0.0)
    assert not any("center" in name for name in (*rustlab.missing_markers, *custom.missing_markers))


def test_center_absence_does_not_reduce_synchronized_tracking_coverage():
    trajectories, qc = bottom_trajectories(
        four_paw_recording(),
        AlmaSettings(pixels_per_cm=10.0),
        {"x_pixels_per_cm": 10.0, "y_pixels_per_cm": 10.0},
        IDENTITY_FILTER,
        pd,
        np,
    )
    assert trajectories["required_tracking_valid"].all()
    assert qc["required_tracking_coverage"] == 1.0
    assert "body_speed_cm_s" not in trajectories
    assert not any("center" in key for key in qc["marker_coordinate_coverage"])


@pytest.mark.parametrize("selection", [None, tuple(RETIRED_BOTTOM_PARAMETER_NAMES)])
def test_retired_profile_selections_cannot_restore_center_parameters(selection):
    table = pd.DataFrame({"animal_id": ["mouse"], **dict.fromkeys(RETIRED_BOTTOM_PARAMETER_NAMES, [1.0])})
    output = selected_combined_output(table, AlmaSettings(enabled_parameter_names=selection))
    assert list(output) == ["animal_id"]


def test_parameter_documentation_lists_paw_only_bottom_requirements():
    catalog = gait_parameter_catalog()
    assert not RETIRED_BOTTOM_PARAMETER_NAMES.intersection(item.name for item in catalog)
    bottom = [item for item in catalog if item.views == "Bottom view"]
    assert {item.name for item in bottom} == BOTTOM_FEATURES
    assert all("center" not in item.markers.lower() and "tail" not in item.markers.lower() for item in catalog)
    assert all("paw" in item.markers for item in bottom)
