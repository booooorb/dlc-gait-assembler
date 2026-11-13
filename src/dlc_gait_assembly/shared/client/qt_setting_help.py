"""Expose setting descriptions on controls and their associated info labels."""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
)

SETTING_CONTROLS = (QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QSlider, QSpinBox)
INFO_SUFFIX = "  ⓘ"


def _label_for_control(layout, control):
    """Find a label within the control's own row, including nested layouts."""
    if layout is None:
        return None
    index = layout.indexOf(control)
    if index >= 0:
        if isinstance(layout, QFormLayout):
            return layout.labelForField(control)
        if isinstance(layout, QGridLayout):
            row, column, _, _ = layout.getItemPosition(index)
            # Only the immediately preceding cell belongs to this setting.
            item = layout.itemAtPosition(row, column - 1) if column else None
            return item.widget() if item and isinstance(item.widget(), QLabel) else None
        if isinstance(layout, QHBoxLayout):
            item = layout.itemAt(index - 1) if index else None
            return item.widget() if item and isinstance(item.widget(), QLabel) else None
        return None
    for index in range(layout.count()):
        child = layout.itemAt(index).layout()
        if child is not None:
            label = _label_for_control(child, control)
            if label is not None:
                return label
    return None


class SettingHelp(QObject):
    """Refresh label help after layout construction and when descriptions change."""

    def refresh(self, control):
        text = control.toolTip()
        if not text:
            return
        control.setAccessibleDescription(text)
        if isinstance(control, QCheckBox):
            # Keep action text stable for shortcuts, accessibility and callers.
            return
        parent = control.parentWidget()
        label = _label_for_control(parent.layout(), control) if parent is not None else None
        if label is not None:
            if not label.text().endswith(INFO_SUFFIX):
                label.setText(label.text() + INFO_SUFFIX)
            label.setToolTip(text)
            label.setAccessibleDescription(text)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.ToolTipChange):
            self.refresh(watched)
        return False


def attach_setting_help(control):
    """Register once; Show handles controls configured before entering a layout."""
    if not isinstance(control, SETTING_CONTROLS):
        return
    if not hasattr(control, "_setting_help"):
        control._setting_help = SettingHelp(control)
        control.installEventFilter(control._setting_help)
    control._setting_help.refresh(control)
