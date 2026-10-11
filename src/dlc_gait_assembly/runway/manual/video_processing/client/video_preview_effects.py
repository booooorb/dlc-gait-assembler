"""Apply display-only enhancement effects to already-decoded preview frames."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtGui import QImage

from dlc_gait_assembly.shared.client.qt_frame_conversion import qimage_to_rgb_array


class VideoPreviewEffects:
    """VideoPreviewEffects operates on its explicitly supplied RegionPreviewView view."""

    def __init__(self, view):
        self.view = view

    def _apply_enhancements(self, image: QImage) -> QImage:
        if not self.view._enhancements.is_enabled() or np is None:
            return image
        array = qimage_to_rgb_array(image)
        if array is None:
            return image
        settings = self.view._enhancements
        frame = array.astype("float32") / 255.0
        frame *= 2.0**settings.exposure
        frame += settings.black_level
        input_black = min(settings.input_black, settings.input_white - 0.01)
        input_white = max(settings.input_white, input_black + 0.01)
        frame = (frame - input_black) / (input_white - input_black)
        output_black = min(settings.output_black, settings.output_white - 0.01)
        output_white = max(settings.output_white, output_black + 0.01)
        frame = output_black + frame * (output_white - output_black)
        frame += settings.brightness
        frame = (frame - 0.5) * settings.contrast + 0.5
        if abs(settings.tone_scale - 1.0) > 0.001:
            gamma = 1.0 / max(0.05, settings.tone_scale)
            frame = np.power(np.clip(frame, 0.0, 1.0), gamma)
        frame = np.clip(frame, 0.0, 1.0)
        if cv2 is not None and settings.sharpening > 0.001:
            blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
            frame = np.clip(frame + (frame - blurred) * settings.sharpening, 0.0, 1.0)
        if cv2 is not None and settings.cas > 0.001:
            blurred = cv2.GaussianBlur(frame, (0, 0), 0.65)
            detail = frame - blurred
            adaptive_weight = 1.0 - np.abs(frame * 2.0 - 1.0)
            frame = np.clip(frame + detail * adaptive_weight * settings.cas * 1.8, 0.0, 1.0)
        output = np.ascontiguousarray((frame * 255.0).round().astype("uint8"))
        (height, width, _channels) = output.shape
        return QImage(output.data, width, height, width * 3, QImage.Format_RGB888).copy()
