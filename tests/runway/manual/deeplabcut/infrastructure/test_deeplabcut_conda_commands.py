from __future__ import annotations

import shlex
from types import SimpleNamespace

import pytest

from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure import deeplabcut_environment_adapter
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
    deeplabcut_analysis_command,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
    deeplabcut_environment_file,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
    deeplabcut_install_command,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import (
    deeplabcut_launch_command,
)
from dlc_gait_assembly.runway.manual.deeplabcut.infrastructure.deeplabcut_conda_commands import deeplabcut_probe_command
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path


def test_deeplabcut_environment_recipe_is_packaged(tmp_path):
    path = deeplabcut_environment_file(tmp_path)
    assert path == resource_path("environments", "DEEPLABCUT.yaml")
    assert path.is_file()


def test_deeplabcut_install_command_accepts_explicit_recipe(tmp_path):
    environment_file = tmp_path / "imports" / "DEEPLABCUT.yaml"
    command = deeplabcut_install_command(environment_file, platform="darwin")
    quoted_path = shlex.quote(str(environment_file.resolve()))
    assert f"conda env create -f {quoted_path}" in command
    assert f"conda env update -f {quoted_path}" in command


@pytest.mark.parametrize("quoted", [False, True])
def test_windows_terminal_cd_preserves_backslashes_and_spaces(tmp_path, monkeypatch, quoted):
    monkeypatch.setattr(deeplabcut_environment_adapter, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(
        deeplabcut_environment_adapter, "manual_pipeline_output_folders", lambda: SimpleNamespace(root=tmp_path)
    )
    name = r"Mouse data\Trials"
    target = tmp_path / name
    target.mkdir(parents=True)
    adapter = deeplabcut_environment_adapter.DeepLabCutEnvironmentAdapter()
    command = f'cd "{name}"' if quoted else f"cd {name}"
    assert adapter.change_directory(command, tmp_path) == target.resolve()


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
    assert f"python -u {shlex.quote(str(script.resolve()))} --run-request {shlex.quote(str(request.resolve()))}" in command
