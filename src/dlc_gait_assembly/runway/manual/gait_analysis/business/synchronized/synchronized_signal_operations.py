"""Calculate finite-signal statistics, interpolation, and angular operations for synchronized features."""

from __future__ import annotations

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_analysis_settings import AlmaSettings


def view_calibration(settings: AlmaSettings, view: str) -> dict[str, object] | None:
    configured = (settings.view_calibration or {}).get(view)
    if isinstance(configured, (int, float)) and float(configured) > 0:
        value = float(configured)
        return {"x_pixels_per_cm": value, "y_pixels_per_cm": value, "source": f"{view} scalar"}
    if isinstance(configured, dict):
        scalar = configured.get("pixels_per_cm")
        x_value = configured.get("x_pixels_per_cm", scalar)
        y_value = configured.get("y_pixels_per_cm", scalar)
        if x_value and y_value and (float(x_value) > 0) and (float(y_value) > 0):
            return {
                "x_pixels_per_cm": float(x_value),
                "y_pixels_per_cm": float(y_value),
                "source": f"{view} axis-specific",
            }
    if settings.pixels_per_cm and float(settings.pixels_per_cm) > 0:
        value = float(settings.pixels_per_cm)
        return {"x_pixels_per_cm": value, "y_pixels_per_cm": value, "source": "manual scalar"}
    return None


def side_calibration_source(settings: AlmaSettings, view: str) -> str:
    configured = (settings.view_calibration or {}).get(view)
    if configured:
        return f"{view} view-specific calibration: {configured}"
    if settings.calibration_method == "reference":
        return f"ALMA anatomical reference: {settings.reference_segment}={settings.reference_length_cm:g} cm"
    if settings.pixels_per_cm:
        return f"manual scalar: {float(settings.pixels_per_cm):g} px/cm"
    return "unresolved"


def interpolate_short_gaps(values, maximum_gap: int, pd):
    values = values.copy()
    missing = values.isna().to_numpy()
    candidate = values.interpolate(method="linear", limit_area="inside")
    for start, end in true_runs(missing):
        if end - start > int(maximum_gap):
            candidate.iloc[start:end] = float("nan")
    return candidate


def filter_with_gaps(values, frame_rate, cutoff, kinematics, pd, np):
    output = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.notna().to_numpy()
    for start, end in true_runs(valid):
        segment = values.iloc[start:end].to_numpy(dtype=float)
        if len(segment) < 4:
            output.iloc[start:end] = segment
            continue
        try:
            output.iloc[start:end] = kinematics.butterworth_filter(segment, frame_rate, cutoff)
        except (ValueError, TypeError):
            output.iloc[start:end] = segment
    return output


def debounce_boolean(values, minimum_run: int, np):
    values = np.asarray(values, dtype=bool).copy()
    for start, end in true_runs(values):
        if end - start < minimum_run:
            values[start:end] = False
    inverse = ~values
    for start, end in true_runs(inverse):
        if 0 < start and end < len(values) and (end - start < minimum_run):
            values[start:end] = True
    return values


def true_runs(values):
    start = None
    for index, value in enumerate(values):
        if bool(value) and start is None:
            start = index
        elif not bool(value) and start is not None:
            yield (start, index)
            start = None
    if start is not None:
        yield (start, len(values))


def onsets(stance, np):
    if len(stance) == 0:
        return np.asarray([], dtype=int)
    transitions = np.flatnonzero(stance & ~np.r_[False, stance[:-1]])
    return transitions.astype(int)


def stance_end(stance, start, maximum):
    if start is None:
        return None
    end = int(start)
    while end < maximum and stance[end + 1]:
        end += 1
    return end


def safe_mean(values, np):
    array = np.asarray(values, dtype=float)
    return float(np.nanmean(array)) if np.isfinite(array).any() else np.nan


def safe_variance(values, np):
    array = np.asarray(values, dtype=float)
    return float(np.nanvar(array, ddof=1)) if np.count_nonzero(np.isfinite(array)) > 1 else np.nan
