"""Runtime discovery shared by ALMA-based pipeline adapters."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def find_alma_python() -> Path | None:
    """Return a compatible external Python interpreter when one is available."""

    if os.environ.get("DLC_GAIT_ALMA_PIPELINE_CHILD") == "1":
        return None
    if _environment_flag("DLC_GAIT_DISABLE_ALMA_EXTERNAL_RUNTIME"):
        return None

    candidates: list[Path] = []
    configured = os.environ.get("DLC_GAIT_ALMA_PYTHON")
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(alma_python_candidates())

    current = Path(sys.executable).resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved == current or not resolved.exists():
            continue
        if has_alma_runtime_dependencies(resolved):
            return resolved
    return None


def alma_python_candidates() -> tuple[Path, ...]:
    """Return configured and conventional ALMA-compatible interpreter paths."""

    candidates: list[Path] = []
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        envs_root = Path(conda_prefix).resolve().parent
        candidates.extend(
            [
                envs_root / "venv_python_3_10" / "bin" / "python",
                envs_root / "ALMA" / "bin" / "python",
                envs_root / "DEEPLABCUT" / "bin" / "python",
            ]
        )
    candidates.extend(
        [
            Path("/opt/miniconda3/envs/venv_python_3_10/bin/python"),
            Path("/opt/miniconda3/envs/ALMA/bin/python"),
            Path("/opt/miniconda3/envs/DEEPLABCUT/bin/python"),
        ]
    )
    return tuple(candidates)


def has_alma_runtime_dependencies(python_executable: Path) -> bool:
    """Probe an interpreter for the scientific packages required by ALMA."""

    probe = "import pandas, scipy, sklearn, matplotlib, numpy"
    try:
        completed = subprocess.run(
            [str(python_executable), "-c", probe],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def temporary_directory_root() -> Path:
    """Return a writable root suitable for child-process request files."""

    for candidate in (Path("/private/tmp"), Path(tempfile.gettempdir())):
        if candidate.exists() and os.access(candidate, os.W_OK):
            return candidate
    return Path(tempfile.gettempdir())


def _environment_flag(name: str) -> bool:
    value = os.environ.get(name, "")
    return value.strip().casefold() in {"1", "true", "yes", "on"}


__all__ = [
    "alma_python_candidates",
    "find_alma_python",
    "has_alma_runtime_dependencies",
    "temporary_directory_root",
]
