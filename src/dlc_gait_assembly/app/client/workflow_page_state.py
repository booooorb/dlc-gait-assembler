"""Round-trip editable workflow state, keeping source files separate from settings."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QAbstractButton, QComboBox, QDoubleSpinBox, QLineEdit, QSpinBox

from dlc_gait_assembly.runway.manual.calibration.business.calibration_measurements import (
    CalibrationPoint,
    CalibrationStick,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.gait_coordinate_contracts import (
    AlmaViewCsvSet,
    StrokeStudyMetadata,
)
from dlc_gait_assembly.runway.manual.video_processing.business.video_enhancement_settings import EnhancementSettings
from dlc_gait_assembly.runway.manual.video_processing.business.video_processing_contracts import ProcessingOptions
from dlc_gait_assembly.runway.manual.video_processing.business.video_region_geometry import CropRegion, NormalizedRect
from dlc_gait_assembly.runway.manual.video_processing.business.video_trim_ranges import TrimRange

VALUE_TYPES = {cls.__name__: cls for cls in (
    CalibrationPoint, CalibrationStick, AlmaViewCsvSet, StrokeStudyMetadata, EnhancementSettings, ProcessingOptions,
    CropRegion, NormalizedRect, TrimRange,
)}
STATE_SETTINGS = {
    "gait_parameter_analysis": (
        "calibration_map_path", "calibration_map_source", "calibration_map_pixels_per_cm",
        "raw_bodyparts", "view_label_mappings",
    ),
    "knee_correction": ("calibration_map_path", "pixels_per_cm"),
    "manual_calibration": ("calibration_sticks_by_media", "timeline_ms_by_media"),
    "video_processing": ("trim_ranges_by_video", "active_trim_range_by_video"),
}
FILE_CONTROLS = {"csv_edit", "right_csv_edit", "video_edit", "right_video_edit"}
UI_ONLY_CONTROLS = {"crop_tool_button", "enhancements_tool_button", "trim_tool_button",
                    "x_tool_button", "y_tool_button", "cm_tool_button"}


def encode_value(value):
    if isinstance(value, Path):
        return {"$path": str(value)}
    if is_dataclass(value) and type(value).__name__ in VALUE_TYPES:
        return {"$type": type(value).__name__, "fields": {
            field.name: encode_value(getattr(value, field.name)) for field in fields(value)
        }}
    if isinstance(value, tuple):
        return {"$tuple": [encode_value(item) for item in value]}
    if isinstance(value, frozenset):
        return {"$frozenset": [encode_value(item) for item in sorted(value)]}
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ValueError(f"Unsupported workflow setting: {type(value).__name__}")


def decode_value(value):
    if isinstance(value, list):
        return [decode_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    if "$path" in value:
        return Path(value["$path"])
    if "$tuple" in value:
        return tuple(decode_value(item) for item in value["$tuple"])
    if "$frozenset" in value:
        return frozenset(decode_value(item) for item in value["$frozenset"])
    if "$type" in value:
        cls = VALUE_TYPES.get(value["$type"])
        if cls is None:
            raise ValueError("Unsupported workflow setting type.")
        return cls(**{key: decode_value(item) for key, item in value["fields"].items()})
    return {key: decode_value(item) for key, item in value.items()}


def page_view(page):
    return getattr(page, "kinematics_widget", page)


def _controls(view):
    """Use Python attribute names as stable keys, rather than translated labels or tree positions."""
    def walk(name, value):
        if isinstance(value, (QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit)):
            yield name, value
        elif isinstance(value, QAbstractButton) and value.isCheckable():
            yield name, value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield from walk(f"{name}/{key}", item)

    for name, value in vars(view).items():
        if name not in FILE_CONTROLS | UI_ONLY_CONTROLS:
            yield from walk(name, value)


def _control_value(control):
    if isinstance(control, (QSpinBox, QDoubleSpinBox)):
        return control.value()
    if isinstance(control, QComboBox):
        return {"text": control.currentText(), "data": encode_value(control.currentData())}
    if isinstance(control, QLineEdit):
        return control.text()
    return control.isChecked()


def _list_paths(widget):
    return [str(widget.item(index).data(Qt.UserRole) or widget.item(index).text()) for index in range(widget.count())]


def capture_page(tool_id, page):
    view = page_view(page)
    result = {"controls": {name: _control_value(control) for name, control in _controls(view)}}
    state = getattr(view, "state", None)
    result["data"] = encode_value({
        name: getattr(state, name) for name in STATE_SETTINGS.get(tool_id, ())
    })
    inputs = {}
    if tool_id == "gait_parameter_analysis":
        inputs = {"paths": view.state.selected_files, "pairings": view.state.manual_view_sets}
        result["data"]["view_calibration_sources"] = encode_value(view.view_calibration_sources)
        result["parameters"] = list(view.parameter_selection.enabled_parameter_names())
    elif tool_id == "video_processing":
        result["options"] = encode_value(view.controller._current_processing_options())
        inputs = {"paths": _list_paths(view.video_list), "current": view.state.current_video}
    elif tool_id == "manual_calibration":
        view.controller._save_media_state()
        result["data"] = encode_value({name: getattr(state, name) for name in STATE_SETTINGS[tool_id]})
        inputs = {"paths": _list_paths(view.media_list), "current": state.current_media}
    elif tool_id == "knee_correction":
        inputs = {"paths": state.selected_paths}
    elif tool_id == "pca_random_forest":
        inputs = {"paths": view._files}
    elif tool_id == "ladder_analysis":
        inputs = {name: getattr(state, name) for name in ("csv_path", "right_csv_path", "video_path", "right_video_path")}
        result["bodyparts"] = {
            name: [widget.item(i).text() for i in range(widget.count()) if widget.item(i).checkState() == Qt.Checked]
            for name in ("bodyparts_list", "right_bodyparts_list")
            for widget in (getattr(view, name),)
        }
    result["inputs"] = encode_value(inputs)
    return result


def _apply_controls(view, saved):
    controls = dict(_controls(view))
    blockers = [QSignalBlocker(control) for control in controls.values()]
    try:
        for name, value in saved.get("controls", {}).items():
            control = controls.get(name)
            if isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.setValue(value)
            elif isinstance(control, QComboBox):
                text = value.get("text", "") if isinstance(value, dict) else value
                item_data = decode_value(value.get("data")) if isinstance(value, dict) else None
                if control.findText(text) < 0 and item_data is not None:
                    control.addItem(text, item_data)
                if control.findText(text) >= 0 or control.isEditable():
                    control.setCurrentText(text)
            elif isinstance(control, QLineEdit):
                control.setText(value)
            elif isinstance(control, QAbstractButton):
                control.setChecked(value)
    finally:
        del blockers


def apply_page(tool_id, page, saved, *, restore_files):
    view = page_view(page)
    data = decode_value(saved.get("data", {}))
    for name in STATE_SETTINGS.get(tool_id, ()):
        if name in data:
            setattr(view.state, name, data[name])
    if tool_id == "gait_parameter_analysis":
        view.view_calibration_sources = data.get("view_calibration_sources", {})
        view.mapping._refresh_bodypart_mapping_choices()
    _apply_controls(view, saved)
    if tool_id == "gait_parameter_analysis":
        enabled = set(saved.get("parameters", view.parameter_selection.enabled_parameter_names()))
        with QSignalBlocker(view.parameter_selection.tree):
            for definition, item in view.parameter_selection._items:
                item.setCheckState(1, Qt.Checked if definition.name in enabled else Qt.Unchecked)
        view.setup._update_workflow()
        view.setup._update_input_mode()
        view.setup._update_analysis_mode()
        view.setup._update_limb_scope()
        view.calibration._update_calibration_method()
        view.mapping._update_mapping_enabled()
        view.view_timing_disclosure.set_expanded(any(
            spin.value() != 0 for spin in (*view.view_fps_spins.values(), *view.view_offset_spins.values())
        ))
    elif tool_id == "video_processing" and "options" in saved:
        options = decode_value(saved["options"])
        view.preview.set_crop_regions(options.crop_regions)
        view.preview.set_invert_regions(options.invert_rects)
        view.preview.set_enhancements(options.enhancements)
        view.settings_panel.refresh()
        view.trims._refresh_trim_context()
    elif tool_id == "manual_calibration":
        view.controller._update_calibration_results()
    elif tool_id == "ladder_analysis":
        from PySide6.QtWidgets import QListWidgetItem
        for name, markers in saved.get("bodyparts", {}).items():
            widget = getattr(view, name)
            for marker in markers:
                item = QListWidgetItem(marker)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                widget.addItem(item)
    if restore_files:
        _restore_inputs(tool_id, view, decode_value(saved.get("inputs", {})), saved)
        _apply_controls(view, saved)
    if hasattr(view.controller, "_update_run_state"):
        view.controller._update_run_state()
    if tool_id == "ladder_analysis":
        view.controller._update_mode()
        view.controller._update_method_controls()


def _existing_paths(paths):
    return [Path(path) for path in paths if Path(path).is_file()]


def _restore_inputs(tool_id, view, inputs, saved):
    paths = _existing_paths(inputs.get("paths", ()))
    if tool_id == "gait_parameter_analysis":
        view.inputs._add_csv_paths(paths)
        pairings = inputs.get("pairings")
        if pairings is not None:
            available = set(paths)
            view.state.manual_view_sets = [item for item in pairings if all(
                path in available for path in (item.left_csv, item.right_csv, item.bottom_csv)
            )]
            view.inputs._refresh_view_sets()
    elif tool_id == "video_processing":
        view.sources._add_video_paths(paths)
    elif tool_id == "manual_calibration":
        view.media_panel._add_media_paths(paths)
    elif tool_id == "knee_correction":
        view.inputs._add_paths(paths)
    elif tool_id == "pca_random_forest":
        view._files = paths
        view.file_list.addItems([str(path) for path in paths])
    elif tool_id == "ladder_analysis":
        _restore_ladder(view, inputs, saved)
    if tool_id in {"manual_calibration", "video_processing"}:
        widget = view.media_list if tool_id == "manual_calibration" else view.video_list
        for index in range(widget.count()):
            if widget.item(index).data(Qt.UserRole) == str(inputs.get("current", "")):
                widget.setCurrentRow(index)
                break


def _restore_ladder(view, inputs, saved):
    from PySide6.QtWidgets import QListWidgetItem

    for name in ("csv_path", "right_csv_path", "video_path", "right_video_path"):
        path = inputs.get(name)
        if path is None or not Path(path).is_file():
            continue
        setattr(view.state, name, Path(path))
        getattr(view, name.replace("_path", "_edit")).setText(str(path))
        if "csv" in name:
            widget = view.right_bodyparts_list if name.startswith("right") else view.bodyparts_list
            selected = set(saved.get("bodyparts", {}).get("right_bodyparts_list" if name.startswith("right") else "bodyparts_list", ()))
            widget.clear()
            for marker in view.use_cases.bodyparts(path):
                item = QListWidgetItem(marker)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if marker in selected else Qt.Unchecked)
                widget.addItem(item)
        else:
            camera = "right" if name.startswith("right") else "left" if view.controller._is_dual_mode() else "single"
            capture = view.media_access.open_video(path)
            setattr(view, "_right_video_capture" if camera == "right" else "_video_capture", capture)
            view.state.video_frame_counts[camera] = max(1, int(capture.info.frame_count))
            view.state.active_preview_view = camera
            view.frame_slider.setRange(0, view.state.video_frame_counts[camera] - 1)
            view.video_review._show_video_frame(0)


def has_previous_inputs(workspace_state):
    if workspace_state.get("automation_videos"):
        return True
    return any(bool(decode_value(page.get("inputs", {})).get("paths")) or any(
        decode_value(page.get("inputs", {})).get(name)
        for name in ("csv_path", "right_csv_path", "video_path", "right_video_path")
    ) for page in workspace_state.get("pages", {}).values())
