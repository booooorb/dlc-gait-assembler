"""Render native ALMA stick plots from the supplied updated ALMA implementation."""

import json

import matplotlib
import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_treadmill_validation import BODY_PARTS

matplotlib.use("Agg")
from matplotlib import pyplot as plt


def render_native_alma_stickplot(prepared, destination, output_format="svg", dpi=None):
    """Use ALMA's own continuous-cycle plots in previews and saved figures."""
    report = prepared.coordinates.attrs.get("analysis_report", {})
    if report.get("analysis_type") == "spontaneous":
        masks = []
        for item in report["intervals"]:
            if item["retained"]:
                masks.append(
                    prepared.coordinates["runway drag"]
                    .iloc[item["stance_end_frame"] : item["end_frame"]]
                    .to_numpy(dtype=bool)
                )
            else:
                masks.append(np.array([], dtype=bool))
        return plot_continuous(
            prepared.parameters,
            prepared.coordinates,
            prepared.stance,
            masks,
            prepared.continuous_cycles,
            destination,
            True,
            prepared.coordinates.attrs.get("stickplot_source", "tracked"),
            output_format,
            dpi,
        )
    return continuous_stickplot(
        prepared.coordinates,
        prepared.bodyparts,
        prepared.stance,
        prepared.x_coordinates,
        prepared.y_coordinates,
        prepared.start_frame,
        prepared.end_frame,
        destination,
        prepared.dragging,
        output_format=output_format,
        dpi=dpi,
        metadata={
            "Description": json.dumps(
                {
                    "renderer": "ALMA native",
                    "coordinate_source": "analysis",
                    "retained_intervals": [
                        {"start_frame": int(row["stride_start (frame)"]), "end_frame": int(row["stride_end (frame)"])}
                        for _, row in prepared.parameters.iterrows()
                        if pd.notna(pd.to_numeric(row["cycle duration (s)"], errors="coerce"))
                    ],
                }
            )
        },
    )


def plot_continuous(
    parameters,
    coordinates,
    phase,
    drag_masks,
    count,
    filename,
    plot,
    coordinate_source="analysis",
    output_format="svg",
    dpi=None,
):
    """Select one contiguous retained bout; never draw across a rejected/gap interval."""
    intervals = parameters.attrs["analysis_report"]["intervals"]
    groups = []
    current = []
    for i, item in enumerate(intervals):
        if not item["retained"]:
            if current:
                groups.append(current)
            current = []
        elif current and (
            item["bout_id"] != intervals[current[-1]]["bout_id"]
            or item["start_frame"] != intervals[current[-1]]["end_frame"]
        ):
            groups.append(current)
            current = [i]
        else:
            current.append(i)
    if current:
        groups.append(current)
    selected = max(groups, key=len)[: max(1, int(count))] if groups else []
    subset = parameters.iloc[selected]
    if not plot:
        return subset
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_skeleton_coordinates import (
        LOW_CONFIDENCE,
        RECONSTRUCTED,
        skeleton_coordinates,
    )

    xy, states = skeleton_coordinates(
        coordinates, coordinate_source, parameters.attrs["analysis_report"]["settings"]["confidence_threshold"]
    )
    fig, ax = plt.subplots(figsize=(12, 5))
    for i in selected:
        item = intervals[i]
        for frame in range(item["start_frame"], item["end_frame"], 2):
            color = "#999999" if phase[frame] == 1 else "#FAAF40"
            offset = frame - item["stance_end_frame"]
            if 0 <= offset < len(drag_masks[i]) and drag_masks[i][offset]:
                color = "#d62762"
            for joint in range(len(BODY_PARTS) - 1):
                points = xy[frame, joint : joint + 2]
                status = states[frame, joint : joint + 2]
                low = bool((status == LOW_CONFIDENCE).any())
                estimated = bool((status == RECONSTRUCTED).any())
                if np.isfinite(points).all():
                    ax.plot(
                        points[:, 0],
                        points[:, 1],
                        color="#b0b0b0" if low else color,
                        linewidth=0.8,
                        linestyle=":" if low else ("--" if estimated else "-"),
                    )
    if not selected:
        for frame in range(0, len(coordinates), 2):
            for joint in range(len(BODY_PARTS) - 1):
                points = xy[frame, joint : joint + 2]
                if np.isfinite(points).all():
                    ax.plot(points[:, 0], points[:, 1], color="#b0b0b0", linewidth=0.8, linestyle=":")
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_yaxis()
    label = "tracked keypoints (unfiltered)" if coordinate_source == "tracked" else "analysis coordinates (filtered)"
    ax.set(
        xlabel="x coordinate (pixel)",
        ylabel="y coordinate (pixel)",
        title=f"{len(selected)} consecutive retained cycles | {label}",
    )
    ax.legend(
        handles=[
            Line2D([0], [0], color=color, label=label)
            for color, label in [
                ("#999999", "Support"),
                ("#FAAF40", "Foot movement"),
                ("#d62762", "Near-ground movement"),
            ]
        ]
        + [
            Line2D([0], [0], color="#b0b0b0", linestyle=":", label="Low-confidence tracking"),
            Line2D([0], [0], color="#555555", linestyle="--", label="Reconstructed endpoint"),
        ],
        loc="best",
        fontsize=8,
    )
    fig.tight_layout()
    fig.savefig(
        filename,
        format=output_format,
        dpi=dpi,
        metadata={
            "Description": json.dumps(
                {
                    "renderer": "ALMA native",
                    "coordinate_source": coordinate_source,
                    "retained_intervals": [
                        {"start_frame": intervals[i]["start_frame"], "end_frame": intervals[i]["end_frame"]}
                        for i in selected
                    ],
                }
            )
        },
    )
    plt.close(fig)
    return subset


