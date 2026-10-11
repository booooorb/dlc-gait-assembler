"""Plot every exported parameter, retaining all recordings and missing-data counts."""

import textwrap
from io import BytesIO

import numpy as np
import pandas as pd

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    gait_parameter_catalog,
)


def parameter_figure_pages(table, page_size=12, progress_callback=None):
    from matplotlib import pyplot as plt

    names = {definition.name for definition in gait_parameter_catalog()}
    from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_bottom_windows import (
        BOTTOM_STRIDE_NAMES,
        GENERAL_PHASE_NAMES,
    )

    names.update((*BOTTOM_STRIDE_NAMES, *GENERAL_PHASE_NAMES))
    columns = [name for name in table if name in names]
    general = "synchronization_start (s)" in table and "stride_start (frame)" not in table
    if not 1 <= page_size <= 12:
        raise ValueError("Figure pages support between 1 and 12 parameters.")
    groups = (
        table["recording"].fillna("Recording").astype(str)
        if "recording" in table
        else pd.Series("Recording", index=table.index)
    )
    pages = []
    for first in range(0, len(columns), page_size):
        if progress_callback:
            progress_callback(first // page_size + 1, (len(columns) + page_size - 1) // page_size)
        selected = columns[first : first + page_size]
        fig, axes = plt.subplots(4, 3, figsize=(15, 12), constrained_layout=True)
        try:
            for ax, name in zip(axes.flat, selected, strict=False):
                values = pd.to_numeric(table[name], errors="coerce").to_numpy(float)
                for group in dict.fromkeys(groups):
                    indices = np.flatnonzero((groups == group).to_numpy())
                    # Preserve source row position and leave gaps for unavailable measurements.
                    ax.plot(indices + 1, values[indices], ".-", markersize=4, linewidth=0.7, label=group)
                count = int(np.isfinite(values).sum())
                ax.set_title("\n".join(textwrap.wrap(name.replace("__", " · "), 34)), fontsize=9)
                row_label = "Recording summary" if general else "Stride row"
                ax.set_xlabel(f"{row_label} · n={count}/{len(values)} valid", fontsize=8)
                ax.set_xlim(0.5, max(1, len(values)) + 0.5)
                ax.grid(alpha=0.2)
                if count == 0:
                    ax.text(
                        0.5,
                        0.5,
                        "No valid measurements\nCheck tracking, mapping, calibration and stride filters",
                        transform=ax.transAxes,
                        ha="center",
                        va="center",
                        fontsize=8,
                    )
            for ax in list(axes.flat)[len(selected) :]:
                ax.set_visible(False)
            if len(table):
                handles, labels = axes.flat[0].get_legend_handles_labels()
                fig.legend(handles, labels, loc="outside lower center", ncol=min(4, len(labels)), fontsize=8)
            detail = (
                "Whole-recording measurements; missing values remain blank"
                if general
                else "Every stride in this table is included; missing values remain gaps"
            )
            fig.suptitle(
                f"All exported parameters · {first + 1}–{first + len(selected)} of {len(columns)}\n{detail}",
                fontsize=13,
            )
            buf = BytesIO()
            fig.savefig(buf, format="svg")
            pages.append((f"Parameters {first + 1}–{first + len(selected)}", buf.getvalue()))
        finally:
            plt.close(fig)
    return tuple(pages)
