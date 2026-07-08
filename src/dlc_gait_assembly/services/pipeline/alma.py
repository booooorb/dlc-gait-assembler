from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.services.imports import default_alma_root as _default_alma_root
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RUSTLAB1_PARAMETER_NAMES,
    extract_rustlab1_parameters,
)


AnalysisType = Literal["Treadmill", "Spontaneous walking"]
CalibrationMethod = Literal["reference", "manual"]
InputMode = Literal["Multi side view", "Single side view", "Three-view", "Single-side ALMA"]
ALMA_BODYPARTS = ("toe", "mtp", "ankle", "knee", "hip", "iliac crest")


@dataclass(frozen=True)
class AlmaSettings:
    input_mode: InputMode = "Multi side view"
    analysis_type: AnalysisType = "Treadmill"
    frame_rate: float = 120.0
    filter_cutoff: float = 6.0
    treadmill_speed_cm_s: float = 30.0
    calibration_method: CalibrationMethod = "reference"
    reference_segment: str = "ankle_toe"
    reference_length_cm: float = 1.5
    calibration_map_path: Path | None = None
    right_to_left: bool | str = False
    pixels_per_cm: float | None = None
    no_outlier_filter: bool = False
    dragging_filter: bool = False
    likelihood_threshold: float = 0.5
    drag_clearance_cm: float = 0.1
    drag_min_consecutive_frames: int = 4
    step_height_min_cm: float = 0.0
    step_height_max_cm: float = 2.0
    stride_length_min_cm: float = 0.0
    stride_length_max_cm: float = 8.0
    n_continuous_strides: int = 10
    generate_stickplot: bool = True
    generate_rustlab1_parameters: bool = True
    custom_bodypart_mapping: dict[str, str] | None = None
    view_bodypart_mapping: dict[str, object] | None = None


@dataclass(frozen=True)
class AlmaRunResult:
    input_file: Path
    output_files: tuple[Path, ...]
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class AlmaViewCsvSet:
    name: str
    left_csv: Path
    right_csv: Path
    bottom_csv: Path

    @property
    def alma_csv(self) -> Path:
        return self.left_csv


def default_alma_root(project_root: Path) -> Path:
    return _default_alma_root(project_root)


def load_alma_config_defaults(alma_root: Path) -> dict:
    config_path = alma_root / "config.yaml"
    if not config_path.exists():
        return {}

    try:
        import yaml
    except ModuleNotFoundError:
        return {}

    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.load(handle, Loader=yaml.FullLoader) or {}


def settings_from_alma_config(config: dict) -> AlmaSettings:
    right_to_left = config.get("right_to_left", False)
    if isinstance(right_to_left, str):
        if right_to_left.lower() == "auto":
            right_to_left = "auto"
        else:
            right_to_left = _coerce_bool(right_to_left)

    pixels_per_cm = config.get("pixels_per_cm", None)
    if pixels_per_cm == "":
        pixels_per_cm = None

    cm_speed = config.get("cm_speed", None)
    if cm_speed in (None, ""):
        cm_speed = 30.0

    reference_length_cm = config.get("reference_length_cm", 1.5)
    if reference_length_cm == "":
        reference_length_cm = 1.5

    auto_calibrate_spatial = _coerce_bool(config.get("auto_calibrate_spatial", True), default=True)
    likelihood_threshold = config.get("kinematics_likelihood_threshold", 0.5)
    if likelihood_threshold == "":
        likelihood_threshold = 0.5

    return AlmaSettings(
        frame_rate=float(config.get("frame_rate", 120.0)),
        filter_cutoff=float(config.get("lowpass_filter_cutoff", 6.0)),
        treadmill_speed_cm_s=float(cm_speed),
        calibration_method="reference" if auto_calibrate_spatial else "manual",
        reference_segment=str(config.get("reference_segment", "ankle_toe")),
        reference_length_cm=float(reference_length_cm),
        right_to_left=right_to_left,
        pixels_per_cm=None if pixels_per_cm is None else float(pixels_per_cm),
        no_outlier_filter=_coerce_bool(config.get("no_outlier_filter", False)),
        dragging_filter=_coerce_bool(config.get("dragging_filter", False)),
        likelihood_threshold=float(likelihood_threshold),
        drag_clearance_cm=float(config.get("drag_clearance_cm", 0.1)),
        drag_min_consecutive_frames=int(config.get("drag_min_consecutive_frames", 4)),
        step_height_min_cm=float(config.get("step_height_min_cm", 0.0)),
        step_height_max_cm=float(config.get("step_height_max_cm", 2.0)),
        stride_length_min_cm=float(config.get("stride_length_min_cm", 0.0)),
        stride_length_max_cm=float(config.get("stride_length_max_cm", 8.0)),
        generate_rustlab1_parameters=_coerce_bool(config.get("generate_rustlab1_parameters", True), default=True),
    )


