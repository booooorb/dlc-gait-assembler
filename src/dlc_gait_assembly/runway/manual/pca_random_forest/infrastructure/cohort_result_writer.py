"""Persist cohort tables and figures in their established output formats."""

from pathlib import Path

from dlc_gait_assembly.runway.manual.pca_random_forest.infrastructure.cohort_figure_renderer import (
    render_run_grouped_random_forest,
    render_run_pca,
)
from dlc_gait_assembly.runway.manual.pca_random_forest.infrastructure.cohort_session_summary_reader import (
    load_session_summaries,
)


class CohortResultWriter:
    def prepare(self, destination):
        Path(destination).mkdir(parents=True, exist_ok=True)

    def read_summaries(self, paths, pd):
        return load_session_summaries(paths, pd)

    def write_table(self, table, path, **options):
        table.to_csv(path, **options)

    def export_calculation(self, result, destination):
        paths = []
        for table in result.tables:
            path = destination / table.name
            self.write_table(table.dataframe, path, index=table.include_index)
            paths.append(path)
        if "pca" in result.figures:
            paths.extend(render_run_pca(result.figures["pca"], destination))
        if "random_forest" in result.figures:
            paths.extend(render_run_grouped_random_forest(result.figures["random_forest"], destination))
        return (tuple(paths), result.message)
