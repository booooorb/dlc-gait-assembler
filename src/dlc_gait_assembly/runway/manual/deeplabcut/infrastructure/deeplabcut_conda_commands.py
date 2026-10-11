"""Construct quoted platform-specific Conda environment and DeepLabCut launch commands."""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path

DEEPLABCUT_ENV_NAME = "DEEPLABCUT"
DEEPLABCUT_ENVIRONMENT_FILE = "DEEPLABCUT.yaml"
POSIX_CONDA_PROFILE_CANDIDATES = (
    "$HOME/anaconda3/etc/profile.d/conda.sh",
    "$HOME/miniconda3/etc/profile.d/conda.sh",
    "/opt/anaconda3/etc/profile.d/conda.sh",
    "/opt/miniconda3/etc/profile.d/conda.sh",
)
WINDOWS_CONDA_BAT_CANDIDATES = (
    "%USERPROFILE%\\anaconda3\\condabin\\conda.bat",
    "%USERPROFILE%\\miniconda3\\condabin\\conda.bat",
    "%LOCALAPPDATA%\\anaconda3\\condabin\\conda.bat",
    "%LOCALAPPDATA%\\miniconda3\\condabin\\conda.bat",
    "C:\\ProgramData\\anaconda3\\condabin\\conda.bat",
    "C:\\ProgramData\\miniconda3\\condabin\\conda.bat",
)


def deeplabcut_environment_file(project_root: Path) -> Path:
    return resource_path("environments", "DEEPLABCUT.yaml")


def deeplabcut_probe_command(platform: str | None = None) -> str:
    return conda_command(
        f"run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -c {python_import_probe(platform)}", platform=platform
    )


def deeplabcut_launch_command(platform: str | None = None) -> str:
    return conda_command(f"run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -u -m deeplabcut", platform=platform)


def deeplabcut_analysis_command(script_path: Path, request_path: Path, platform: str | None = None) -> str:
    script_argument = quote_path(Path(script_path).expanduser().resolve(), platform=platform)
    request_argument = quote_path(Path(request_path).expanduser().resolve(), platform=platform)
    return conda_command(
        f"run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -u {script_argument} --run-request {request_argument}",
        platform=platform,
    )


def deeplabcut_install_command(environment_file: Path, platform: str | None = None) -> str:
    environment_file = Path(environment_file).expanduser().resolve()
    file_argument = quote_path(environment_file, platform=platform)
    create_args = f"env create -f {file_argument}"
    update_args = f"env update -f {file_argument}"
    return conda_create_or_update_command(create_args, update_args, platform=platform)


def deeplabcut_launch_display_command() -> str:
    return f"conda run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -u -m deeplabcut"


def deeplabcut_install_display_command(environment_file: Path) -> str:
    return f"conda env create -f {quote_path(Path(environment_file).expanduser().resolve())}"


def conda_command(conda_args: str, platform: str | None = None) -> str:
    if is_windows(platform):
        return " || ".join(windows_conda_attempts(conda_args))
    return f"{posix_conda_initialization_command()}; conda {conda_args}"


def conda_create_or_update_command(create_args: str, update_args: str, platform: str | None = None) -> str:
    if is_windows(platform):
        attempts = [
            f"conda {create_args} || conda {update_args}",
            *[
                f'if exist "{candidate}" (call "{candidate}" {create_args} || call "{candidate}" {update_args})'
                for candidate in WINDOWS_CONDA_BAT_CANDIDATES
            ],
        ]
        return " || ".join(attempts)
    return f"{posix_conda_initialization_command()}; conda {create_args} || conda {update_args}"


def windows_conda_attempts(conda_args: str) -> list[str]:
    return [
        f"conda {conda_args}",
        *[f'if exist "{candidate}" call "{candidate}" {conda_args}' for candidate in WINDOWS_CONDA_BAT_CANDIDATES],
    ]


def posix_conda_initialization_command() -> str:
    source_attempts = " || ".join(
        f'{{ [ -f "{candidate}" ] && . "{candidate}"; }}' for candidate in POSIX_CONDA_PROFILE_CANDIDATES
    )
    return f"command -v conda >/dev/null 2>&1 || {{ {source_attempts}; }}"


def python_import_probe(platform: str | None) -> str:
    if is_windows(platform):
        return '"import deeplabcut"'
    return shlex.quote("import deeplabcut")


def quote_path(path: Path, platform: str | None = None) -> str:
    if is_windows(platform):
        return f'"{path}"'
    return shlex.quote(str(path))


def is_windows(platform: str | None) -> bool:
    value = platform or sys.platform
    return value.startswith("win")
