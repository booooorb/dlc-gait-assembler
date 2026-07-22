from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractButton, QComboBox, QDoubleSpinBox, QSpinBox, QWidget

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


def animate_button_emphasis(
    button: QAbstractButton,
    emphasized: bool,
    *,
    resting_height: int = 32,
    emphasized_height: int = 42,
) -> None:
    """Briefly resize a processing action without leaving a repaint loop running."""
    existing = getattr(button, "_emphasis_animation", None)
    if existing is not None:
        existing.stop()
    target = emphasized_height if emphasized else resting_height
    start = button.minimumHeight()
    if start <= 0:
        start = max(resting_height, button.sizeHint().height())
        button.setMinimumHeight(start)
    if start == target:
        return
    animation = existing or QPropertyAnimation(button, b"minimumHeight", button)
    animation.setDuration(180)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.setStartValue(start)
    animation.setEndValue(target)
    button._emphasis_animation = animation
    animation.start()
