"""Prepare synchronized recording inputs and persist the calculated feature bundle."""

from dlc_gait_assembly.runway.manual.gait_analysis.business.synchronized.synchronized_analysis_engine import (
    calculate_synchronized_recording,
)


def generate_stroke_analysis_outputs(
    view_set, output_folder, settings, left_parameters, right_parameters, view_mappings, kinematics, pd, *, outputs
):
    merged = outputs.read_views(view_set, view_mappings)
    calculation = calculate_synchronized_recording(
        merged, view_set, settings, left_parameters, right_parameters, kinematics, pd
    )
    return outputs.write_synchronized(calculation, view_set, output_folder)
