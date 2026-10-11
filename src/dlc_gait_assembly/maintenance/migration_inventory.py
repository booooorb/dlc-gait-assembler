"""Inventory existing outputs and verify their byte-level integrity without modifying them."""

import hashlib
import os
from pathlib import Path

from dlc_gait_assembly.maintenance.migration_contracts import InventoryEntry


def file_digest(path):
    path = Path(path)
    digest = hashlib.sha256()
    if path.is_symlink():
        digest.update(os.readlink(path).encode("utf-8"))
    else:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def inventory_outputs(source_root):
    root = Path(source_root).resolve()
    output = root / "outputs"
    if not output.is_dir():
        return ()
    entries = []
    for directory, folders, filenames in os.walk(output, followlinks=False):
        folders.sort()
        paths = [Path(directory) / name for name in sorted(filenames)]
        links = [name for name in folders if (Path(directory) / name).is_symlink()]
        paths.extend(Path(directory) / name for name in links)
        folders[:] = [name for name in folders if name not in links]
        for path in paths:
            relative = path.relative_to(root).as_posix()
            entries.append(
                InventoryEntry(
                    str(path),
                    relative,
                    path.lstat().st_size,
                    file_digest(path),
                    "symlink" if path.is_symlink() else "file",
                )
            )
    return tuple(sorted(entries, key=lambda item: item.relative))


def verify_file(path, expected_hash):
    path = Path(path)
    if not path.exists() and (not path.is_symlink()):
        raise FileNotFoundError(path)
    if file_digest(path) != expected_hash:
        raise RuntimeError(f"File changed since inventory: {path}")
