"""Enforce workflow ownership and dependency direction in the shipped package."""

from __future__ import annotations

import ast
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
SOURCE_ROOT = ROOT / "src/dlc_gait_assembly"


def sources():
    return sorted(SOURCE_ROOT.rglob("*.py"))


def imports(path):
    owner = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name, None
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = ".".join([*owner.split(".")[: -node.level], *module.split(".")])
            for alias in node.names:
                yield node.lineno, module, alias.name


def test_modules_have_unique_names_and_ownership_docstrings():
    owners = defaultdict(list)
    for path in sources():
        if path.name in {"__init__.py", "__main__.py"}:
            continue
        owners[path.name].append(path.relative_to(SOURCE_ROOT).as_posix())
        tree = ast.parse(path.read_text())
        assert ast.get_docstring(tree), path
        assert any(not isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)) for node in tree.body), path
    assert {name: paths for name, paths in owners.items() if len(paths) > 1} == {}
    assert not any(name in owners for name in ("utils.py", "helpers.py", "services.py"))


def test_business_has_no_qt_io_or_concrete_adapters():
    violations = []
    forbidden = ("PySide6", "cv2", "matplotlib", "subprocess", "shutil", "tempfile", "os", "io")
    filesystem_calls = {
        "open",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "mkdir",
        "unlink",
        "rmdir",
        "glob",
        "rglob",
        "iterdir",
        "is_file",
        "is_dir",
        "stat",
        "resolve",
        "expanduser",
    }
    for path in sources():
        if "business" not in path.parts:
            continue
        for line, module, _ in imports(path):
            if module.split(".")[0] in forbidden or ".client" in module or ".infrastructure" in module:
                violations.append(f"{path.relative_to(SOURCE_ROOT)}:{line} imports {module}")
        tree = ast.parse(path.read_text())
        # Filesystem methods are forbidden on paths; business calls to injected
        # repositories (such as outputs.is_file) are explicitly permitted.
        path_names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id in {"path", "root", "folder", "directory", "source", "destination", "input_path", "output_path"}
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                violations.append(f"{path}:{node.lineno} opens a file")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in filesystem_calls
            ):
                if isinstance(node.func.value, ast.Name) and node.func.value.id in path_names:
                    violations.append(f"{path}:{node.lineno} performs {node.func.attr}")
    assert violations == []


def test_shared_and_infrastructure_dependency_direction():
    violations = []
    for path in sources():
        for line, module, _ in imports(path):
            if (
                "shared" in path.parts
                and module.startswith("dlc_gait_assembly.")
                and not module.startswith("dlc_gait_assembly.shared.")
            ):
                violations.append(f"{path}:{line} shared imports {module}")
            if "infrastructure" in path.parts and ".client" in module:
                violations.append(f"{path}:{line} infrastructure imports {module}")
    assert violations == []


def test_features_do_not_import_other_feature_clients():
    violations = []
    automatic_assembly = SOURCE_ROOT / "runway/automatic/client"
    for path in sources():
        if "client" not in path.parts:
            continue
        owner = ".".join(path.relative_to(ROOT / "src").with_suffix("").parts).split(".client.")[0]
        for line, module, _ in imports(path):
            if not module.startswith("dlc_gait_assembly.") or ".client." not in module:
                continue
            target = module.split(".client.")[0]
            if target == owner or target.startswith("dlc_gait_assembly.shared"):
                continue
            # The automatic workspace assembles its own three child surfaces;
            # neutral parent display constants may be used by those surfaces.
            if path.parent == automatic_assembly and target.startswith(owner + "."):
                continue
            if module == "dlc_gait_assembly.runway.automatic.client.automatic_display_constants":
                continue
            violations.append(f"{path}:{line} imports {module}")
    assert violations == []


def test_clients_use_injected_feature_io():
    violations = []
    for path in sources():
        if "client" not in path.parts:
            continue
        for line, module, _ in imports(path):
            if ".infrastructure." in module and module not in {
                "dlc_gait_assembly.shared.infrastructure.packaged_resource_reader",
                "dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer",
            }:
                violations.append(f"{path}:{line} imports {module}")
    assert violations == []


def test_no_obsolete_packages_or_reference_loaders():
    assert not (SOURCE_ROOT / "gui").exists()
    assert not (SOURCE_ROOT / "services").exists()
    for path in sources():
        text = path.read_text()
        assert "alma_root" not in text, path
        assert "spec_from_file_location" not in text, path
        for _, module, _ in imports(path):
            assert not module.startswith(
                ("dlc_gait_assembly.gui", "dlc_gait_assembly.services", "references", "imports.alma")
            ), path


def test_only_readme_markdown_is_in_the_repository_changeset():
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    markdown = {
        name for name in result.stdout.decode().split("\0") if name.lower().endswith(".md") and (ROOT / name).is_file()
    }
    assert markdown == {"README.md"}


def test_modules_do_not_import_private_names():
    violations = [
        f"{path}:{line} {module}.{name}"
        for path in sources()
        for line, module, name in imports(path)
        if name and name.startswith("_")
    ]
    assert violations == []
