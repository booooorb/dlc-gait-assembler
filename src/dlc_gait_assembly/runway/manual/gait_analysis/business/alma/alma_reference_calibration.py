"""Estimate anatomical-reference scale and treadmill speed from tracked coordinates."""

from __future__ import annotations

import numpy as np
import scipy


def estimate_pixels_per_cm_from_bodyparts(pd_dataframe, bodypart1, bodypart2, known_distance_cm=None):
    """
    Camera-distance independent calibration using anatomical reference
    Estimates pixels_per_cm by measuring a body segment with known real-world length

    bodypart1, bodypart2: two bodyparts defining a reference segment (e.g., 'hip' to 'knee')
    known_distance_cm: known real-world distance between bodyparts in cm
                       If None, uses typical rodent measurements:
                       - hip to knee (femur): ~2.5 cm for mouse, ~4.5 cm for rat
                       - knee to ankle (tibia): ~2.0 cm for mouse, ~3.5 cm for rat
    """
    bodypart1_variants = [bodypart1, bodypart1.lower(), bodypart1.replace("_", " ")]
    bodypart2_variants = [bodypart2, bodypart2.lower(), bodypart2.replace("_", " ")]

    def find_bodypart_column(bodypart_variants, coord):
        for variant in bodypart_variants:
            col_name = f"{variant} {coord}"
            if col_name in pd_dataframe.columns:
                return col_name
        return f"{bodypart_variants[0]} {coord}"

    try:
        x1 = pd_dataframe[find_bodypart_column(bodypart1_variants, "x")]
        y1 = pd_dataframe[find_bodypart_column(bodypart1_variants, "y")]
        x2 = pd_dataframe[find_bodypart_column(bodypart2_variants, "x")]
        y2 = pd_dataframe[find_bodypart_column(bodypart2_variants, "y")]
        likelihood1 = pd_dataframe[find_bodypart_column(bodypart1_variants, "likelihood")]
        likelihood2 = pd_dataframe[find_bodypart_column(bodypart2_variants, "likelihood")]
        valid_frames = (likelihood1 > 0.9) & (likelihood2 > 0.9)
        n_frames_high = valid_frames.sum()
        if n_frames_high == 0:
            valid_frames = (likelihood1 > 0.7) & (likelihood2 > 0.7)
            n_frames_medium = valid_frames.sum()
            if n_frames_medium == 0:
                valid_frames = (likelihood1 > 0.5) & (likelihood2 > 0.5)
                n_frames_low = valid_frames.sum()
                if n_frames_low < 10:
                    print(f"  ✗ Insufficient tracking for {bodypart1}-{bodypart2}:")
                    print(f"    Frames with likelihood > 0.5: {n_frames_low}")
                    print("    Need at least 10 frames for reliable calibration")
                    return None
                else:
                    print(f"  ⚠ Using {n_frames_low} frames with lower confidence (>0.5)")
            else:
                print(f"  ⚠ Using {n_frames_medium} frames with medium confidence (>0.7)")
        else:
            print(f"  ✓ Using {n_frames_high} high-confidence frames (>0.9)")
        distances_px = np.sqrt((x1[valid_frames] - x2[valid_frames]) ** 2 + (y1[valid_frames] - y2[valid_frames]) ** 2)
        median_distance_px = np.median(distances_px)
        std_distance_px = np.std(distances_px)
        cv = std_distance_px / median_distance_px * 100
        if cv > 15:
            print(f"  ⚠ High variability detected: CV = {cv:.1f}%")
            print("    Segment length varies significantly across frames")
            print("    This might indicate poor tracking or actual limb flexion")
            if cv > 30:
                print("  ✗ Calibration unreliable (CV > 30%), rejecting this segment")
                return None
        if known_distance_cm is None:
            segment_key = f"{bodypart1}_{bodypart2}".lower().replace(" ", "_")
            defaults = {
                "hip_knee": 2.5,
                "knee_ankle": 2.0,
                "ankle_mtp": 0.8,
                "ankle_toe": 1.5,
                "mtp_toe": 0.7,
                "hip_ankle": 4.5,
                "iliac_crest_hip": 1.5,
                "crest_hip": 1.5,
            }
            known_distance_cm = defaults.get(segment_key, 3.0)
            print(f"  Using default distance for {bodypart1}-{bodypart2}: {known_distance_cm} cm")
        pixels_per_cm = median_distance_px / known_distance_cm
        print(f"  Segment: {median_distance_px:.1f} ± {std_distance_px:.1f} pixels (CV: {cv:.1f}%)")
        return pixels_per_cm
    except KeyError as e:
        print(f"Warning: Could not find bodypart columns for calibration: {e}")
        print(f"Available columns: {list(pd_dataframe.columns[:10])}...")
        return None


