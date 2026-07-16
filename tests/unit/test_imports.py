from __future__ import annotations

from dlc_gait_assembly.services.imports import (
    deeplabcut_analysis_command,
    deeplabcut_environment_file,
    deeplabcut_install_command,
    deeplabcut_launch_command,
    deeplabcut_probe_command,
    default_alma_root,
)


def test_default_alma_root_prefers_imports_folder(tmp_path):
    imported_root = tmp_path / "imports" / "alma"
    imported_root.mkdir(parents=True)
    legacy_root = tmp_path / "alma-import"
    legacy_root.mkdir()

    assert default_alma_root(tmp_path) == imported_root


def test_default_alma_root_falls_back_to_legacy_import(tmp_path):
    legacy_root = tmp_path / "alma-import"
    legacy_root.mkdir()

    assert default_alma_root(tmp_path) == legacy_root


def test_default_alma_root_falls_back_to_upstream_checkout(tmp_path):
    assert default_alma_root(tmp_path) == tmp_path / "DLC-Gait-Analysis-main" / "alma-master"


def test_deeplabcut_environment_file_lives_under_imports(tmp_path):
    assert deeplabcut_environment_file(tmp_path) == tmp_path / "imports" / "DEEPLABCUT.yaml"


def test_deeplabcut_install_command_uses_imported_yaml(tmp_path):
    environment_file = tmp_path / "imports" / "DEEPLABCUT.yaml"

    command = deeplabcut_install_command(environment_file, platform="darwin")

    assert f"conda env create -f {environment_file}" in command
    assert f"conda env update -f {environment_file}" in command


def test_deeplabcut_probe_and_launch_commands_use_named_conda_env():
    assert "conda run -n DEEPLABCUT" in deeplabcut_probe_command(platform="darwin")
    assert "python -c 'import deeplabcut'" in deeplabcut_probe_command(platform="darwin")
    assert "conda run -n DEEPLABCUT" in deeplabcut_launch_command(platform="darwin")
    assert "python -u -m deeplabcut" in deeplabcut_launch_command(platform="darwin")


def test_deeplabcut_analysis_command_runs_request_in_named_environment(tmp_path):
    script = tmp_path / "pipeline bridge.py"
    request = tmp_path / "request file.json"

    command = deeplabcut_analysis_command(script, request, platform="darwin")

    assert "conda run -n DEEPLABCUT" in command
    assert f"python -u '{script}' --run-request '{request}'" in command
