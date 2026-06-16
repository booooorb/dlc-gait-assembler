from __future__ import annotations

import shlex
import sys
from pathlib import Path


DEEPLABCUT_ENV_NAME = "DEEPLABCUT"
DEEPLABCUT_ENVIRONMENT_FILE = "DEEPLABCUT.yaml"
IMPORTS_DIR_NAME = "imports"
ALMA_IMPORT_DIR_NAME = "alma"
LEGACY_ALMA_IMPORT_DIR_NAME = "alma-import"

_POSIX_CONDA_PROFILE_CANDIDATES = (
    "$HOME/anaconda3/etc/profile.d/conda.sh",
    "$HOME/miniconda3/etc/profile.d/conda.sh",
    "/opt/anaconda3/etc/profile.d/conda.sh",
    "/opt/miniconda3/etc/profile.d/conda.sh",
)

_WINDOWS_CONDA_BAT_CANDIDATES = (
    "%USERPROFILE%\\anaconda3\\condabin\\conda.bat",
    "%USERPROFILE%\\miniconda3\\condabin\\conda.bat",
    "%LOCALAPPDATA%\\anaconda3\\condabin\\conda.bat",
    "%LOCALAPPDATA%\\miniconda3\\condabin\\conda.bat",
    "C:\\ProgramData\\anaconda3\\condabin\\conda.bat",
    "C:\\ProgramData\\miniconda3\\condabin\\conda.bat",
)


def imports_root(project_root: Path) -> Path:
    return Path(project_root).expanduser().resolve() / IMPORTS_DIR_NAME


def deeplabcut_environment_file(project_root: Path) -> Path:
    return imports_root(project_root) / DEEPLABCUT_ENVIRONMENT_FILE


def default_alma_root(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    imported_root = root / IMPORTS_DIR_NAME / ALMA_IMPORT_DIR_NAME
    if imported_root.exists():
        return imported_root

    legacy_imported_root = root / LEGACY_ALMA_IMPORT_DIR_NAME
    if legacy_imported_root.exists():
        return legacy_imported_root

    return root / "DLC-Gait-Analysis-main" / "alma-master"


def deeplabcut_probe_command(platform: str | None = None) -> str:
    return _conda_command(
        f"run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -c {_python_import_probe(platform)}",
        platform=platform,
    )


def deeplabcut_launch_command(platform: str | None = None) -> str:
    return _conda_command(
        f"run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -u -m deeplabcut",
        platform=platform,
    )


def deeplabcut_install_command(environment_file: Path, platform: str | None = None) -> str:
    environment_file = Path(environment_file).expanduser().resolve()
    file_argument = _quote_path(environment_file, platform=platform)
    create_args = f"env create -f {file_argument}"
    update_args = f"env update -f {file_argument}"
    return _conda_create_or_update_command(create_args, update_args, platform=platform)


def deeplabcut_launch_display_command() -> str:
    return f"conda run -n {DEEPLABCUT_ENV_NAME} --no-capture-output python -u -m deeplabcut"


def deeplabcut_install_display_command(environment_file: Path) -> str:
    return f"conda env create -f {_quote_path(Path(environment_file).expanduser().resolve())}"


def _conda_command(conda_args: str, platform: str | None = None) -> str:
    if _is_windows(platform):
        return " || ".join(_windows_conda_attempts(conda_args))
    return f"{_posix_conda_initialization_command()}; conda {conda_args}"


def _conda_create_or_update_command(create_args: str, update_args: str, platform: str | None = None) -> str:
    if _is_windows(platform):
        attempts = [
            f"conda {create_args} || conda {update_args}",
            *[
                f'if exist "{candidate}" (call "{candidate}" {create_args} || call "{candidate}" {update_args})'
                for candidate in _WINDOWS_CONDA_BAT_CANDIDATES
            ],
        ]
        return " || ".join(attempts)

    return f"{_posix_conda_initialization_command()}; conda {create_args} || conda {update_args}"


def _windows_conda_attempts(conda_args: str) -> list[str]:
    return [
        f"conda {conda_args}",
        *[f'if exist "{candidate}" call "{candidate}" {conda_args}' for candidate in _WINDOWS_CONDA_BAT_CANDIDATES],
    ]


def _posix_conda_initialization_command() -> str:
    source_attempts = " || ".join(
        f'[ -f "{candidate}" ] && . "{candidate}"' for candidate in _POSIX_CONDA_PROFILE_CANDIDATES
    )
    return f"command -v conda >/dev/null 2>&1 || {source_attempts}"


def _python_import_probe(platform: str | None) -> str:
    if _is_windows(platform):
        return '"import deeplabcut"'
    return shlex.quote("import deeplabcut")


def _quote_path(path: Path, platform: str | None = None) -> str:
    if _is_windows(platform):
        return f'"{path}"'
    return shlex.quote(str(path))


def _is_windows(platform: str | None) -> bool:
    value = platform or sys.platform
    return value.startswith("win")