def estimate_speed(
    pd_dataframe,
    bodypart,
    cm_speed,
    frame_rate,
    right_to_left=True,
    auto_calibrate_spatial=False,
    reference_bodyparts=None,
    reference_distance_cm=None,
):
    """
    Estimate speed parameters for treadmill analysis

    auto_calibrate_spatial: if True, uses intrinsic body scaling for camera-independent calibration
    reference_bodyparts: tuple of (bodypart1, bodypart2) for spatial calibration, e.g., ('hip', 'knee')
    reference_distance_cm: known distance between reference bodyparts in cm
    """
    x_change = np.diff(pd_dataframe[f"{bodypart} x"][pd_dataframe[f"{bodypart} likelihood"] > 0.5])
    x_change_filt = x_change[
        (x_change < np.mean(x_change) + 1 * np.std(x_change)) & (x_change > np.mean(x_change) - 1 * np.std(x_change))
    ]
    if right_to_left:
        (px_speed, _) = scipy.stats.norm.fit(x_change_filt[x_change_filt > 0])
    else:
        (px_speed, _) = scipy.stats.norm.fit(x_change_filt[x_change_filt < 0])
        px_speed = -px_speed
    if cm_speed is None:
        cm_speed = None
    else:
        px_to_cm_speed_ratio = px_speed / cm_speed
    if auto_calibrate_spatial and reference_bodyparts is not None:
        pixels_per_cm = estimate_pixels_per_cm_from_bodyparts(
            pd_dataframe, reference_bodyparts[0], reference_bodyparts[1], reference_distance_cm
        )
        if pixels_per_cm is None:
            print(f"Primary segment {reference_bodyparts[0]}-{reference_bodyparts[1]} failed.")
            print("Trying fallback segments...")
            fallback_segments = [
                (("ankle", "toe"), 1.5),
                (("mtp", "toe"), 0.7),
                (("knee", "ankle"), 2.0),
                (("hip", "knee"), 2.5),
            ]
            for fallback_pair, fallback_length in fallback_segments:
                if fallback_pair == reference_bodyparts:
                    continue
                print(f"  Trying {fallback_pair[0]}-{fallback_pair[1]}...")
                pixels_per_cm = estimate_pixels_per_cm_from_bodyparts(
                    pd_dataframe, fallback_pair[0], fallback_pair[1], fallback_length
                )
                if pixels_per_cm is not None:
                    print(f"  ✓ Success with {fallback_pair[0]}-{fallback_pair[1]}")
                    break
        if pixels_per_cm is not None:
            print(f"Auto-calibrated: {pixels_per_cm:.2f} pixels/cm (camera-distance independent)")
        else:
            print("⚠ All segments failed, falling back to traditional method")
            pixels_per_cm = 1 / (cm_speed / px_speed / frame_rate)
    else:
        pixels_per_cm = 1 / (cm_speed / px_speed / frame_rate)
    return (cm_speed, px_speed, pixels_per_cm, px_to_cm_speed_ratio)
