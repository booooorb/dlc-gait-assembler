"""Calibrated paw contact states shared by bottom-view measurements."""

from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_calibration import view_scale

configured_axis_scale = view_scale


def stance_mask(series, marker, x_scale, y_scale, settings, np):
    axes = series.get(marker, {})
    x, y = axes.get("x"), axes.get("y")
    if x is None or y is None or not x_scale or not y_scale:
        return None
    dx = np.diff(x, prepend=np.nan) / float(x_scale)
    dy = np.diff(y, prepend=np.nan) / float(y_scale)
    speed = np.sqrt(dx**2 + dy**2) * float(settings.frame_rate)
    stance = np.isfinite(speed) & (speed <= float(settings.swing_speed_threshold_cm_s))
    if len(stance) > 1:
        stance[0] = stance[1]
    return stance
