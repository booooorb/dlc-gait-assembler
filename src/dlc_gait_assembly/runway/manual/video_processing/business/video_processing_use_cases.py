"""Resolve processing jobs, execute them through the exporter, and preserve output order."""

from pathlib import Path

from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_plan import plan_video_outputs
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_ports import VideoExporterPort
from dlc_gait_assembly.shared.business.execution_feedback_contracts import ExecutionFeedback


class VideoProcessingUseCases:
    def __init__(self, exporter: VideoExporterPort, settings=None, documents=None):
        self.exporter = exporter
        self.settings, self.documents = settings, documents

    def process_outputs(self, input_path, output_dir, options, feedback=None):
        feedback = feedback or ExecutionFeedback()
        jobs = plan_video_outputs(Path(input_path), options)
        results = []
        for index, job in enumerate(jobs):
            feedback.checkpoint()
            feedback.progress(index, len(jobs), f"Processing {Path(input_path).name}")
            results.append(
                self.exporter.export(
                    Path(input_path),
                    Path(output_dir),
                    job.options,
                    job.region_name,
                    job.region_folder,
                    feedback=feedback,
                )
            )
        return results

    def process(self, input_path, output_dir, options):
        results = self.process_outputs(input_path, output_dir, options)
        if not results:
            raise RuntimeError("No video outputs were produced.")
        return results[0]

    def available(self):
        return self.exporter.available()

    def load_settings(self, path):
        return self.settings.read(path)

    def save_settings(self, path, options, trims):
        return self.settings.write(path, options, trims)

    def prepare_session(self, path):
        return self.documents.allocate(path)

    def record_session(self, *args):
        return self.documents.write(*args)
