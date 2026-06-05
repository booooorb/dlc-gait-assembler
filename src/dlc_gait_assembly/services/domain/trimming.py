from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrimRange:
    start_ms: int
    end_ms: int

    def clamped(self, duration_ms: int) -> "TrimRange":
        duration_ms = max(0, int(duration_ms))
        start = _clamp_int(self.start_ms, 0, duration_ms)
        end = _clamp_int(self.end_ms, start, duration_ms)
        return TrimRange(start, end)

    def is_usable(self) -> bool:
        return self.end_ms > self.start_ms

    def start_seconds(self) -> float:
        return self.start_ms / 1000.0

    def end_seconds(self) -> float:
        return self.end_ms / 1000.0


def _clamp_int(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))
