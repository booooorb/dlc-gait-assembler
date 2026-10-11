"""Paired coordinate persistence retains nonstandard HDF keys and upstream metadata."""

import numpy as np
import pandas as pd

from dlc_gait_assembly.shared.infrastructure.coordinate_h5_codec import read_dlc_h5, write_dlc_h5


def test_h5_round_trip_keeps_coordinates_and_custom_metadata(tmp_path):
    columns = pd.MultiIndex.from_product(
        [["DLC_custom"], ["hip", "knee", "toe"], ["x", "y", "likelihood"]], names=["scorer", "bodyparts", "coords"]
    )
    table = pd.DataFrame(np.arange(45, dtype=float).reshape(5, 9), columns=columns)
    table.iloc[2, 0] = np.nan
    source, output = tmp_path / "original.h5", tmp_path / "corrected.h5"
    table.to_hdf(source, key="custom_coordinates", format="table")
    with pd.HDFStore(source, "a") as store:
        store.root._v_attrs.project_notes = {"camera": "left", "fps": 120.0}
        store.get_storer("custom_coordinates").attrs.experiment_id = "animal-001"
        store.get_node("/custom_coordinates/table")._v_attrs.tracking_metadata = "confidence retained"
    loaded, key = read_dlc_h5(source)
    corrected = loaded.copy()
    corrected[("DLC_custom", "knee", "x")] += 2
    write_dlc_h5(corrected, output, key, source_path=source)
    restored, restored_key = read_dlc_h5(output)
    pd.testing.assert_frame_equal(restored, corrected)
    assert restored_key == key == "/custom_coordinates"
    with pd.HDFStore(output, "r") as store:
        assert store.root._v_attrs.project_notes == {"camera": "left", "fps": 120.0}
        assert store.get_storer("custom_coordinates").attrs.experiment_id == "animal-001"
        assert store.get_node("/custom_coordinates/table")._v_attrs.tracking_metadata == "confidence retained"
