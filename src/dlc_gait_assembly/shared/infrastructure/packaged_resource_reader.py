"""Locate installed application assets without depending on a source checkout."""

from __future__ import annotations

import atexit
from contextlib import ExitStack
from functools import cache
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory

_resources = ExitStack()
atexit.register(_resources.close)


@cache
def resource_path(*parts: str) -> Path:
    """Return an asset path valid for the application lifetime, including zip installs."""
    if any(not part or part in {".", ".."} or "/" in part or ("\\" in part) for part in parts):
        raise ValueError("Resource names must be individual relative path components")
    resource = files("dlc_gait_assembly.resources").joinpath(*parts)
    if isinstance(resource, Path):
        return resource
    if resource.is_file():
        return _resources.enter_context(as_file(resource))
    if not resource.is_dir():
        raise FileNotFoundError("/".join(parts))
    directory = Path(_resources.enter_context(TemporaryDirectory(prefix="gait-resources-")))

    def copy_tree(source, destination):
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            target = destination / child.name
            if child.is_dir():
                copy_tree(child, target)
            else:
                target.write_bytes(child.read_bytes())

    copy_tree(resource, directory)
    return directory


def read_resource_text(*parts: str) -> str:
    """Read a UTF-8 packaged document."""
    return resource_path(*parts).read_text(encoding="utf-8")


def resource_exists(*parts: str) -> bool:
    """Check an optional packaged asset without exposing filesystem inspection to widgets."""
    return resource_path(*parts).is_file()
