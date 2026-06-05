from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnhancementSettings:
    sharpening: float = 0.0
    cas: float = 0.0
    brightness: float = 0.0
    contrast: float = 1.0
    exposure: float = 0.0
    black_level: float = 0.0
    tone_scale: float = 1.0
    input_black: float = 0.0
    input_white: float = 1.0
    output_black: float = 0.0
    output_white: float = 1.0

    def is_enabled(self) -> bool:
        return any(
            (
                abs(self.sharpening) > 0.001,
                abs(self.cas) > 0.001,
                abs(self.brightness) > 0.001,
                abs(self.contrast - 1.0) > 0.001,
                abs(self.exposure) > 0.001,
                abs(self.black_level) > 0.001,
                abs(self.tone_scale - 1.0) > 0.001,
                abs(self.input_black) > 0.001,
                abs(self.input_white - 1.0) > 0.001,
                abs(self.output_black) > 0.001,
                abs(self.output_white - 1.0) > 0.001,
            )
        )
