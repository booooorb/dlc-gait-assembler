"""Read and write DeepLabCut HDF coordinates while preserving keys and custom metadata."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from dlc_gait_assembly.shared.business.coordinate_table_contracts import (
    validate_dlc_dataframe as _validate_dlc_dataframe,
)


def read_dlc_h5(path: str | Path) -> tuple[pd.DataFrame, str]:
    h5_path = Path(path).expanduser().resolve()
    try:
        with pd.HDFStore(h5_path, mode="r") as store:
            keys = store.keys()
            if len(keys) != 1:
                raise ValueError("The H5 file must contain exactly one coordinate dataset.")
            key = keys[0]
            dataframe = store[key]
    except Exception as exc:
        raise ValueError(f"Could not read DeepLabCut H5: {h5_path.name}") from exc
    _validate_dlc_dataframe(dataframe, h5_path)
    return (dataframe, key)


def write_dlc_h5(dataframe, path, key, *, source_path=None):
    """Preserve the coordinate key/columns and any source-specific HDF metadata."""
    source_attributes = {}
    if source_path is not None:
        with pd.HDFStore(source_path, mode="r") as source:
            for node_path in ("/", key, key.rstrip("/") + "/table"):
                try:
                    attributes = source.get_node(node_path)._v_attrs
                except (AttributeError, KeyError):
                    continue
                source_attributes[node_path] = {name: attributes[name] for name in attributes._f_list("user")}
    dataframe.to_hdf(path, key=key.lstrip("/"), mode="w", format="table")
    if source_attributes:
        with pd.HDFStore(path, mode="a") as target:
            for node_path, values in source_attributes.items():
                node = target.get_node(node_path)
                if node is None:
                    continue
                attributes = node._v_attrs
                generated = set(attributes._f_list("all"))
                for name, value in values.items():
                    if name not in generated:
                        attributes[name] = value
