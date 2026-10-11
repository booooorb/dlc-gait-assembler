"""Selectable, confidence-aware overground detectors, compared on source frames."""

from functools import partial

import numpy as np
import pandas as pd
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_spontaneous_cycles import (
    clean_short_boolean_runs,
    robust_stance_segments_from_toe,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.stride_candidates import (
    EXPERIMENTAL_METHODS,
    ORIGINAL_ALMA,
    RELATIVE_METHODS,
    candidate_stance,
    original_alma_detection,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import CONTEXT_MIXTURE_METHOD
from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.tracking_gap_policy import tracking_gap_frames

RUSTLAB1_METHOD = "RustLab1 (bottom paw)"
BOTTOM_METHODS = ("Bottom paw speed", RUSTLAB1_METHOD)
STRIDE_METHODS = ("ALMA (legacy)", "Adaptive paw speed", "Paw excursion peaks", *BOTTOM_METHODS, *EXPERIMENTAL_METHODS)
STRIDE_METHOD_DESCRIPTIONS = {
    "ALMA (legacy)": "The app’s modified ALMA detector (separate from original 2021). Uses side-view toe speed and height with recording-wide thresholds. Only complete stance-to-stance cycles are retained; cycles crossing long tracking gaps are excluded.",
    "Adaptive paw speed": "Uses side-view toe speed with thresholds that adapt over a moving half-second window. Slow movement enters stance; faster movement enters swing. Complete stance-to-stance cycles are retained when tracking is usable.",
    "Paw excursion peaks": "Uses the toe’s forward/backward position relative to the hip. Each forward-position peak begins a stride; maximum retraction ends inferred stance. This estimates contact from motion and needs both toe and hip tracking.",
    "Bottom paw speed": "Uses the adaptive speed method on the bottom hind paws: lhpaw sets left timing and rhpaw sets right timing. Those exact frames colour the side-view stick plots. Paired videos must be synchronized; side views still supply limb geometry.",
    RUSTLAB1_METHOD: "Uses RustLab1’s horizontal bottom-paw displacement rule: stance at or below the speed threshold, swing above it. Left and right hind paws set their own side-view stick-plot timing. Adjust the speed threshold below for your recording.",
    ORIGINAL_ALMA: "Original ALMA spontaneous-walking rule (2021 source): toe displacement ≤0.001 px/frame, onset confidence >0.6 and >20 px between admitted contacts. Often too strict for noisy overground tracking. Complete cycles only; source-frame alignment and gap checks are applied.",
    "Speed histogram (Otsu)": "Experimental: splits the log-speed histogram into slow contact and fast swing using maximum between-class separation. One recording-wide threshold; no training data.",
    CONTEXT_MIXTURE_METHOD: "Experimental: starts with Speed mixture probabilities, then uses preceding and following frames to refine stance/swing support. Consistent neighbours strengthen a phase; conflicting evidence can reduce certainty. Pale frames have less than 70% model support or unavailable tracking. Scores estimate phase, not marker-tracking accuracy.",
    "Speed mixture (GMM)": "Experimental: fits two Gaussian groups to log toe speed. The slower group is stance. Useful when the speed distribution has two distinct modes.",
    "Paw height mixture (GMM)": "Experimental: fits two groups to side-view toe height. The lower spatial group is stance. Requires a stable camera and visible paw clearance.",
    "Hip-relative velocity": "Experimental: stance is backward toe movement relative to the hip, oriented to the walking direction; forward relative motion is swing. Needs reliable hip tracking.",
    "Height + speed contact": "Experimental: combines locally low toe speed with proximity to the local floor-height estimate. Both thresholds adapt over half a second.",
    "Temporal speed + height": "Experimental: a two-state sequence model combines locally normalized speed (60%) and height (40%), with a penalty against rapid phase switches. Restarts across tracking gaps.",
}


def trusted_samples(likelihood, cutoff, maximum_gap):
    values = np.asarray(likelihood, dtype=float)
    valid = np.isfinite(values) & (values >= cutoff) if cutoff > 0 else np.ones(len(values), dtype=bool)
    trusted = valid.copy()
    # Only bridge short, internal gaps. Long gaps and recording edges stay invalid.
    edges = np.diff(np.r_[True, valid, True].astype(int))
    for start, stop in zip(np.flatnonzero(edges == -1), np.flatnonzero(edges == 1), strict=True):
        if start > 0 and stop < len(valid) and stop - start <= maximum_gap:
            trusted[start:stop] = True
    return valid, trusted


def cycles_from_stance(stance, trusted, minimum_frames):
    stance = np.asarray(stance, dtype=bool)
    # Resuming tracking during stance is not an observed touchdown. Otherwise a
    # long dropout creates a false onset and a truncated, apparently valid stride.
    onsets = np.flatnonzero(stance & trusted & ~np.r_[False, stance[:-1]] & np.r_[True, trusted[:-1]])
    starts, ends = [], []
    for start, stop in zip(onsets[:-1], onsets[1:], strict=True):
        if stop - start >= minimum_frames and trusted[start : stop + 1].all() and (~stance[start:stop]).any():
            starts.append(int(start))
            ends.append(int(stop - 1))
    return starts, ends


def detect_strides(
    x,
    y,
    likelihood,
    frame_rate,
    *,
    method,
    cutoff=0.5,
    maximum_gap=-1,
    relative_x=None,
    reference_likelihood=None,
    diagnostics=None,
    coordinate_valid=None,
    right_to_left="auto",
    original_x=None,
    mixture_context_ms=60.0,
    **_,
):
    x, y = np.asarray(x, float), np.asarray(y, float)
    maximum_gap = tracking_gap_frames(maximum_gap, frame_rate)
    if reference_likelihood is not None:
        likelihood = np.minimum(np.asarray(likelihood, float), reference_likelihood)
    valid, trusted = trusted_samples(likelihood, cutoff, maximum_gap)
    if coordinate_valid is not None:
        valid, trusted = trusted_samples(valid & coordinate_valid, 0.5, maximum_gap)
    trusted &= np.isfinite(x) & np.isfinite(y)
    valid &= np.isfinite(x) & np.isfinite(y)
    if diagnostics is not None:
        diagnostics.update(
            x=x,
            y=y,
            confidence=np.asarray(likelihood, float),
            observed=valid,
            trusted=trusted,
            maximum_gap_frames=maximum_gap,
        )
    if len(x) < 4 or trusted.sum() < 4:
        if diagnostics is not None:
            diagnostics["trusted"] = np.zeros(len(x), bool)
        return np.zeros(len(x), dtype=bool), [], [], np.nan
    # Filtering a constant trace leaves floating-point ripples. Distribution and
    # sign-based detectors must not turn subpixel jitter into walking cycles.
    if max(np.ptp(x[trusted]), np.ptp(y[trusted])) < 0.5:
        stance = trusted.copy()
        if diagnostics is not None:
            diagnostics["stance"] = stance
            if method == CONTEXT_MIXTURE_METHOD:
                ambiguous = np.where(trusted, 0.5, np.nan)
                diagnostics.update(
                    raw_stance_probability=ambiguous,
                    stance_probability=ambiguous,
                    phase_confidence=ambiguous,
                    mixture_context_ms=mixture_context_ms,
                )
        return stance.tolist(), [], [], float(np.nanmedian(y[trusted]))
    if method == ORIGINAL_ALMA:
        stance, starts, ends = original_alma_detection(
            x if original_x is None else original_x, np.asarray(likelihood, float), trusted
        )
        if diagnostics is not None:
            diagnostics["stance"] = stance
        return stance.tolist(), starts, ends, float(np.nanpercentile(y[trusted], 90))
    if method == "ALMA (legacy)":
        mask, _starts, _ends, ground = robust_stance_segments_from_toe(
            x, y, likelihood, frame_rate, likelihood_min=cutoff
        )
        # Legacy differences are aligned to frames 1..N-1. Put them back on the
        # source frame axis and exclude partial tails and long confidence gaps.
        stance = np.r_[mask[0], mask] if len(mask) else np.zeros(len(x), dtype=bool)
        stance = stance[: len(x)] & trusted
        starts, ends = cycles_from_stance(stance, trusted, max(3, round(frame_rate * 0.08)))
        if diagnostics is not None:
            diagnostics["stance"] = stance
        return stance.tolist(), starts, ends, ground
    speed = median_filter(np.hypot(np.gradient(x), np.gradient(y)), size=3, mode="nearest")
    motion_reference = x - relative_x if relative_x is not None else x
    travel = (
        np.nanmedian(np.diff(motion_reference)[trusted[1:] & trusted[:-1]])
        if right_to_left == "auto"
        else (-1 if right_to_left else 1)
    )
    direction = -1 if travel < 0 else 1
    if method in EXPERIMENTAL_METHODS:
        stance = candidate_stance(
            method,
            x,
            y,
            speed,
            trusted,
            frame_rate,
            relative_x,
            direction,
            diagnostics=diagnostics,
            context_ms=mixture_context_ms,
        )
        # The contextual model already imposes persistence. Further boolean cleanup
        # would make the displayed phase contradict its posterior probability.
        if method != CONTEXT_MIXTURE_METHOD:
            stance = clean_short_boolean_runs(stance, max(2, round(frame_rate * 0.02)))
        stance = np.asarray(stance, bool) & trusted
        starts, ends = cycles_from_stance(stance, trusted, max(3, round(frame_rate * 0.08)))
        if diagnostics is not None:
            diagnostics.update(speed=speed, stance=stance)
        return stance.tolist(), starts, ends, float(np.nanpercentile(y[trusted], 90))
    reliable_speed = pd.Series(np.where(trusted, speed, np.nan))
    window = max(7, int(frame_rate * 0.5) | 1)
    low = reliable_speed.rolling(window, center=True, min_periods=3).quantile(0.25).to_numpy()
    high = reliable_speed.rolling(window, center=True, min_periods=3).quantile(0.70).to_numpy()
    low = np.where(np.isfinite(low), low, np.nanquantile(speed[trusted], 0.25))
    high = np.maximum(np.where(np.isfinite(high), high, np.nanquantile(speed[trusted], 0.70)), low + 0.01)
    if diagnostics is not None:
        diagnostics.update(speed=speed, low=low, high=high)
    stance = np.zeros(len(x), dtype=bool)
    state = False
    for i in range(len(x)):
        if not trusted[i]:
            state = False
        elif speed[i] <= low[i]:
            state = True
        elif speed[i] >= high[i]:
            state = False
        stance[i] = state
    stance = np.asarray(clean_short_boolean_runs(stance, max(2, round(frame_rate * 0.02))), dtype=bool) & trusted
    minimum_frames = max(3, round(frame_rate * 0.08))
    starts, ends = cycles_from_stance(stance, trusted, minimum_frames)
    if method == "Paw excursion peaks":
        if relative_x is None:
            raise ValueError("Paw excursion detection requires a tracked hip reference.")
        signal = np.asarray(relative_x, float)
        # Determine travel direction from robust displacement, independent of camera mirroring.
        oriented = signal * direction
        finite = trusted & np.isfinite(oriented)
        filled = pd.Series(np.where(finite, oriented, np.nan)).interpolate(limit_direction="both").to_numpy()
        if diagnostics is not None:
            diagnostics.update(relative_x=filled, trusted=finite)
        spread = np.nanpercentile(filled[finite], 90) - np.nanpercentile(filled[finite], 10) if finite.any() else 0
        peaks, _properties = find_peaks(filled, distance=minimum_frames, prominence=max(0.5, spread * 0.15))
        starts, ends = [], []
        # Partial edge cycles still have inferred phase; only complete peak pairs
        # receive stride numbers. Long gaps remain unknown through the trusted mask.
        stance = (np.gradient(filled) <= 0) & finite
        for start, stop in zip(peaks[:-1], peaks[1:], strict=True):
            if finite[start : stop + 1].all() and stop - start <= frame_rate * 2:
                starts.append(int(start))
                ends.append(int(stop - 1))
                # Stance ends at maximum retraction within this peak-to-peak cycle.
                trough = start + int(np.argmin(filled[start : stop + 1]))
                stance[start:stop] = False
                stance[start:trough] = True
    ground = float(np.nanpercentile(y[trusted], 90))
    if diagnostics is not None:
        diagnostics["stance"] = stance
    return stance.tolist(), starts, ends, ground


def side_detector(settings, dataframe, diagnostics=None, original_dataframe=None):
    method = getattr(settings, "stride_detection_method", STRIDE_METHODS[0])
    if method not in STRIDE_METHODS:
        raise ValueError(f"Unknown stride detection method: {method}")
    if method in BOTTOM_METHODS:
        raise ValueError(f"{method} requires paired left, right, and bottom CSVs.")
    relative = None
    reference_likelihood = None
    if method in RELATIVE_METHODS:
        from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter

        relative = butterworth_filter(
            dataframe["toe x"], settings.frame_rate, settings.filter_cutoff
        ) - butterworth_filter(dataframe["hip x"], settings.frame_rate, settings.filter_cutoff)
        reference_likelihood = dataframe["hip likelihood"].to_numpy(float)
    return partial(
        detect_strides,
        method=method,
        cutoff=settings.likelihood_threshold,
        maximum_gap=settings.max_interpolation_gap_frames,
        mixture_context_ms=getattr(settings, "mixture_context_ms", 60.0),
        relative_x=relative,
        reference_likelihood=reference_likelihood,
        diagnostics=diagnostics,
        right_to_left=settings.right_to_left,
        original_x=(original_dataframe if original_dataframe is not None else dataframe)["toe x"].to_numpy(float),
    )


def bottom_detection(raw, side, settings, mappings=None, diagnostics=None):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_view_alignment import (
        align_multiview_coordinates,
    )

    aligned = align_multiview_coordinates({"bottom": raw}, pd, mappings)
    marker = f"d-back-{side}"
    required = [(marker, coord) for coord in ("x", "y", "likelihood")]
    if not all(key in aligned for key in required):
        raise ValueError(f"Bottom paw speed needs the {side} hind paw mapped in the bottom CSV.")
    x, y, confidence = [pd.to_numeric(aligned[key], errors="coerce").to_numpy(float) for key in required]
    if diagnostics is not None:
        diagnostics.update(raw_x=x.copy(), raw_y=y.copy(), signal_label=f"Bottom {side} hind paw")
    coordinate_valid = np.isfinite(x) & np.isfinite(y)
    confidence = np.where(coordinate_valid, confidence, np.nan)
    if settings.stride_detection_method == RUSTLAB1_METHOD:
        return rustlab1_bottom_detection(aligned, marker, confidence, settings, diagnostics)
    # Interpolate only for signal processing; trusted_samples excludes long gaps from cycles.
    x, y = [
        pd.Series(np.where(confidence >= settings.likelihood_threshold, a, np.nan))
        .interpolate(limit_direction="both")
        .to_numpy()
        for a in (x, y)
    ]
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_signal_filter import butterworth_filter

    x, y = [butterworth_filter(a, settings.frame_rate, settings.filter_cutoff) for a in (x, y)]
    return detect_strides(
        x,
        y,
        confidence,
        settings.frame_rate,
        method="Bottom paw speed",
        cutoff=settings.likelihood_threshold,
        maximum_gap=settings.max_interpolation_gap_frames,
        diagnostics=diagnostics,
        coordinate_valid=coordinate_valid,
    )


def rustlab1_bottom_detection(aligned, marker, confidence, settings, diagnostics=None):
    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma import alma_signal_filter
    from dlc_gait_assembly.runway.manual.gait_analysis.business.preprocessing.gait_coordinate_normalization import (
        prepare_alma_coordinates,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_analysis_settings import (
        RustLab1StandaloneSettings,
    )
    from dlc_gait_assembly.runway.manual.gait_analysis.business.rustlab1.rustlab1_stride_detection import (
        detect_rustlab1_strides,
        rustlab1_stance_mask,
    )

    cfg = RustLab1StandaloneSettings(
        frame_rate=settings.frame_rate,
        filter_cutoff=settings.filter_cutoff,
        likelihood_threshold=settings.likelihood_threshold,
        reference_paw=marker,
        stance_speed_threshold_px_frame=settings.stance_speed_threshold_px_frame,
        maximum_tracking_speed_px_frame=settings.maximum_tracking_speed_px_frame,
        minimum_stance_frames=settings.minimum_stance_frames,
        minimum_swing_frames=settings.minimum_swing_frames,
    )
    prepared = prepare_alma_coordinates(aligned, cfg, alma_signal_filter, markers=(marker,))
    x, y = (prepared.series[marker][axis] for axis in ("x", "y"))
    maximum_gap = tracking_gap_frames(settings.max_interpolation_gap_frames, settings.frame_rate)
    observed, trusted = trusted_samples(confidence, settings.likelihood_threshold, maximum_gap)
    trusted &= np.isfinite(x) & np.isfinite(y)
    stance, speed = rustlab1_stance_mask(x, cfg, np)
    stance &= trusted
    cycles = detect_rustlab1_strides(prepared, cfg, pd, np, trusted=trusted, allow_empty=True)
    if diagnostics is not None:
        diagnostics.update(
            x=x,
            y=y,
            speed=speed,
            stance=stance,
            trusted=trusted,
            observed=observed,
            maximum_gap_frames=maximum_gap,
            confidence=confidence,
            low=np.full(len(x), cfg.stance_speed_threshold_px_frame),
            high=np.full(len(x), cfg.stance_speed_threshold_px_frame),
        )
    starts = cycles["stride_start (frame)"].tolist() if len(cycles) else []
    ends = cycles["stride_end (frame)"].tolist() if len(cycles) else []
    return stance.tolist(), starts, ends, float(np.nanpercentile(y[trusted], 90)) if trusted.any() else np.nan


def side_cycles_from_bottom(detection, cutoff):
    """Use bottom timing, but estimate ground height in the side camera's coordinates."""
    stance, starts, ends, _bottom_ground = detection

    def detector(_x, y, likelihood, _frame_rate):
        y, likelihood = np.asarray(y, float), np.asarray(likelihood, float)
        valid = np.isfinite(y)
        if cutoff > 0:
            valid &= np.isfinite(likelihood) & (likelihood >= cutoff)
        contact = valid & np.asarray(stance, bool)
        values = y[contact] if contact.any() else y[valid]
        ground = float(np.percentile(values, 90)) if len(values) else np.nan
        return stance, starts, ends, ground

    return detector
