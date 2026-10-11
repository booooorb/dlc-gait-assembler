"""Track preview generations and reject results invalidated by input or settings changes."""

from dataclasses import dataclass


@dataclass
class GaitPreviewValidity:
    revision: int = 0
    request_revision: int | None = None
    accepted_revision: int | None = None

    @property
    def ready(self):
        return self.accepted_revision is not None and self.accepted_revision == self.revision

    @property
    def stale(self):
        return self.request_revision is not None and self.request_revision != self.revision

    def invalidate(self):
        self.revision += 1
        self.accepted_revision = None

    def begin(self):
        self.accepted_revision = None
        self.request_revision = self.revision

    def complete(self):
        if self.stale:
            return False
        self.accepted_revision = self.revision
        return True

    def fail(self):
        self.accepted_revision = None