def run_alma_gait_analysis(
    csv_files: list[Path | AlmaViewCsvSet],
    output_folder: Path,
    settings: AlmaSettings,
    alma_root: Path,
    progress_callback=None,
) -> list[AlmaRunResult]:
    external_python = _alma_compatible_python()
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
    kinematics = _load_kinematics_functions(alma_root)
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

    with tempfile.TemporaryDirectory(prefix="alma-pipeline-", dir=_temporary_dir()) as temp_dir:
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
        env.setdefault("MPLCONFIGDIR", str(_temporary_dir() / "matplotlib"))
        src_path = str(Path(__file__).resolve().parents[3])
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
        rustlab1_raw_dataframe = _merge_multiview_rustlab1_dataframe(csv_file, pd)
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
    dataframe, confidence_mask, confidence_messages = _filter_low_confidence_coordinates(
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
        coords = _hide_low_confidence_stickplot_frames(coords, confidence_mask)

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

            scale_text = "unknown scale" if rustlab1.pixels_per_cm is None else f"{rustlab1.pixels_per_cm:.3f} px/cm"
            messages.append(
                f"RustLab1: calculated {len(rustlab1.available_parameters)}/30 parameters at {scale_text} "
                f"({rustlab1.calibration_source})."
            )
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
    view_mappings = _view_mappings_for_set(settings, view_set.name)

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
        rustlab1_source = _merge_multiview_rustlab1_dataframe(
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

            scale_text = "unknown scale" if rustlab1.pixels_per_cm is None else f"{rustlab1.pixels_per_cm:.3f} px/cm"
            messages.append(
                f"RustLab1: calculated {len(rustlab1.available_parameters)}/30 parameters at {scale_text} "
                f"({rustlab1.calibration_source})."
            )
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
    side_mapping = _view_mapping_for(view_mappings, view) or settings.custom_bodypart_mapping
    dataframe, bodyparts, _bodyparts_raw = kinematics.fix_column_names(dataframe, side_mapping)
    dataframe, confidence_mask, confidence_messages = _filter_low_confidence_coordinates(
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
        coords = _hide_low_confidence_stickplot_frames(coords, confidence_mask)

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


def _merge_multiview_rustlab1_dataframe(view_set: AlmaViewCsvSet, pd, view_mappings: dict[str, dict[str, str]] | None = None):
    frames = []
    for view, path in (
        ("left", view_set.left_csv),
        ("right", view_set.right_csv),
        ("bottom", view_set.bottom_csv),
    ):
        frame = pd.read_csv(path, header=[1, 2])
        columns = []
        for column in frame.columns:
            if isinstance(column, tuple) and len(column) >= 2:
                marker, coord = column[0], column[1]
            else:
                parts = str(column).rsplit(" ", 1)
                marker, coord = (parts[0], parts[1]) if len(parts) == 2 else (column, "")
            columns.append((_rustlab1_marker_for_view(marker, view, view_mappings), str(coord).strip().lower()))
        frame = frame.copy()
        frame.columns = pd.MultiIndex.from_tuples(columns)
        frames.append(frame)
    return pd.concat(frames, axis=1)


def _rustlab1_marker_for_view(marker, view: str, view_mappings: dict[str, dict[str, str]] | None = None) -> str:
    key = _marker_key(marker)
    mapped = _view_mapping_for_marker(view_mappings, view, marker)
    if mapped:
        key = _marker_key(mapped)
    if key.startswith(("l-", "r-", "d-")):
        return key
    if view == "left":
        return _side_view_marker(key, "l")
    if view == "right":
        return _side_view_marker(key, "r")
    return _bottom_view_marker(key)


def _view_mappings_for_set(settings: AlmaSettings, set_name: str) -> dict[str, dict[str, str]] | None:
    mappings = settings.view_bodypart_mapping
    if not mappings:
        return None
    if _looks_like_view_mapping(mappings):
        return mappings
    candidate = mappings.get(set_name) if isinstance(mappings, dict) else None
    if isinstance(candidate, dict) and _looks_like_view_mapping(candidate):
        return candidate
    return None


def _looks_like_view_mapping(mapping: dict) -> bool:
    return any(view in mapping for view in ("left", "right", "bottom"))


def _view_mapping_for(view_mappings: dict[str, dict[str, str]] | None, view: str) -> dict[str, str] | None:
    if not view_mappings:
        return None
    mapping = view_mappings.get(view)
    return mapping if isinstance(mapping, dict) else None


def _view_mapping_for_marker(view_mappings: dict[str, dict[str, str]] | None, view: str, marker) -> str | None:
    if not view_mappings:
        return None
    mapping = view_mappings.get(view)
    if not mapping:
        return None
    marker_text = str(marker)
    if marker_text in mapping:
        return mapping[marker_text]
    normalized_marker = _marker_key(marker_text)
    for raw, standard in mapping.items():
        if _marker_key(raw) == normalized_marker:
            return standard
    return None


def _side_view_marker(marker: str, prefix: str) -> str:
    marker = _strip_view_prefix(marker)
    aliases = {
        "toe": "back-toe",
        "toe-tip": "back-toe",
        "back-toe-tip": "back-toe",
        "ankle": "back-ankle",
        "back-ankle": "back-ankle",
        "hip": "hip",
        "back-hip": "hip",
        "iliac-crest": "iliac-crest",
        "crest": "iliac-crest",
        "back-iliac-crest": "iliac-crest",
        "mtp": "back-mtp",
        "knee": "back-knee",
    }
    return f"{prefix}-{aliases.get(marker, marker)}"


def _bottom_view_marker(marker: str) -> str:
    marker = _strip_view_prefix(marker)
    aliases = {
        "center": "center-back",
        "centre": "center-back",
        "center-back": "center-back",
        "centre-back": "center-back",
        "back-center": "center-back",
        "back-centre": "center-back",
        "left": "back-left",
        "left-back": "back-left",
        "back-left": "back-left",
        "right": "back-right",
        "right-back": "back-right",
        "back-right": "back-right",
    }
    return f"d-{aliases.get(marker, marker)}"


def _strip_view_prefix(marker: str) -> str:
    for prefix in ("left-", "right-", "bottom-", "down-", "camera-left-", "camera-right-"):
        if marker.startswith(prefix):
            return marker[len(prefix):]
    return marker


def _marker_key(marker) -> str:
    key = str(marker).strip().lower().replace("_", "-").replace(" ", "-")
    while "--" in key:
        key = key.replace("--", "-")
    return key


def _filter_low_confidence_coordinates(dataframe, threshold: float, pd):
    threshold = float(threshold or 0.0)
    if threshold <= 0:
        return dataframe, None, ()

    bodypart_masks = {}
    for bodypart in ALMA_BODYPARTS:
        likelihood_column = f"{bodypart} likelihood"
        if likelihood_column not in dataframe.columns:
            continue
        likelihood = pd.to_numeric(dataframe[likelihood_column], errors="coerce")
        valid = likelihood.ge(threshold).fillna(False)
        if not bool(valid.any()):
            raise ValueError(
                f"Tracking confidence filter removed every {bodypart} point at likelihood cutoff {threshold:.2f}. "
                "Lower the cutoff, set it to 0, or check body-part mapping."
            )
        bodypart_masks[bodypart] = valid

    if not bodypart_masks:
        return dataframe, None, (
            "Tracking confidence filter skipped: no ALMA likelihood columns were found.",
        )

    valid_mask = pd.DataFrame(bodypart_masks, index=dataframe.index)
    low_confidence_count = int((~valid_mask).sum().sum())
    total_count = int(valid_mask.shape[0] * valid_mask.shape[1])
    if low_confidence_count == 0:
        return dataframe, valid_mask, (
            f"Tracking confidence filter: all frames met the {threshold:.2f} likelihood cutoff.",
        )

    filtered = dataframe.copy()
    filtered_any_coordinates = False
    for bodypart, valid in bodypart_masks.items():
        coordinate_columns = [
            column
            for column in (f"{bodypart} x", f"{bodypart} y")
            if column in filtered.columns
        ]
        if not coordinate_columns:
            continue
        filtered_any_coordinates = True
        filtered.loc[~valid, coordinate_columns] = float("nan")
        interpolated = (
            filtered.loc[:, coordinate_columns]
            .apply(pd.to_numeric, errors="coerce")
            .interpolate(method="linear", limit_direction="both")
        )
        if interpolated.isna().any().any():
            raise ValueError(
                f"Tracking confidence filter could not interpolate {bodypart} at cutoff {threshold:.2f}."
            )
        filtered.loc[:, coordinate_columns] = interpolated
    if not filtered_any_coordinates:
        return dataframe, valid_mask, (
            "Tracking confidence filter skipped: no ALMA x/y coordinate columns were found.",
        )

    message = (
        f"Tracking confidence filter: interpolated {low_confidence_count}/{total_count} "
        f"low-confidence marker sample(s) below {threshold:.2f} for parameter extraction "
        "and hid those marker positions from stickplots."
    )
    return filtered, valid_mask, (message,)


def _hide_low_confidence_stickplot_frames(coords, valid_mask):
    if len(coords) != len(valid_mask):
        return coords

    masked = coords.copy()
    for bodypart in valid_mask.columns:
        coordinate_columns = [
            column
            for column in (f"{bodypart} x", f"{bodypart} y")
            if column in masked.columns
        ]
        if coordinate_columns:
            masked.loc[~valid_mask[bodypart].to_numpy(), coordinate_columns] = float("nan")
    return masked


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


def _alma_compatible_python() -> Path | None:
    if os.environ.get("DLC_GAIT_ALMA_PIPELINE_CHILD") == "1":
        return None
    if _coerce_bool(os.environ.get("DLC_GAIT_DISABLE_ALMA_EXTERNAL_RUNTIME", False)):
        return None

    configured = os.environ.get("DLC_GAIT_ALMA_PYTHON")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).expanduser())

    candidates.extend(_conda_env_python_candidates())
    current = Path(sys.executable).resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved == current or not resolved.exists():
            continue
        if _has_alma_runtime_dependencies(resolved):
            return resolved
    return None


def _conda_env_python_candidates() -> list[Path]:
    candidates: list[Path] = []
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        envs_root = Path(conda_prefix).resolve().parent
        candidates.extend(
            [
                envs_root / "venv_python_3_10" / "bin" / "python",
                envs_root / "ALMA" / "bin" / "python",
                envs_root / "DEEPLABCUT" / "bin" / "python",
            ]
        )

    candidates.extend(
        [
            Path("/opt/miniconda3/envs/venv_python_3_10/bin/python"),
            Path("/opt/miniconda3/envs/ALMA/bin/python"),
            Path("/opt/miniconda3/envs/DEEPLABCUT/bin/python"),
        ]
    )
    return candidates


def _has_alma_runtime_dependencies(python_executable: Path) -> bool:
    probe = "import pandas, scipy, sklearn, matplotlib, numpy"
    try:
        completed = subprocess.run(
            [str(python_executable), "-c", probe],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _settings_to_json(settings: AlmaSettings) -> dict:
    payload = dict(settings.__dict__)
    if settings.calibration_map_path is not None:
        payload["calibration_map_path"] = str(settings.calibration_map_path)
    return payload


def _settings_from_json(payload: dict) -> AlmaSettings:
    if payload.get("calibration_map_path"):
        payload = {**payload, "calibration_map_path": Path(payload["calibration_map_path"])}
    return AlmaSettings(**payload)


def _temporary_dir() -> Path:
    for candidate in (Path("/private/tmp"), Path(tempfile.gettempdir())):
        if candidate.exists() and os.access(candidate, os.W_OK):
            return candidate
    return Path(tempfile.gettempdir())


def pixels_per_cm_from_calibration_map(map_path: Path, view_index: int | None = None) -> tuple[float, str]:
    payload = json.loads(Path(map_path).expanduser().read_text(encoding="utf-8"))
    conversion_map = payload.get("conversion_factor_map", payload)

    if view_index is not None:
        view = conversion_map.get("views", {}).get(str(view_index))
        value = _pixels_per_cm_from_conversion_node(view)
        if value is not None:
            return value, f"view {view_index}"

    overall_value = _pixels_per_cm_from_conversion_node(conversion_map.get("overall"))
    if overall_value is not None:
        return overall_value, "overall"

    for key, view in sorted(conversion_map.get("views", {}).items(), key=lambda item: int(item[0])):
        value = _pixels_per_cm_from_conversion_node(view)
        if value is not None:
            return value, f"view {key}"

    raise ValueError(f"Could not find a usable pixels-per-centimeter value in {map_path}")


def _pixels_per_cm_from_conversion_node(node: dict | None) -> float | None:
    if not node:
        return None

    for key in ("mean_pixels_per_centimeter", "pixels_per_centimeter"):
        value = node.get(key)
        if value:
            return float(value)

    centimeters_per_pixel = node.get("centimeters_per_pixel")
    if centimeters_per_pixel:
        return 1.0 / float(centimeters_per_pixel)

    axis_values = [
        node.get("recommended_x_centimeters_per_pixel"),
        node.get("recommended_y_centimeters_per_pixel"),
    ]
    axis_values = [float(value) for value in axis_values if value]
    if axis_values:
        return 1.0 / (sum(axis_values) / len(axis_values))

    return None


def _coerce_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "on"}:
            return True
        if lowered in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)


def _load_kinematics_functions(alma_root: Path):
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
        import pandas as pd
        import scipy  # noqa: F401
        import sklearn  # noqa: F401
        import numpy  # noqa: F401
        import matplotlib.pyplot as plt
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


def _main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--run-request":
        _run_request(Path(sys.argv[2]))
        return
    raise SystemExit("Usage: alma.py --run-request REQUEST_JSON")


if __name__ == "__main__":
    _main()
