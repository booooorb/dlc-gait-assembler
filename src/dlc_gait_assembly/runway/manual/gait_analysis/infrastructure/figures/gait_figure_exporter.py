"""Render calculated gait outputs while preserving feature-specific figure filenames."""

from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.alma_figure_exporter import (
    generate_alma_representations,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_stickplot_renderer import (
    render_prepared_stickplot,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.rustlab1_figure_exporter import (
    generate_rustlab1_figures,
)


class GaitFigureExporter:
    def render_alma(self, parameters, destination, name):
        import matplotlib.pyplot as plt
        import pandas as pd

        parameters = parameters.copy()
        parameters["limb (hind left / right)"] = name
        return generate_alma_representations(parameters, destination, name, plt, pd, write_tables=False)

    def render_rustlab1(self, raw, parameters, extracted, destination, settings, filtering, preprocessed):
        import matplotlib.pyplot as plt

        return generate_rustlab1_figures(
            raw, parameters, extracted, destination, settings, filtering, plt, preprocessed
        )

    def render_stickplot(self, prepared, destination):
        return render_prepared_stickplot(prepared, destination)
