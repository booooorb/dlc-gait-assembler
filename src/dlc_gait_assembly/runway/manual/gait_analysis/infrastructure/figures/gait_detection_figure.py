"""Full-recording diagnostic of the actual signal supplied to each detector."""

from io import BytesIO

import numpy as np
import pandas as pd


def render_detection_figure(parameters, coordinates, raw, settings, label):
    from matplotlib import pyplot as plt

    from dlc_gait_assembly.runway.manual.gait_analysis.business.alma.alma_bodypart_aliases import fix_column_names

    normalized, _, _ = fix_column_names(raw.copy(), settings.custom_bodypart_mapping)
    trace = coordinates.attrs.get("detection_diagnostics", {})
    signal_name = trace.get("signal_label", "Side toe")
    frames = np.arange(len(normalized))
    confidence = np.asarray(
        trace.get("confidence", pd.to_numeric(normalized["toe likelihood"], errors="coerce")), float
    )
    trusted = np.asarray(
        trace.get("trusted", np.isfinite(confidence) & (confidence >= settings.likelihood_threshold)), bool
    )
    accepted = pd.to_numeric(parameters["cycle duration (s)"], errors="coerce").gt(0)
    has_signal = "speed" in trace or "relative_x" in trace
    fig, axes = plt.subplots(
        4 if has_signal else 3, 1, figsize=(12, 8 if has_signal else 7), sharex=True, constrained_layout=True
    )
    try:
        for ax, axis in zip(axes[:2], ("x", "y"), strict=True):
            original = trace.get(f"raw_{axis}", normalized[f"toe {axis}"])
            processed = np.asarray(trace.get(axis, coordinates[f"toe {axis}"]), float)
            ax.plot(frames, original, color="#8c8c8c", linewidth=0.8, label=f"{signal_name}: raw {axis.upper()}")
            ax.plot(frames, np.where(trusted, processed, np.nan), color="#3377aa", label="Detector coordinates")
            ax.set_ylabel(f"{axis.upper()} (pixels)")
        if has_signal:
            signal_ax = axes[2]
            if "relative_x" in trace:
                signal_ax.plot(
                    frames,
                    np.where(trusted, trace["relative_x"], np.nan),
                    color="#3377aa",
                    label="Direction-adjusted toe minus hip X",
                )
                signal_ax.set_ylabel("Relative X (pixels)")
            else:
                signal_ax.plot(
                    frames, np.where(trusted, trace["speed"], np.nan), color="#3377aa", label=f"{signal_name} speed"
                )
                signal_ax.plot(
                    frames, trace["low"], color="#49865d", linestyle="--", linewidth=0.8, label="Stance-entry threshold"
                )
                signal_ax.plot(
                    frames, trace["high"], color="#bb624e", linestyle="--", linewidth=0.8, label="Stance-exit threshold"
                )
                signal_ax.set_ylabel("Speed (px/frame)")
        for position, (_, row) in enumerate(parameters.iterrows()):
            start, end = pd.to_numeric(row[["stride_start (frame)", "stride_end (frame)"]], errors="coerce")
            if np.isfinite(start) and np.isfinite(end):
                color = "#49865d" if accepted.iloc[position] else "#bb624e"
                for ax in axes[:-1]:
                    ax.axvspan(start, end + 1, color=color, alpha=0.13)
                    ax.axvline(start, color=color, alpha=0.6, linewidth=0.8)
        confidence_ax = axes[-1]
        confidence_label = (
            "Minimum toe / hip confidence"
            if settings.stride_detection_method == "Paw excursion peaks"
            else f"{signal_name} confidence"
        )
        confidence_ax.plot(frames, confidence, label=confidence_label, color="#72539a")
        confidence_ax.axhline(settings.likelihood_threshold, color="#b44040", linestyle="--", label="Selected cutoff")
        confidence_ax.fill_between(
            frames, 0, 1, where=~trusted, color="#b44040", alpha=0.18, label="Excluded tracking gap"
        )
        confidence_ax.set_ylim(0, 1.05)
        confidence_ax.set_ylabel("Confidence")
        for ax in axes:
            ax.legend(loc="upper right", fontsize=8)
            ax.grid(alpha=0.2)
        confidence_ax.set_xlabel("Source frame")
        title = f"{label} — {settings.stride_detection_method}: {accepted.sum()}/{len(parameters)} accepted cycles"
        fig.suptitle(title + "\nGreen: accepted · red: filtered · all source frames included", fontsize=12)
        buffer = BytesIO()
        fig.savefig(buffer, format="svg")
        return buffer.getvalue()
    finally:
        plt.close(fig)
