from dlc_gait_assembly.app.app_bootstrap import (
    build_tool_specs,
)


(TOOL_SPECS, LADDER_TOOL_SPEC) = build_tool_specs()


import os


import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


pytest.importorskip("PySide6")


from PySide6.QtCore import QAbstractAnimation, QRectF, Qt


from PySide6.QtGui import QCursor


from PySide6.QtTest import QTest


from PySide6.QtWidgets import (
    QApplication,
)


from dlc_gait_assembly.runway.manual.calibration.client.calibration_stick_item import CalibrationStickItem


from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationPoint


from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import CalibrationStick


def _wait_for_animation(animation, timeout_ms: int = 1500) -> None:
    elapsed = 0
    while animation.state() == QAbstractAnimation.State.Running and elapsed < timeout_ms:
        QTest.qWait(20)
        elapsed += 20
    assert animation.state() == QAbstractAnimation.State.Stopped


def test_calibration_hover_uses_concrete_qcursors():
    app = QApplication.instance() or QApplication([])
    stick = CalibrationStick("x", 1, CalibrationPoint(0, 0), CalibrationPoint(100, 0))
    item = CalibrationStickItem(stick, QRectF(0, 0, 100, 100), lambda _stick: None)
    expected_shapes = {
        "start": Qt.CrossCursor,
        "end": Qt.CrossCursor,
        "move": Qt.SizeAllCursor,
        0: Qt.PointingHandCursor,
        "none": Qt.ArrowCursor,
    }
    for hit, expected_shape in expected_shapes.items():
        cursor = item._cursor_for_hit(hit)
        assert isinstance(cursor, QCursor)
        assert cursor.shape() == expected_shape
