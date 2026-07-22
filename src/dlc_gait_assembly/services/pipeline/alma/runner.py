from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from dlc_gait_assembly.services.pipeline.alma.models import (
    AlmaRunResult,
    AlmaSettings,
    AlmaViewCsvSet,
)
from dlc_gait_assembly.services.pipeline.alma.multiview import (
    filter_low_confidence_coordinates,
    hide_low_confidence_stickplot_frames,
    merge_multiview_rustlab1_dataframe,
    view_mapping_for,
    view_mappings_for_set,
)
from dlc_gait_assembly.services.pipeline.runtime import (
    find_alma_python,
    temporary_directory_root,
)
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RUSTLAB1_PARAMETER_NAMES,
    extract_rustlab1_parameters,
    generate_rustlab1_figures,
)


def run_alma_gait_analysis(
    csv_files: list[Path | AlmaViewCsvSet],
    output_folder: Path,
    settings: AlmaSettings,
    alma_root: Path,
    progress_callback=None,
) -> list[AlmaRunResult]:
    external_python = find_alma_python()
    if external_python is not None:
        return _run_alma_gait_analysis_external(
            csv_files,
            output_folder,
            settings,
            alma_root,
            external_python,
            progress_callback,
        )

    return _run_alma_gait_analysis_in_process(csv_files, output_folder, settings, alma_root, progress_callback)


def _run_alma_gait_analysis_in_process(
    csv_files: list[Path | AlmaViewCsvSet],
    output_folder: Path,
    settings: AlmaSettings,
    alma_root: Path,
    progress_callback=None,
) -> list[AlmaRunResult]:
    pd, plt = _load_runtime_dependencies()
    kinematics = load_kinematics_functions(alma_root)
    output_folder.mkdir(parents=True, exist_ok=True)

    results: list[AlmaRunResult] = []
    total = max(1, len(csv_files))
    for index, csv_file in enumerate(csv_files, start=1):
        if progress_callback is not None:
            progress_callback(index, total, f"Processing {_alma_input_label(csv_file)}")

        result = _run_single_file(csv_file, output_folder, settings, kinematics, pd, plt)
        results.append(result)

    return results


