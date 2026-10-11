"""Persist parameter tables and run metadata, validate artifacts, and delegate figures to the figure exporter."""

import tempfile
from pathlib import Path

from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.figures.gait_figure_exporter import GaitFigureExporter
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_coordinate_repository import (
    merge_multiview_rustlab1_dataframe,
)
from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.synchronized_result_writer import (
    write_synchronized_recording,
)


class GaitResultWriter:
    """Concrete table persistence and rendering for one gait-analysis session."""

    def __init__(self):
        self.figures = GaitFigureExporter()

    def resolve_calibration(self, settings):
        from dlc_gait_assembly.runway.manual.gait_analysis.infrastructure.gait_calibration_loader import (
            resolve_calibration_settings,
        )

        return resolve_calibration_settings(settings)

    def prepare(self, output_folder):
        Path(output_folder).mkdir(parents=True, exist_ok=True)
        # Fail before expensive calculations when the selected folder is unwritable.
        with tempfile.TemporaryFile(dir=output_folder):
            pass

    def read_table(self, path, **options):
        import pandas as pd

        return pd.read_csv(path, **options)

    def read_views(self, view_set, view_mappings=None):
        import pandas as pd

        return merge_multiview_rustlab1_dataframe(view_set, pd, view_mappings)

    def write_table(self, table, path, **options):
        destination = Path(path)
        with tempfile.NamedTemporaryFile(mode="w", dir=destination.parent, suffix=".csv", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            table.to_csv(temporary, **options)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def write_text(self, path, text):
        Path(path).write_text(text, encoding="utf-8")

    def validate_outputs(self, paths, expected_rows=None):
        import xml.etree.ElementTree as ET

        import pandas as pd

        for path in paths:
            path = Path(path)
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"Export did not create a nonempty file: {path}")
            if path.suffix.lower() == ".svg":
                root = ET.parse(path).getroot()
                if root.tag != "{http://www.w3.org/2000/svg}svg" or not list(root):
                    raise RuntimeError(f"Exported figure is not a valid SVG: {path}")
            elif path.suffix.lower() == ".csv":
                table = pd.read_csv(path)
                if expected_rows is not None and len(table) != expected_rows:
                    raise RuntimeError(f"Exported CSV row count does not match the analysis: {path}")

    def exists(self, path):
        return Path(path).exists()

    def render_alma(self, parameters, destination, name):
        return self.figures.render_alma(parameters, destination, name)

    def render_rustlab1(self, raw, parameters, extracted, destination, settings, filtering, preprocessed):
        return self.figures.render_rustlab1(raw, parameters, extracted, destination, settings, filtering, preprocessed)

    def render_stickplot(self, prepared, destination):
        return self.figures.render_stickplot(prepared, destination)

    def write_synchronized(self, calculation, view_set, destination):
        return write_synchronized_recording(calculation, view_set, destination)

    def get_fignums(self):
        from matplotlib import pyplot as plt

        return plt.get_fignums()

    def close(self, selection):
        from matplotlib import pyplot as plt

        plt.close(selection)
