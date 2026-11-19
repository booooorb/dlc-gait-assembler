"""Use the Win32 extended namespace for filesystem operations on resolved paths."""

from pathlib import PurePath, PureWindowsPath
from typing import TypeVar

_PathT = TypeVar("_PathT", bound=PurePath)


def windows_filesystem_path(path: _PathT) -> _PathT:
    if not isinstance(path, PureWindowsPath) or not path.is_absolute():
        return path
    value = str(path)
    if value.startswith(("\\\\?\\", "\\\\.\\")):
        return path
    if value.startswith("\\\\"):
        return type(path)("\\\\?\\UNC\\" + value[2:])
    return type(path)("\\\\?\\" + value)
