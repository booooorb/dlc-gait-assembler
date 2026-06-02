from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dlc_gait_assembly.services.alma_pipeline import default_alma_root


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def alma_root(project_root: Path) -> Path:
    return default_alma_root(project_root)


@pytest.fixture(scope="session")
def alma_fixtures_dir() -> Path:
    return FIXTURES / "alma"


@pytest.fixture(scope="session")
def video_fixtures_dir() -> Path:
    return FIXTURES / "video"
