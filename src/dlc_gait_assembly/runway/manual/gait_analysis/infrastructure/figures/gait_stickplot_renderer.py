"""Render prepared coordinates and selected cycles into side/synchronized stickplots."""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator

from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.temporal_speed_mixture import PHASE_SUPPORT_THRESHOLD

# Workers return SVG bytes to Qt; rendering must not create Matplotlib GUI windows.
matplotlib.use("Agg")


PHASE_COLOURS = {"stance": "#777777", "swing": "#e69a32", "drag": "#cf4040", "unknown": "#c5cdd3"}


def stickplot_phase_codes(is_stance, count, trusted=None, is_drag=None, phase_confidence=None):
    """Use the detector's labels at source frames; do not redetect from the drawing."""
    codes = np.full(count, "unknown", dtype=object)
    stance = np.asarray(is_stance, dtype=float).reshape(-1)
    available = min(count, len(stance))
    for value, name in ((0, "swing"), (1, "stance")):
        codes[np.flatnonzero(stance[:available] == value)] = name
    if is_drag is not None:
        drag = np.asarray(is_drag, dtype=bool).reshape(-1)
        positions = np.flatnonzero(drag[:count])
        codes[positions[codes[positions] == "swing"]] = "drag"
    if trusted is not None:
        valid = np.zeros(count, dtype=bool)
        trusted = np.asarray(trusted, dtype=bool)
        valid[: min(count, len(trusted))] = trusted[:count]
        codes[~valid] = "unknown"
    if phase_confidence is not None:
        support = np.full(count, np.nan)
        scores = np.asarray(phase_confidence, float).reshape(-1)
        support[: min(count, len(scores))] = scores[:count]
        codes[~np.isfinite(support) | (support < PHASE_SUPPORT_THRESHOLD)] = "unknown"
    return codes


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
    *,
    parameters=None,
    method="ALMA (legacy)",
    timing_source="Side toe",
    view_label="",
    trusted=None,
    axis_limits=None,
    tracking_only=False,
    phase_confidence=None,
):
    frames = np.arange(start, end + 1)
    phases = stickplot_phase_codes(is_stance, len(filt_corrected_df), trusted, is_drag, phase_confidence)
    # One shared, line-only layout for previews and exports. No point markers or
    # method-dependent frame selection; every finite source segment is retained.
    with plt.rc_context(
        {
            "font.size": 10,
            "axes.edgecolor": "#999999",
            "axes.linewidth": 0.6,
            "text.color": "#333333",
            "svg.fonttype": "none",
            "lines.marker": "None",
        }
    ):
        fig = plt.figure(figsize=(14, 6), facecolor="white")
        skeleton = fig.add_axes((0.075, 0.32, 0.90, 0.49))
        timeline = fig.add_axes((0.075, 0.12, 0.90, 0.075))
        try:
            for frame in frames:
                xs, ys = x_coords[frame].to_numpy(float), y_coords[frame].to_numpy(float)
                phase = phases[frame]
                for joint in range(len(bodyparts) - 1):
                    if np.isfinite(xs[joint : joint + 2]).all() and np.isfinite(ys[joint : joint + 2]).all():
                        skeleton.plot(
                            xs[joint : joint + 2],
                            ys[joint : joint + 2],
                            color=PHASE_COLOURS[phase],
                            linewidth=0.65,
                            alpha=0.65,
                            marker=None,
                            gid=f"stick-frame-{frame}-{phase}-segment-{joint}",
                        )
            skeleton.set_xlabel("X (pixels)", labelpad=5)
            skeleton.set_ylabel("Y (pixels)", labelpad=8)
            skeleton.invert_yaxis()
            if axis_limits is not None:
                skeleton.set_xlim(*axis_limits[0])
                skeleton.set_ylim(*axis_limits[1][::-1])
            skeleton.xaxis.set_major_locator(MaxNLocator(6))
            skeleton.yaxis.set_major_locator(MaxNLocator(4))
            skeleton.grid(False)
            for side in ("top", "right"):
                skeleton.spines[side].set_visible(False)
            skeleton.tick_params(length=3, colors="#666666", labelsize=9)
            labels = {"stance": "Stance", "swing": "Swing", "unknown": "Uncertain"}
            legend = [
                Line2D([0], [0], color=PHASE_COLOURS[key], linewidth=3, marker=None, label=labels[key])
                for key in labels
            ]
            fig.legend(
                handles=legend,
                loc="upper right",
                bbox_to_anchor=(0.975, 0.91),
                frameon=False,
                ncol=3,
                fontsize=10,
                handlelength=1.5,
            )
            selected = phases[frames]
            run_edges = np.r_[0, np.flatnonzero(selected[1:] != selected[:-1]) + 1, len(frames)]
            for left, right in zip(run_edges[:-1], run_edges[1:], strict=True):
                phase = selected[left]
                timeline.broken_barh(
                    [(start + left, right - left)],
                    (0, 1),
                    facecolors=PHASE_COLOURS[phase],
                    edgecolors="none",
                    gid=f"phase-{start + left}-{start + right - 1}-{phase}",
                )
            if parameters is not None:
                for _, row in parameters.iterrows():
                    first = float(row["stride_start (frame)"])
                    timeline.axvline(first, color="white", linewidth=0.8, gid=f"stride-start-{int(first)}")
            timeline.set_xlim(start, end + 1)
            timeline.set_ylim(0, 1)
            timeline.set_yticks([])
            timeline.set_ylabel("Phase", labelpad=8)
            timeline.set_xlabel("Frame", labelpad=6)
            timeline.xaxis.set_major_locator(MaxNLocator(8, integer=True))
            timeline.tick_params(length=0, labelsize=9, colors="#666666", pad=5)
            for spine in timeline.spines.values():
                spine.set_visible(False)
            count = len(parameters) if parameters is not None else 0
            accepted = sum(np.isfinite(float(v)) for v in parameters["cycle duration (s)"]) if count else 0
            title = f"{view_label} stick plot" if view_label else "Stick plot"
            fig.text(0.075, 0.95, title, fontsize=16, va="top")
            fig.text(0.075, 0.89, method, fontsize=10, color="#666666", va="top")
            fig.text(
                0.975,
                0.95,
                f"{end - start + 1} frames   |   {count} strides   |   {accepted} accepted",
                fontsize=10,
                color="#666666",
                ha="right",
                va="top",
            )
            note = "White lines mark stride starts. Full recording shown."
            if phase_confidence is not None:
                note += " Pale: phase support below 70% or unavailable."
            fig.text(0.075, 0.02, note, fontsize=9, color="#777777")
            fig.savefig(
                filename,
                format="svg",
                metadata={
                    "Description": f"Full recording: frames {start}–{end}. Timing: {timing_source}. "
                    f"{count} detected strides; {accepted} accepted. All finite source segments retained."
                },
            )
        finally:
            plt.close(fig)


