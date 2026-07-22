from __future__ import annotations

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src" / "dlc_gait_assembly"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, None
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                yield node.lineno, node.module, alias.name


def test_services_do_not_import_gui():
    violations = []
    for path in (SOURCE_ROOT / "services").rglob("*.py"):
        for line, module, _name in _imports(path):
            if module == "dlc_gait_assembly.gui" or module.startswith("dlc_gait_assembly.gui."):
                violations.append(f"{path.relative_to(SOURCE_ROOT)}:{line} imports {module}")
    assert violations == []


def test_domain_stays_dependency_free():
    forbidden = (
        "PySide6",
        "pathlib",
        "subprocess",
        "dlc_gait_assembly.gui",
        "dlc_gait_assembly.services.pipeline",
    )
    violations = []
    for path in (SOURCE_ROOT / "services" / "domain").rglob("*.py"):
        for line, module, _name in _imports(path):
            if any(module == prefix or module.startswith(f"{prefix}.") for prefix in forbidden):
                violations.append(f"{path.relative_to(SOURCE_ROOT)}:{line} imports {module}")
    assert violations == []


def test_modules_do_not_import_private_names_from_other_modules():
    violations = []
    for path in SOURCE_ROOT.rglob("*.py"):
        for line, module, name in _imports(path):
            if name is not None and name.startswith("_"):
                violations.append(
                    f"{path.relative_to(SOURCE_ROOT)}:{line} imports private name {module}.{name}"
                )
    assert violations == []
