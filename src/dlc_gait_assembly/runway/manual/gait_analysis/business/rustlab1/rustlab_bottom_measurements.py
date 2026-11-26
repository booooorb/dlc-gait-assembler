"""Calculate the underside session measures in Run_ALMA_Side_Rust_Bottom.R."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.alma_parameter_definitions import (
    ALMA_PARAMETER_NAMES,
)

BOTTOM_PAWS = ("d-back-left", "d-back-right", "d-front-left", "d-front-right")
BOTTOM_MARKERS = (*BOTTOM_PAWS, "d-center-back", "d-center-front")
ANGLE_PAWS = {"LB": "d-back-left", "LF": "d-front-left", "RB": "d-back-right", "RF": "d-front-right"}
PHASE_MEASURES = (
    "FLBR_RATIO", "FRBL_RATIO", "avg_duration", "duration_sd_diff", "avg_stride_length",
    "stride_length_sd_diff", "avg_stance_time", "avg_swing_time",
)
MEASURE_GROUPS = (
    ("SynchrCycle_downPersp", PHASE_MEASURES),
    ("Angles_downPersp", tuple(f"{paw}__{stat}_Angle" for stat in ("max", "min", "avg") for paw in ANGLE_PAWS)),
)


def calculate_bottom_tables(coordinates, side_tables, session, settings, fps, scale):
    threshold = settings.stance_speed_threshold_px_frame
    max_speed = settings.maximum_tracking_speed_px_frame
    if not np.isfinite([threshold, max_speed]).all() or not 0 <= threshold < max_speed:
        raise ValueError("Invalid underside speed thresholds.")

    phases = bottom_phases(coordinates, settings.likelihood_threshold, threshold, max_speed)
    paws = phases[phases.parameter.isin(BOTTOM_PAWS)]
    stance = paws.loc[~paws.swing].assign(time=lambda rows: rows.source_frame / fps)
    measurements = {**phase_measurements(paws, stance, scale), **angle_measurements(phases)}
    rows = [
        (*session, name, measurements.get(name, np.nan), group)
        for group, names in MEASURE_GROUPS for name in names
    ]
    rows.extend(alma_session_rows(side_tables, session))
    raw = pd.DataFrame(rows, columns=("full_id", "day", "mouse", "Measure", "Value", "ParameterGroup"))
    # Each call exports one recording, so every summary group has one subject.
    summary = raw[["day", "Measure", "ParameterGroup"]].assign(Mean=raw.Value, median=raw.Value, sd=np.nan, sem=np.nan)
    return raw, summary.sort_values(["day", "Measure", "ParameterGroup"])


def bottom_phases(coordinates, confidence, threshold, max_speed):
    valid = np.isfinite(coordinates[["x_corr", "y_corr", "likelyhood"]]).all(axis=1)
    rows = coordinates.loc[valid & (coordinates.likelyhood >= confidence)].sort_values(["parameter", "source_frame"])
    tracks = rows.groupby("parameter", sort=False)
    first = tracks.cumcount().eq(0)
    speed = tracks.x_corr.diff().abs().mask(first, 0).where(first | tracks.source_frame.diff().eq(1))
    swing = speed.gt(threshold).astype("boolean").where(speed.notna())
    # RustLab starts numbering at zero and increments on both edges of a tracking gap.
    changes = swing.ne(swing.groupby(rows.parameter, sort=False).shift()).fillna(True).mask(first, False)
    phase = changes.groupby(rows.parameter, sort=False).cumsum()
    rows = rows.assign(speed=speed, swing=swing, phase=phase).loc[np.isfinite(speed)]
    # The original phase QC pools speeds by phase number across all underside markers.
    qualified = rows.loc[rows.groupby("phase").speed.transform("max").lt(max_speed)]
    return qualified if qualified.phase.max() > 10 else qualified.iloc[:0]


def phase_measurements(paws, stance, scale):
    states = paws.pivot(index="source_frame", columns="parameter", values="swing").reindex(columns=BOTTOM_PAWS)
    states = states.dropna().astype(bool)
    moving = states.loc[states.any(axis=1)]
    back_left, back_right, front_left, front_right = (moving[paw] for paw in BOTTOM_PAWS)
    values = {"FLBR_RATIO": (front_left != back_right).mean(), "FRBL_RATIO": (front_right != back_left).mean()}
    if stance.empty:
        return values

    duration = stance.groupby("phase").time.agg(["min", "max", "std"])
    stance = stance.assign(side=stance.parameter.str.rsplit("-", n=1).str[-1])
    distance = stance.groupby(["phase", "side"]).x_corr.agg(["min", "max", "std"])
    windows = stance.groupby(["phase", "parameter"]).time.agg(["min", "max"]).reset_index()
    previous_end = windows.groupby("parameter")["max"].shift().fillna(windows["max"])
    stances = windows["max"] - windows["min"]
    swings = windows["min"] - previous_end
    later = windows.phase.ne(0)
    values.update(
        avg_duration=(duration["max"] - duration["min"]).median(),
        duration_sd_diff=duration["std"].median(),
        avg_stride_length=(distance["max"] - distance["min"]).median() / scale if scale else np.nan,
        stride_length_sd_diff=distance["std"].median() / scale if scale else np.nan,
        avg_stance_time=stances[later].median(),
        avg_swing_time=swings[later].median(),
    )
    return values


def angle_measurements(phases):
    values = {}
    coordinates = phases.set_index(["parameter", "source_frame"])[["x_corr", "y_corr"]]
    markers = coordinates.index.get_level_values("parameter")
    for name, paw in ANGLE_PAWS.items():
        center = "d-center-back" if name.endswith("B") else "d-center-front"
        if paw not in markers or center not in markers:
            continue
        delta = (coordinates.loc[paw] - coordinates.loc[center]).dropna()
        if delta.empty:
            continue
        angles = np.abs(np.degrees(np.arctan2(delta.y_corr, delta.x_corr)))
        angles = np.where(angles > 90, angles - 90, angles)
        values[f"{name}__max_Angle"], values[f"{name}__min_Angle"] = np.quantile(angles, [0.95, 0.10])
        values[f"{name}__avg_Angle"] = angles.mean()
    return values


def alma_session_rows(side_tables, session):
    rows = []
    for side in ("left", "right"):
        table = side_tables[side]
        for parameter in ALMA_PARAMETER_NAMES:
            if parameter not in table:
                raise ValueError(f"Missing ALMA column: {parameter}")
            values = pd.to_numeric(table[parameter], errors="coerce")
            values = values[np.isfinite(values)]
            rows.extend(
                (*session, f"{side}__{parameter}__{stat}", value, "ALMA_sidePersp")
                for stat, value in (("mean", values.mean()), ("sd", values.std(ddof=1)))
            )
    return rows