def continuous_stickplot(
    filt_corrected_df,
    bodyparts,
    is_stance,
    x_coords,
    y_coords,
    start,
    end,
    filename="truncated_stickplot",
    is_drag=None,
    drag_min_consecutive_frames=4,
    output_format="svg",
    dpi=None,
    metadata=None,
):

    x_min = min(x_coords.loc[:, start:end].min())
    x_max = max(x_coords.loc[:, start:end].max())
    x_range = x_max - x_min
    y_min = min(y_coords.loc[:, start:end].min())
    y_max = max(y_coords.loc[:, start:end].max())
    y_range = y_max - y_min
    width = max(5.0, min(20.0, 5.0 * x_range / max(y_range, 1.0)))
    plt.figure(figsize=(width, 5))

    for t in filt_corrected_df.index[start:end]:
        if t % 2 == 0:
            # plotting every two frames to reduce clutter
            toe_mtp = pd.DataFrame(pd.concat([x_coords[t].iloc[0:2], y_coords[t].iloc[0:2]], axis=1))
            mtp_ankle = pd.DataFrame(pd.concat([x_coords[t].iloc[1:3], y_coords[t].iloc[1:3]], axis=1))
            ankle_knee = pd.DataFrame(pd.concat([x_coords[t].iloc[2:4], y_coords[t].iloc[2:4]], axis=1))
            knee_hip = pd.DataFrame(pd.concat([x_coords[t].iloc[3:5], y_coords[t].iloc[3:5]], axis=1))
            hip_crest = pd.DataFrame(pd.concat([x_coords[t].iloc[4:6], y_coords[t].iloc[4:6]], axis=1))

            toe_mtp.columns = ["coord x", "coord y"]
            mtp_ankle.columns = ["coord x", "coord y"]
            ankle_knee.columns = ["coord x", "coord y"]
            knee_hip.columns = ["coord x", "coord y"]
            hip_crest.columns = ["coord x", "coord y"]

            # Determine color: red for dragging, gray for stance, orange for clean swing
            # Only show red if there are at least drag_min_consecutive_frames consecutive dragging frames
            is_dragging_frame = False
            if is_drag is not None and len(is_drag) > t and is_drag[t]:
                # Check if this dragging frame is part of a sequence with minimum consecutive frames
                drag_start = t
                drag_end = t
                # Find start of dragging sequence
                while drag_start > 0 and is_drag[drag_start - 1]:
                    drag_start -= 1
                # Find end of dragging sequence
                while drag_end < len(is_drag) - 1 and is_drag[drag_end + 1]:
                    drag_end += 1
                # Only show red if sequence is at least drag_min_consecutive_frames
                if drag_end - drag_start + 1 >= drag_min_consecutive_frames:
                    is_dragging_frame = True

            if is_dragging_frame:
                color = "#FF0000"  # Red for dragging (only if minimum consecutive frames met)
            elif is_stance[t] == 1:
                color = "#999999"  # Gray for stance
            else:
                color = "#FAAF40"  # Orange for swing

            plt.plot("coord x", "coord y", data=toe_mtp, c=color)
            plt.plot("coord x", "coord y", data=mtp_ankle, c=color)
            plt.plot("coord x", "coord y", data=ankle_knee, c=color)
            plt.plot("coord x", "coord y", data=knee_hip, c=color)
            plt.plot("coord x", "coord y", data=hip_crest, c=color)

    plt.xlabel("x coordinate (pixel)")
    plt.ylabel("y coordinate (pixel)")
    plt.legend(
        [
            f"{bodyparts[0]}-{bodyparts[1]}",
            f"{bodyparts[1]}-{bodyparts[2]}",
            f"{bodyparts[2]}-{bodyparts[3]}",
            f"{bodyparts[3]}-{bodyparts[4]}",
            f"{bodyparts[4]}-{bodyparts[5]}",
        ],
        loc="upper right",
    )

    plt.ylim((y_min - 0.5, y_max + 0.5) if y_min == y_max else (y_min, y_max))
    plt.gca().set_aspect("equal", adjustable="box")
    plt.gca().invert_yaxis()
    plt.savefig(filename, format=output_format, dpi=dpi, metadata=metadata)
    plt.close()
