"""Load maintained scientific defaults from installed package resources."""

from __future__ import annotations

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import read_resource_text


def load_alma_config_defaults() -> dict:
    import yaml

    return yaml.load(read_resource_text("defaults", "alma.yaml"), Loader=yaml.FullLoader) or {}
