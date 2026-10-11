"""Configured virtual environments keep their own interpreter identity."""

import sys

from dlc_gait_assembly.shared.infrastructure import scientific_runtime_adapter as runtime


def test_explicit_virtualenv_is_not_discarded_when_python_is_a_symlink(tmp_path, monkeypatch):
    selected = tmp_path / "venv/bin/python"
    selected.parent.mkdir(parents=True)
    selected.symlink_to(sys.executable)
    probes = []
    monkeypatch.delenv("DLC_GAIT_DISABLE_ALMA_EXTERNAL_RUNTIME", raising=False)
    monkeypatch.delenv("DLC_GAIT_ALMA_PIPELINE_CHILD", raising=False)
    monkeypatch.setenv("DLC_GAIT_ALMA_PYTHON", str(selected))
    monkeypatch.setattr(runtime, "has_alma_runtime_dependencies", lambda path: probes.append(path) or True)
    assert runtime.find_alma_python() == selected
    assert probes == [selected]


def test_default_runtime_does_not_probe_other_environments(monkeypatch):
    monkeypatch.delenv("DLC_GAIT_ALMA_PYTHON", raising=False)

    def unexpected(_):
        raise AssertionError("No interpreter was explicitly selected")

    monkeypatch.setattr(runtime, "has_alma_runtime_dependencies", unexpected)
    assert runtime.find_alma_python() is None
