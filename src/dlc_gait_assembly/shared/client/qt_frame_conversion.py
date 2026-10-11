"""Convert decoded image arrays into Qt images and pixmaps for presentation."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage


def rgb_array_to_qimage(frame: np.ndarray) -> QImage:
    """Copy an already-decoded RGB frame into a Qt-owned display image."""
    rgb = np.ascontiguousarray(frame, dtype=np.uint8)
    (height, width, _channels) = rgb.shape
    return QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()


def qimage_to_rgb_array(image: QImage):
    if np is None:
        return None
    converted = image.convertToFormat(QImage.Format_RGB888)
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    buffer = converted.constBits()
    array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, bytes_per_line))
    return array[:, : width * 3].reshape((height, width, 3)).copy()
