from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dlc_gait_assembly.services.imports import default_alma_root as _default_alma_root
from dlc_gait_assembly.services.pipeline.rustlab1 import (
    RUSTLAB1_PARAMETER_NAMES,
    extract_rustlab1_parameters,
)


AnalysisType = Literal["Treadmill", "Spontaneous walking"]
CalibrationMethod = Literal["reference", "manual"]


@dataclass(frozen=True)
class AlmaSettings:
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


@dataclass(frozen=True)
class AlmaRunResult:
    input_file: Path
    output_files: tuple[Path, ...]
    messages: tuple[str, ...] = ()


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
        drag_clearance_cm=float(config.get("drag_clearance_cm", 0.1)),
        drag_min_consecutive_frames=int(config.get("drag_min_consecutive_frames", 4)),
        step_height_min_cm=float(config.get("step_height_min_cm", 0.0)),
        step_height_max_cm=float(config.get("step_height_max_cm", 2.0)),
        stride_length_min_cm=float(config.get("stride_length_min_cm", 0.0)),
        stride_length_max_cm=float(config.get("stride_length_max_cm", 8.0)),
        generate_rustlab1_parameters=_coerce_bool(config.get("generate_rustlab1_parameters", True), default=True),
    )


def run_alma_gait_analysis(
    csv_files: list[Path],
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
    csv_files: list[Path],
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
            progress_callback(index, total, f"Processing {csv_file.name}")

        result = _run_single_file(csv_file, output_folder, settings, kinematics, pd, plt)
        results.append(result)

    return results


def _run_alma_gait_analysis_external(
    csv_files: list[Path],
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
            "csv_files": [str(Path(path).expanduser().resolve()) for path in csv_files],
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


def _run_single_file(csv_file: Path, output_folder: Path, settings: AlmaSettings, kinematics, pd, plt) -> AlmaRunResult:
    raw_dataframe = pd.read_csv(csv_file, header=[1, 2])
    dataframe = raw_dataframe.copy()
    dataframe, bodyparts, _bodyparts_raw = kinematics.fix_column_names(dataframe, settings.custom_bodypart_mapping)

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
        )

    base_name = csv_file.stem
    output_files: list[Path] = []
    messages: list[str] = []

    parameters_path = output_folder / f"{base_name}_parameters.csv"
    parameters.to_csv(parameters_path, index=False)
    output_files.append(parameters_path)

    if settings.generate_rustlab1_parameters:
        rustlab1 = extract_rustlab1_parameters(raw_dataframe, parameters, settings, kinematics)
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

    return AlmaRunResult(input_file=csv_file, output_files=tuple(output_files), messages=tuple(messages))


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
    results = _run_alma_gait_analysis_in_process(
        [Path(path) for path in request["csv_files"]],
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
