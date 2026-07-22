from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QWidget

WHEEL_VALUE_WIDGETS = (QComboBox, QDoubleSpinBox, QSpinBox)


class WheelValueGuard(QObject):
    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(watched, WHEEL_VALUE_WIDGETS):
            event.ignore()
            return True
        return super().eventFilter(watched, event)


def install_wheel_value_guard(root: QWidget) -> WheelValueGuard:
    guard = WheelValueGuard(root)
    for widget_type in WHEEL_VALUE_WIDGETS:
        for widget in root.findChildren(widget_type):
            widget.installEventFilter(guard)
    return guard


def set_tooltip(widget: QWidget, text: str, shortcut: str | None = None) -> None:
    widget.setToolTip(f"{text}\nShortcut: {shortcut}" if shortcut else text)


def add_shortcut(parent: QWidget, sequence: str, callback: Callable[[], None]) -> QShortcut:
    shortcut = QShortcut(QKeySequence(sequence), parent)
    shortcut.activated.connect(callback)
    return shortcut
