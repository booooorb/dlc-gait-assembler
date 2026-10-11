"""Immutable inventory, move plans, collisions, and migration journal records."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class InventoryEntry:
    source: str
    relative: str
    size: int
    sha256: str
    kind: str = "file"


@dataclass(frozen=True)
class PlannedMove:
    source: str
    destination: str
    size: int
    sha256: str
    kind: str = "file"


@dataclass(frozen=True)
class MigrationCollision:
    source_bundle: str
    requested_destination: str
    preserved_destination: str


@dataclass(frozen=True)
class MigrationPlan:
    source_root: str
    workspace_root: str
    moves: tuple[PlannedMove, ...]
    collisions: tuple[MigrationCollision, ...] = ()
    profile_id_remapping: dict[str, str] = field(default_factory=dict)
    version: int = 1

    def as_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if value.get("version") != 1:
            raise ValueError("Unsupported migration plan version.")
        return cls(
            source_root=value["source_root"],
            workspace_root=value["workspace_root"],
            moves=tuple(PlannedMove(**item) for item in value["moves"]),
            collisions=tuple(MigrationCollision(**item) for item in value.get("collisions", ())),
            profile_id_remapping=value.get("profile_id_remapping", {}),
        )