def _run_alma_gait_analysis_external(
    csv_files: list[Path | AlmaViewCsvSet],
    output_folder: Path,
    settings: AlmaSettings,
    alma_root: Path,
    python_executable: Path,
    progress_callback=None,
) -> list[AlmaRunResult]:
    output_folder = Path(output_folder).expanduser().resolve()
    output_folder.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="alma-pipeline-", dir=temporary_directory_root()) as temp_dir:
        temp_path = Path(temp_dir)
        request_path = temp_path / "request.json"
        result_path = temp_path / "result.json"
        request = {
            "inputs": [_alma_input_to_json(item) for item in csv_files],
            "output_folder": str(output_folder),
            "alma_root": str(Path(alma_root).expanduser().resolve()),
            "settings": _settings_to_json(settings),
            "result_path": str(result_path),
        }
        request_path.write_text(json.dumps(request), encoding="utf-8")

        env = os.environ.copy()
        env["DLC_GAIT_ALMA_PIPELINE_CHILD"] = "1"
        env.setdefault("MPLCONFIGDIR", str(temporary_directory_root() / "matplotlib"))
        src_path = str(Path(__file__).resolve().parents[4])
        env["PYTHONPATH"] = src_path if not env.get("PYTHONPATH") else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"

        if progress_callback is not None:
            progress_callback(1, max(1, len(csv_files)), "Running ALMA-compatible pipeline")

        completed = subprocess.run(
            [str(python_executable), str(Path(__file__).resolve()), "--run-request", str(request_path)],
            cwd=str(Path(alma_root).expanduser().resolve()),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "ALMA-compatible pipeline failed.\n"
                f"Python: {python_executable}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        payload = json.loads(result_path.read_text(encoding="utf-8"))
        results = [
            AlmaRunResult(
                input_file=Path(item["input_file"]),
                output_files=tuple(Path(path) for path in item["output_files"]),
                messages=tuple(item.get("messages", ())),
            )
            for item in payload["results"]
        ]

        if progress_callback is not None:
            for index, result in enumerate(results, start=1):
                progress_callback(index, len(results), f"Processed {result.input_file.name}")
        return results


def _run_single_file(
    csv_file: Path | AlmaViewCsvSet,
    output_folder: Path,
    settings: AlmaSettings,
    kinematics,
    pd,
    plt,
) -> AlmaRunResult:
    if isinstance(csv_file, AlmaViewCsvSet) and not _is_single_side_input_mode(settings.input_mode):
        return _run_view_csv_set(csv_file, output_folder, settings, kinematics, pd, plt)

    rustlab1_raw_dataframe = None
    if isinstance(csv_file, AlmaViewCsvSet):
        input_file = csv_file.alma_csv
        base_name = csv_file.name
        rustlab1_raw_dataframe = merge_multiview_rustlab1_dataframe(csv_file, pd)
        view_messages = (
            "Multi-view CSV set: "
            f"left={csv_file.left_csv.name}, right={csv_file.right_csv.name}, bottom={csv_file.bottom_csv.name}.",
        )
    else:
        input_file = Path(csv_file)
        base_name = input_file.stem
        view_messages = ()

    raw_dataframe = pd.read_csv(input_file, header=[1, 2])
    dataframe = raw_dataframe.copy()
    dataframe, bodyparts, _bodyparts_raw = kinematics.fix_column_names(dataframe, settings.custom_bodypart_mapping)
    dataframe, confidence_mask, confidence_messages = filter_low_confidence_coordinates(
        dataframe,
        settings.likelihood_threshold,
        pd,
    )

    output_files: list[Path] = []
    messages: list[str] = [*view_messages, *confidence_messages]

    if settings.analysis_type == "Treadmill":
        parameters, coords, is_stance, bodyparts, drag_masks, starts = kinematics.extract_parameters(
            settings.frame_rate,
            dataframe,
            settings.filter_cutoff,
            "toe",
            cm_speed=settings.treadmill_speed_cm_s,
            right_to_left=settings.right_to_left,
            step_height_min_cm=settings.step_height_min_cm,
            step_height_max_cm=settings.step_height_max_cm,
            stride_length_min_cm=settings.stride_length_min_cm,
            stride_length_max_cm=settings.stride_length_max_cm,
            drag_clearance_cm=settings.drag_clearance_cm,
            drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
        )
    else:
        pixels_per_cm = settings.pixels_per_cm if settings.pixels_per_cm is not None else 49.143
        parameters, coords, is_stance, bodyparts, drag_masks, starts = kinematics.extract_spontaneous_parameters(
            settings.frame_rate,
            dataframe,
            settings.filter_cutoff,
            pixels_per_cm=pixels_per_cm,
            no_outlier_filter=settings.no_outlier_filter,
            dragging_filter=settings.dragging_filter,
            step_height_min_cm=settings.step_height_min_cm,
            step_height_max_cm=settings.step_height_max_cm,
            stride_length_min_cm=settings.stride_length_min_cm,
            stride_length_max_cm=settings.stride_length_max_cm,
            drag_clearance_cm=settings.drag_clearance_cm,
            drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
            right_to_left=settings.right_to_left,
        )

    if confidence_mask is not None and coords is not None:
        coords = hide_low_confidence_stickplot_frames(coords, confidence_mask)

    parameters_path = output_folder / f"{base_name}_parameters.csv"
    parameters.to_csv(parameters_path, index=False)
    output_files.append(parameters_path)

    if settings.generate_rustlab1_parameters:
        rustlab1_source = rustlab1_raw_dataframe if rustlab1_raw_dataframe is not None else raw_dataframe
        rustlab1 = extract_rustlab1_parameters(rustlab1_source, parameters, settings, kinematics)
        if rustlab1.dataframe is None:
            messages.append("RustLab1 output skipped: no left/right/down RustLab1 marker labels were detected.")
        else:
            rustlab1_path = output_folder / f"{base_name}_rustlab1_parameters.csv"
            rustlab1.dataframe.to_csv(rustlab1_path, index=False)
            output_files.append(rustlab1_path)

            merged_path = output_folder / f"{base_name}_expanded_parameters.csv"
            rustlab_features = rustlab1.dataframe.loc[:, list(RUSTLAB1_PARAMETER_NAMES)].reset_index(drop=True)
            merged = pd.concat([parameters.reset_index(drop=True), rustlab_features], axis=1)
            merged.to_csv(merged_path, index=False)
            output_files.append(merged_path)

            rustlab1_figure_paths = generate_rustlab1_figures(
                rustlab1_source,
                parameters,
                rustlab1,
                output_folder / f"{base_name}_rustlab1_figures",
                settings,
                kinematics,
                plt,
            )
            output_files.extend(rustlab1_figure_paths)

            scale_text = "unknown scale" if rustlab1.pixels_per_cm is None else f"{rustlab1.pixels_per_cm:.3f} px/cm"
            messages.append(
                f"RustLab1: calculated {len(rustlab1.available_parameters)}/30 parameters at {scale_text} "
                f"({rustlab1.calibration_source})."
            )
            messages.append(f"RustLab1: generated {len(rustlab1_figure_paths)}/18 runway figures.")
            if rustlab1.missing_markers:
                messages.append("RustLab1 missing markers: " + ", ".join(rustlab1.missing_markers))

    if coords is not None:
        coords_path = output_folder / f"{base_name}_coordinates.csv"
        coords.to_csv(coords_path, index=False)
        output_files.append(coords_path)

    if settings.generate_stickplot:
        stickplot_path = output_folder / f"{base_name}_stickplot.svg"
        try:
            kinematics.return_continuous(
                parameters,
                n_continuous=settings.n_continuous_strides,
                plot=True,
                pd_dataframe_coords=coords,
                bodyparts=bodyparts,
                is_stance=is_stance,
                filename=str(stickplot_path),
                drag_masks=drag_masks,
                starts=starts,
                drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
            )
            if stickplot_path.exists():
                output_files.append(stickplot_path)
        finally:
            if plt.get_fignums():
                plt.close("all")

    return AlmaRunResult(input_file=input_file, output_files=tuple(output_files), messages=tuple(messages))


def _run_view_csv_set(view_set: AlmaViewCsvSet, output_folder: Path, settings: AlmaSettings, kinematics, pd, plt) -> AlmaRunResult:
    output_files: list[Path] = []
    messages: list[str] = [
        "Multi-view CSV set: "
        f"left={view_set.left_csv.name}, right={view_set.right_csv.name}, bottom={view_set.bottom_csv.name}."
    ]
    view_mappings = view_mappings_for_set(settings, view_set.name)

    left_result = _extract_side_view_parameters(
        view_set.left_csv,
        f"{view_set.name}_left",
        "left",
        output_folder,
        settings,
        kinematics,
        pd,
        plt,
        view_mappings,
    )
    right_result = _extract_side_view_parameters(
        view_set.right_csv,
        f"{view_set.name}_right",
        "right",
        output_folder,
        settings,
        kinematics,
        pd,
        plt,
        view_mappings,
    )
    output_files.extend(left_result["output_files"])
    output_files.extend(right_result["output_files"])
    messages.extend(left_result["messages"])
    messages.extend(right_result["messages"])

    if settings.generate_rustlab1_parameters:
        rustlab1_source = merge_multiview_rustlab1_dataframe(
            view_set,
            pd,
            view_mappings,
        )
        rustlab1 = extract_rustlab1_parameters(
            rustlab1_source,
            left_result["parameters"],
            settings,
            kinematics,
        )
        if rustlab1.dataframe is None:
            messages.append("RustLab1 output skipped: no left/right/down RustLab1 marker labels were detected.")
            rustlab_features = pd.DataFrame(index=range(max(len(left_result["parameters"]), len(right_result["parameters"]))))
        else:
            rustlab1_path = output_folder / f"{view_set.name}_rustlab1_parameters.csv"
            rustlab1.dataframe.to_csv(rustlab1_path, index=False)
            output_files.append(rustlab1_path)
            rustlab_features = rustlab1.dataframe.loc[:, list(RUSTLAB1_PARAMETER_NAMES)].reset_index(drop=True)

            rustlab1_figure_paths = generate_rustlab1_figures(
                rustlab1_source,
                left_result["parameters"],
                rustlab1,
                output_folder / f"{view_set.name}_rustlab1_figures",
                settings,
                kinematics,
                plt,
            )
            output_files.extend(rustlab1_figure_paths)

            scale_text = "unknown scale" if rustlab1.pixels_per_cm is None else f"{rustlab1.pixels_per_cm:.3f} px/cm"
            messages.append(
                f"RustLab1: calculated {len(rustlab1.available_parameters)}/30 parameters at {scale_text} "
                f"({rustlab1.calibration_source})."
            )
            messages.append(f"RustLab1: generated {len(rustlab1_figure_paths)}/18 runway figures.")
            if rustlab1.missing_markers:
                messages.append("RustLab1 missing markers: " + ", ".join(rustlab1.missing_markers))
    else:
        rustlab_features = pd.DataFrame(index=range(max(len(left_result["parameters"]), len(right_result["parameters"]))))

    expanded = pd.concat(
        [
            left_result["parameters"].reset_index(drop=True).add_prefix("left__"),
            right_result["parameters"].reset_index(drop=True).add_prefix("right__"),
            rustlab_features,
        ],
        axis=1,
    )
    expanded_path = output_folder / f"{view_set.name}_expanded_parameters.csv"
    expanded.to_csv(expanded_path, index=False)
    output_files.append(expanded_path)

    combined_path = output_folder / f"{view_set.name}_parameters.csv"
    expanded.to_csv(combined_path, index=False)
    output_files.append(combined_path)

    return AlmaRunResult(input_file=view_set.left_csv, output_files=tuple(output_files), messages=tuple(messages))


def _extract_side_view_parameters(
    csv_file: Path,
    base_name: str,
    view: str,
    output_folder: Path,
    settings: AlmaSettings,
    kinematics,
    pd,
    plt,
    view_mappings: dict[str, dict[str, str]] | None = None,
) -> dict:
    raw_dataframe = pd.read_csv(csv_file, header=[1, 2])
    dataframe = raw_dataframe.copy()
    side_mapping = view_mapping_for(view_mappings, view) or settings.custom_bodypart_mapping
    dataframe, bodyparts, _bodyparts_raw = kinematics.fix_column_names(dataframe, side_mapping)
    dataframe, confidence_mask, confidence_messages = filter_low_confidence_coordinates(
        dataframe,
        settings.likelihood_threshold,
        pd,
    )

    if settings.analysis_type == "Treadmill":
        parameters, coords, is_stance, bodyparts, drag_masks, starts = kinematics.extract_parameters(
            settings.frame_rate,
            dataframe,
            settings.filter_cutoff,
            "toe",
            cm_speed=settings.treadmill_speed_cm_s,
            right_to_left=settings.right_to_left,
            step_height_min_cm=settings.step_height_min_cm,
            step_height_max_cm=settings.step_height_max_cm,
            stride_length_min_cm=settings.stride_length_min_cm,
            stride_length_max_cm=settings.stride_length_max_cm,
            drag_clearance_cm=settings.drag_clearance_cm,
            drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
        )
    else:
        pixels_per_cm = settings.pixels_per_cm if settings.pixels_per_cm is not None else 49.143
        parameters, coords, is_stance, bodyparts, drag_masks, starts = kinematics.extract_spontaneous_parameters(
            settings.frame_rate,
            dataframe,
            settings.filter_cutoff,
            pixels_per_cm=pixels_per_cm,
            no_outlier_filter=settings.no_outlier_filter,
            dragging_filter=settings.dragging_filter,
            step_height_min_cm=settings.step_height_min_cm,
            step_height_max_cm=settings.step_height_max_cm,
            stride_length_min_cm=settings.stride_length_min_cm,
            stride_length_max_cm=settings.stride_length_max_cm,
            drag_clearance_cm=settings.drag_clearance_cm,
            drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
            right_to_left=settings.right_to_left,
        )

    if confidence_mask is not None and coords is not None:
        coords = hide_low_confidence_stickplot_frames(coords, confidence_mask)

    output_files: list[Path] = []
    parameters_path = output_folder / f"{base_name}_parameters.csv"
    parameters.to_csv(parameters_path, index=False)
    output_files.append(parameters_path)

    if coords is not None:
        coords_path = output_folder / f"{base_name}_coordinates.csv"
        coords.to_csv(coords_path, index=False)
        output_files.append(coords_path)

    if settings.generate_stickplot:
        stickplot_path = output_folder / f"{base_name}_stickplot.svg"
        try:
            kinematics.return_continuous(
                parameters,
                n_continuous=settings.n_continuous_strides,
                plot=True,
                pd_dataframe_coords=coords,
                bodyparts=bodyparts,
                is_stance=is_stance,
                filename=str(stickplot_path),
                drag_masks=drag_masks,
                starts=starts,
                drag_min_consecutive_frames=settings.drag_min_consecutive_frames,
            )
            if stickplot_path.exists():
                output_files.append(stickplot_path)
        finally:
            if plt.get_fignums():
                plt.close("all")

    messages = [f"{view.title()} ALMA view: {csv_file.name}.", *confidence_messages]
    return {
        "parameters": parameters,
        "raw_dataframe": raw_dataframe,
        "output_files": output_files,
        "messages": messages,
    }


def _alma_input_label(item: Path | AlmaViewCsvSet) -> str:
    if isinstance(item, AlmaViewCsvSet):
        return item.name
    return Path(item).name


def _alma_input_to_json(item: Path | AlmaViewCsvSet) -> dict:
    if isinstance(item, AlmaViewCsvSet):
        return {
            "kind": "multiview",
            "name": item.name,
            "left_csv": str(Path(item.left_csv).expanduser().resolve()),
            "right_csv": str(Path(item.right_csv).expanduser().resolve()),
            "bottom_csv": str(Path(item.bottom_csv).expanduser().resolve()),
        }
    return {"kind": "single", "csv_file": str(Path(item).expanduser().resolve())}


def _alma_input_from_json(payload) -> Path | AlmaViewCsvSet:
    if isinstance(payload, str):
        return Path(payload)
    if payload.get("kind") == "multiview":
        return AlmaViewCsvSet(
            name=str(payload["name"]),
            left_csv=Path(payload["left_csv"]),
            right_csv=Path(payload["right_csv"]),
            bottom_csv=Path(payload["bottom_csv"]),
        )
    return Path(payload["csv_file"])


def _is_single_side_input_mode(input_mode: str) -> bool:
    return input_mode in {"Single side view", "Single-side ALMA"}


def _settings_to_json(settings: AlmaSettings) -> dict:
    payload = dict(settings.__dict__)
    if settings.calibration_map_path is not None:
        payload["calibration_map_path"] = str(settings.calibration_map_path)
    return payload


def _settings_from_json(payload: dict) -> AlmaSettings:
    if payload.get("calibration_map_path"):
        payload = {**payload, "calibration_map_path": Path(payload["calibration_map_path"])}
    return AlmaSettings(**payload)


def load_kinematics_functions(alma_root: Path):
    module_path = alma_root / "Functions" / "KinematicsFunctions.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Could not find ALMA KinematicsFunctions.py at {module_path}")

    import matplotlib

    matplotlib.use("Agg", force=True)
    spec = importlib.util.spec_from_file_location("alma_kinematics_functions", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load ALMA KinematicsFunctions.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runtime_dependencies():
    try:
        import matplotlib.pyplot as plt
        import numpy  # noqa: F401
        import pandas as pd
        import scipy  # noqa: F401
        import sklearn  # noqa: F401
    except ModuleNotFoundError as exc:
        missing = exc.name or "a required package"
        raise ModuleNotFoundError(
            f"ALMA gait analysis requires {missing}. Install or activate the ALMA environment before running the pipeline."
        ) from exc
    return pd, plt


def _run_request(request_path: Path) -> None:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    inputs = request.get("inputs")
    if inputs is None:
        inputs = request["csv_files"]
    results = _run_alma_gait_analysis_in_process(
        [_alma_input_from_json(item) for item in inputs],
        Path(request["output_folder"]),
        _settings_from_json(request["settings"]),
        Path(request["alma_root"]),
    )
    payload = {
        "results": [
            {
                "input_file": str(result.input_file),
                "output_files": [str(path) for path in result.output_files],
                "messages": list(result.messages),
            }
            for result in results
        ]
    }
    Path(request["result_path"]).write_text(json.dumps(payload), encoding="utf-8")


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-request":
        _run_request(Path(sys.argv[2]))
        return
    raise SystemExit("Usage: python -m dlc_gait_assembly.services.pipeline.alma --run-request REQUEST_JSON")


if __name__ == "__main__":
    main()
