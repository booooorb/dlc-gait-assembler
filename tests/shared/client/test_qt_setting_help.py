"""Verify setting help survives lazy layouts, hidden tabs, and dynamic descriptions."""

import pytest
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGridLayout,
    QHBoxLayout, QLabel, QSpinBox, QWidget,
)

from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip
from dlc_gait_assembly.shared.client.qt_setting_help import INFO_SUFFIX


@pytest.fixture(scope="module")
def application():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("layout_type", [QGridLayout, QFormLayout, QHBoxLayout])
def test_help_reaches_label_after_layout_construction(application, layout_type):
    root = QWidget()
    layout = layout_type(root)
    control = QSpinBox()
    # Settings are usually described before they have a parent or layout.
    set_tooltip(control, "Minimum accepted number of stance frames.")
    label = QLabel("Stance frames")
    if layout_type is QGridLayout:
        layout.addWidget(label, 0, 0)
        layout.addWidget(control, 0, 1)
    elif layout_type is QFormLayout:
        layout.addRow(label, control)
    else:
        layout.addWidget(label)
        layout.addWidget(control)
    root.show()
    application.processEvents()
    assert label.text() == "Stance frames" + INFO_SUFFIX
    assert label.toolTip() == control.toolTip()
    assert control.accessibleDescription() == control.toolTip()
    # Updating a detector changes its description without duplicating its icon.
    set_tooltip(control, "Updated detector description.")
    assert label.toolTip() == "Updated detector description."
    root.hide()
    root.show()
    application.processEvents()
    assert label.text().count(INFO_SUFFIX) == 1
    root.close()


def test_grid_help_does_not_replace_neighbouring_setting_help(application):
    root = QWidget()
    layout = QGridLayout(root)
    for column, description in ((0, "First setting."), (2, "Second setting.")):
        label, control = QLabel("Setting"), QComboBox()
        layout.addWidget(label, 0, column)
        layout.addWidget(control, 0, column + 1)
        set_tooltip(control, description)
        assert label.toolTip() == description
    assert layout.itemAtPosition(0, 0).widget().toolTip() == "First setting."
    root.close()


def test_checkbox_preserves_action_text_and_exposes_description(application):
    control = QCheckBox("Include gait analysis")
    set_tooltip(control, "Run gait analysis after tracking.")
    assert control.text() == "Include gait analysis"
    assert control.accessibleDescription() == "Run gait analysis after tracking."
    control.close()
