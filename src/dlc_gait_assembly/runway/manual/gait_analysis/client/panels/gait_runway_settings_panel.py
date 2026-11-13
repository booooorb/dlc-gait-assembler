"""Edit the updated ALMA runway detector, reconstruction and tracking-review settings."""

from PySide6.QtWidgets import QComboBox, QGridLayout, QGroupBox, QLabel

from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_analysis_settings_panel import double_spin
from dlc_gait_assembly.shared.client.qt_input_behaviors import set_tooltip

# Values are in seconds and fractions, matching configuration files and saved profiles.
RUNWAY_SPINS = {
    "runway_confidence_threshold": (
        "Tracking confidence min",
        0.01,
        0.99,
        2,
        "Mask unreliable coordinates before filtering; independent of treadmill and legacy detectors.",
    ),
    "runway_max_gap_s": (
        "Event gap max (s)",
        0.0,
        1.0,
        3,
        "Bridge only internal foot/body gaps within this time for events and foot trajectories. Zero disables bridging; longer gaps split valid segments.",
    ),
    "runway_min_body_speed": (
        "Body speed min (reference lengths/s)",
        0.0,
        20.0,
        3,
        "Minimum moving-bout speed relative to median toe-to-body separation, with an adaptive noise floor. Review for slow or impaired locomotion.",
    ),
    "runway_min_contact_s": (
        "Contact duration min (s)",
        0.001,
        1.0,
        3,
        "Suppress brief contact fluctuations; frame count follows each camera's FPS.",
    ),
    "runway_joint_max_gap_s": (
        "Joint gap max (s)",
        0.0,
        1.0,
        3,
        "Reconstruct only short internal joint gaps; never extrapolate at recording edges. Independent of event gaps.",
    ),
    "runway_joint_max_interpolated_fraction": (
        "Joint filled fraction max",
        0.0,
        1.0,
        3,
        "Maximum union of filled frames across each metric's required joints per cycle. Excess coverage leaves that metric unavailable.",
    ),
    "runway_joint_max_segment_change": (
        "Segment deviation max (fraction)",
        0.0,
        1.0,
        3,
        "Reject reconstructed geometry exceeding this relative change from local observed segment lengths.",
    ),
}


def build_gait_runway_settings(view, layout):
    box = QGroupBox("Confidence-aware runway settings")
    grid = QGridLayout(box)
    view.runway_settings_box = box
    view.runway_spins = {}
    for row, (name, (title, low, high, decimals, help_text)) in enumerate(RUNWAY_SPINS.items()):
        spin = double_spin(low, high, getattr(view._defaults, name), decimals)
        spin.setSingleStep(0.01)
        spin.setAccessibleName(title)
        set_tooltip(spin, help_text)
        view.runway_spins[name] = spin
        grid.addWidget(QLabel(title), row, 0)
        grid.addWidget(spin, row, 1)
    row = len(RUNWAY_SPINS)
    view.runway_joint_combo = QComboBox()
    for text, value in (("Observed only", "none"), ("Short-gap linear", "linear"), ("Short-gap PCHIP", "pchip")):
        view.runway_joint_combo.addItem(text, value)
    view.runway_joint_combo.setCurrentIndex(view.runway_joint_combo.findData(view._defaults.runway_joint_interpolation))
    set_tooltip(
        view.runway_joint_combo,
        "Optional reconstruction for joint angles and toe-to-crest distance. Geometry and motion checks reject unsupported estimates. Timing stays independent.",
    )
    grid.addWidget(QLabel("Joint reconstruction"), row, 0)
    grid.addWidget(view.runway_joint_combo, row, 1)
    view.runway_joint_cutoff_spin = double_spin(0.0, 50.0, view._defaults.runway_joint_filter_cutoff or 0.0, 1)
    view.runway_joint_cutoff_spin.setSpecialValueText("Inherit main cutoff")
    set_tooltip(
        view.runway_joint_cutoff_spin,
        "Zero inherits the main cutoff. A separate joint cutoff affects joint angles and toe-to-crest distance without changing events or foot trajectories. Must be below half the camera FPS.",
    )
    grid.addWidget(QLabel("Joint filter cutoff (Hz)"), row + 1, 0)
    grid.addWidget(view.runway_joint_cutoff_spin, row + 1, 1)
    view.runway_source_combo = QComboBox()
    view.runway_source_combo.addItem("Tracked (unfiltered)", "tracked")
    view.runway_source_combo.addItem("Analysis (filtered)", "analysis")
    view.runway_source_combo.setCurrentIndex(view.runway_source_combo.findData(view._defaults.runway_stickplot_source))
    set_tooltip(
        view.runway_source_combo,
        "Display only: tracked review preserves finite input points with dotted low-confidence bones; filtered analysis uses dashed reconstructed endpoints.",
    )
    grid.addWidget(QLabel("Stick-plot coordinates"), row + 2, 0)
    grid.addWidget(view.runway_source_combo, row + 2, 1)
    layout.addWidget(box)