class GaitStickplotRenderer:
    def render_detection(self, parameters, coordinates, raw, settings, label):
        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_detection_figure import (
            render_detection_figure,
        )

        return render_detection_figure(parameters, coordinates, raw, settings, label)

    def render_preview(self, prepared):
        from io import BytesIO

        buffer = BytesIO()
        try:
            render_prepared_stickplot(prepared, buffer)
            return buffer.getvalue()
        finally:
            plt.close("all")

    def render_rustlab1_preview(self, calculation, settings):
        from io import BytesIO

        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_step_figures import (
            generate_rustlab1_stride_preview,
        )

        buffer = BytesIO()
        generate_rustlab1_stride_preview(calculation.paw_speed, calculation.strides, buffer, settings, plt, np)
        return buffer.getvalue()


def render_prepared_stickplot(prepared, destination):
    if prepared is not None:
        continuous_stickplot(
            prepared.coordinates,
            prepared.bodyparts,
            prepared.stance,
            prepared.x_coordinates,
            prepared.y_coordinates,
            prepared.start_frame,
            prepared.end_frame,
            destination,
            prepared.dragging,
            parameters=prepared.parameters,
            method=prepared.method,
            timing_source=prepared.timing_source,
            view_label=prepared.view_label,
            trusted=prepared.trusted,
            axis_limits=prepared.axis_limits,
            tracking_only=prepared.tracking_only,
            phase_confidence=prepared.phase_confidence,
        )
