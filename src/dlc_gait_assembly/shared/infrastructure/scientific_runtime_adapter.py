"""Validate explicitly selected scientific interpreters against the installed application package."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def find_alma_python() -> Path | None:
    """Use this environment by default; opt in to an installed external runtime."""
    if os.environ.get("DLC_GAIT_ALMA_PIPELINE_CHILD") == "1" or environment_flag(
        "DLC_GAIT_DISABLE_ALMA_EXTERNAL_RUNTIME"
    ):
        return None
    configured = os.environ.get("DLC_GAIT_ALMA_PYTHON")
    if not configured:
        return None
    candidate = Path(configured).expanduser().absolute()
    if candidate == Path(sys.executable).absolute():
        return None
    if not candidate.is_file() or not has_alma_runtime_dependencies(candidate):
        raise RuntimeError(
            f"The configured scientific Python must contain this application and its scientific dependencies: {candidate}"
        )
    return candidate


def has_alma_runtime_dependencies(python_executable: Path) -> bool:
    """Check the scientific stack and require the same installed distribution version."""
    try:
        expected_version = version("dlc-gait-assembler")
    except PackageNotFoundError:
        expected_version = "0.1.0"
    probe = f'import pandas, scipy, sklearn, matplotlib, numpy; import dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_engine; from importlib.metadata import version; assert version("dlc-gait-assembler") == {expected_version!r}'
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    try:
        result = subprocess.run(
            [str(python_executable), "-c", probe],
            env=environment,
            cwd=tempfile.gettempdir(),
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def temporary_directory_root() -> Path:
    """Return the platform's writable temporary directory."""
    return Path(tempfile.gettempdir())


def environment_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "on"}
