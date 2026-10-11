"""Contracts for paired coordinates, settings persistence, and correction outputs."""

from pathlib import Path
from typing import Protocol


class KneeCoordinateRepositoryPort(Protocol):
    def load_preview(self, pair): ...

    def load(self, pair) -> tuple: ...


class KneeResultWriterPort(Protocol):
    def write(self, pair, destination: Path, corrected, h5_key: str, reports): ...


class KneeSettingsStorePort(Protocol):
    def read(self, path: Path): ...

    def write(self, path: Path, settings): ...
