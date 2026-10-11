from __future__ import annotations
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def alma_fixtures_dir() -> Path:
    return FIXTURES / "alma"


@pytest.fixture(scope="session")
def video_fixtures_dir() -> Path:
    return FIXTURES / "video"


@pytest.fixture(autouse=True)
def isolated_application_workspace(tmp_path, monkeypatch):
    """GUI and adapter tests never create profiles or outputs in the user's workspace."""
    monkeypatch.setenv("DLC_GAIT_WORKSPACE", str(tmp_path / "workspace"))
