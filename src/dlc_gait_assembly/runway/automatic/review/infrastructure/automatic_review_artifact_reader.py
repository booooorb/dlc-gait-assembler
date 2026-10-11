"""Read review metadata, textual summaries, and packaged demonstration assets."""

from __future__ import annotations

import json
from pathlib import Path

from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path


class AutomaticReviewArtifactReader:
    def reference_stickplot(self) -> Path:
        return resource_path("analysis_previews", "alma", "stickplot.svg")

    def exists(self, path: Path) -> bool:
        return path.is_file()

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def processing_enhancements(self, path: Path) -> dict | None:
        try:
            data = json.loads(self.read_text(path))
            enhancements = data["operations"].get("enhancements", {})
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            return None
        return enhancements if isinstance(enhancements, dict) else None

    def image_bytes(self, path):
        from dlc_gait_assembly.shared.infrastructure.svg_preview_sanitizer import qt_safe_svg_bytes

        data = Path(path).read_bytes()
        return qt_safe_svg_bytes(data) if Path(path).suffix.lower() == ".svg" else data
