"""Define resolved application workspace locations without accessing the filesystem."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManualPipelineOutputFolders:
    root: Path
    processed_videos: Path
    analyzed_videos: Path
    labeled_videos: Path
    knee_correction: Path
    gait_analysis: Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path

    @property
    def manual(self):
        return self.root / "runway" / "manual"

    @property
    def automatic_profiles(self):
        return self.root / "runway" / "automatic" / "profiles"

    @property
    def automatic_runs(self):
        return self.root / "runway" / "automatic" / "runs"

    @property
    def ladder_analyses(self):
        return self.root / "ladder" / "analyses"

    @property
    def ui_reviews(self):
        return self.root / "development" / "ui_reviews"

    @property
    def migrations(self):
        return self.root / "migrations"
