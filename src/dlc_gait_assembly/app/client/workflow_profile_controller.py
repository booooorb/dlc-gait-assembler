"""Own the saved workflow shared by manual tools and automation."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.client.workflow_page_state import apply_page, capture_page, has_previous_inputs, page_view
from dlc_gait_assembly.runway.automatic.profiles.business.automatic_profile_from_manual import (
    ManualProfileSnapshot,
    combine_manual_snapshots,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon


class _WorkflowRowDelegate(QStyledItemDelegate):
    """Keep native selection and focus behind the two-line workflow row."""

    def initStyleOption(self, option: QStyleOptionViewItem, index):
        super().initStyleOption(option, index)
        option.text = ""


class _WorkflowPicker(QWidget):
    resized = Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resized.emit()


class _WorkflowList(QListWidget):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            item = self.currentItem()
            if item is not None and not item.isHidden():
                self.itemActivated.emit(item)
            event.accept()
            return
        super().keyPressEvent(event)


class WorkflowProfileController:
    def __init__(self, window):
        self.window = window
        self.automatic = window._main_menu.automated_profiles
        self.automatic.workflow_controller = self
        self.use_cases = self.automatic.profile_use_cases
        self.active = None
        self.workspace_state = {"version": 1, "pages": {}}
        self.restore_files = False
        self.pending_route = None
        self.saved_snapshot = ""
        self.loading = False
        self._build_bar()
        self._build_picker()
        self.refresh_profiles()
        self.timer = QTimer(window)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh_dirty_state)
        self.timer.start()
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, window)
        self.save_shortcut.activated.connect(self.save)
        self.automatic.profiles_changed.connect(self._automatic_saved)
        self._simplify_automation()

    def _simplify_automation(self):
        for frame in self.automatic.findChildren(QFrame):
            if frame.objectName() == "ProfileManagementPanel":
                frame.hide()
        self.automatic.profile_selector.hide()
        self.automatic.save_profile_button.hide()
        for label in self.automatic._automation_header.findChildren(QLabel):
            if label.text() == "Profile":
                label.hide()
        for name in ("manifest_upload_button", "calibration_upload_button", "analysis_manifest_upload_button", "knee_manifest_upload_button"):
            getattr(self.automatic, name).hide()
        self.automatic.open_profile_configuration_button.setText("Automation settings")
        for name, text, tooltip in (
            ("open_video_settings_button", "Video settings", "Edit video regions, trimming and enhancements, then save the workflow."),
            ("open_calibration_settings_button", "Calibration", "Edit the calibration used by this workflow."),
            ("open_gait_settings_button", "Gait settings", "Edit gait analysis settings, then save the workflow."),
            ("open_knee_settings_button", "Knee settings", "Edit knee correction settings, then save the workflow."),
        ):
            button = getattr(self.automatic, name)
            button.setText(text)
            button.setToolTip(tooltip)
        for label in self.automatic.findChildren(QLabel):
            replacements = {
                "Manage automated profiles": "Automation settings",
                "Gait analysis manifest": "Gait settings",
                "Knee analysis manifest": "Knee settings",
            }
            if label.text() in replacements:
                label.setText(replacements[label.text()])

    def _build_bar(self):
        self.bar = QFrame()
        self.bar.setObjectName("WorkflowProfileBar")
        self.bar.setAccessibleName("Saved workflow profile")
        layout = QHBoxLayout(self.bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.selector = QComboBox()
        self.selector.setAccessibleName("Active workflow profile")
        self.selector.setFixedWidth(180)
        self.selector.currentIndexChanged.connect(self._selected)
        layout.addWidget(self.selector)
        self.status = QLabel("Open or create a workflow to begin", self.bar)
        self.status.setObjectName("MutedLabel")
        self.status.hide()
        self.new_button = QPushButton()
        self.new_button.setAccessibleName("New workflow")
        self.new_button.setToolTip("Create a new workflow")
        self.new_button.clicked.connect(self.new)
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.setFixedWidth(80)
        self.save_button.setToolTip("Save all workflow settings and current file selections (Ctrl+S).")
        self.save_button.clicked.connect(self.save)
        self.save_as_button = QPushButton()
        self.save_as_button.setAccessibleName("Save workflow as")
        self.save_as_button.setToolTip("Save as a separate workflow")
        self.save_as_button.clicked.connect(self.save_as)
        self.close_button = QPushButton("×")
        self.close_button.setAccessibleName("Close workflow")
        self.close_button.setToolTip("Close the active workflow")
        self.close_button.clicked.connect(self.close_profile)
        for button in (self.save_button, self.new_button, self.save_as_button, self.close_button):
            layout.addWidget(button)
        for button in (self.new_button, self.save_as_button, self.close_button):
            button.setFixedWidth(30)
        self.apply_bar_theme()

    def apply_bar_theme(self):
        self.new_button.setIcon(interface_icon("plus", theme.TEXT))
        self.save_button.setIcon(interface_icon("download", theme.PRIMARY_TEXT, size=16))
        self.save_as_button.setIcon(interface_icon("copy", theme.TEXT))

    def _set_status(self, message):
        self.status.setText(message)
        name = self.active.name if self.active else "No workflow selected"
        self.selector.setToolTip(f"Profile: {name}\n{message}")
        self.save_button.setAccessibleDescription(message)

    def _build_picker(self):
        self.picker = _WorkflowPicker()
        self.picker.setObjectName("WorkflowPicker")
        self.picker.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self.picker)
        outer.setContentsMargins(48, 32, 48, 28)
        outer.setSpacing(0)
        content = QWidget()
        content.setMinimumWidth(860)
        content.setMaximumWidth(960)
        body = QVBoxLayout(content)
        self._picker_body = body
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(16)
        heading = QHBoxLayout()
        title = QLabel("Workflows")
        title.setObjectName("WorkflowPickerTitle")
        heading.addWidget(title, 1)
        self.new_profile_button = QPushButton("New workflow…")
        self.new_profile_button.setMinimumHeight(40)
        self.new_profile_button.clicked.connect(self.new)
        heading.addWidget(self.new_profile_button)
        body.addLayout(heading)
        self.profile_search = QLineEdit()
        self.profile_search.setPlaceholderText("Search workflows…")
        self.profile_search.setAccessibleName("Search saved workflows")
        self.profile_search.setClearButtonEnabled(True)
        self.profile_search.setMinimumHeight(40)
        self.profile_search.textChanged.connect(self._filter_profiles)
        body.addWidget(self.profile_search)
        self.profile_list = _WorkflowList()
        self.profile_list.setAccessibleName("Saved workflows")
        self.profile_list.setItemDelegate(_WorkflowRowDelegate(self.profile_list))
        self.profile_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.profile_list.itemActivated.connect(lambda item: self.open_profile(item.data(Qt.UserRole)))
        body.addWidget(self.profile_list)
        self.empty_label = QLabel()
        self.empty_label.setObjectName("WorkflowEmptyState")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignCenter)
        body.addWidget(self.empty_label)
        actions = QWidget()
        row = QHBoxLayout(actions)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("PrimaryButton")
        self.open_button.clicked.connect(self._open_selected)
        self.rename_button = QPushButton("Rename…")
        self.rename_button.clicked.connect(self.rename_selected)
        self.delete_button = QPushButton("Delete workflow…")
        self.delete_button.setObjectName("DeleteButton")
        self.delete_button.clicked.connect(self.delete_selected)
        self.profile_list.itemSelectionChanged.connect(self._sync_picker_actions)
        row.addWidget(self.rename_button)
        row.addWidget(self.delete_button)
        row.addStretch()
        row.addWidget(self.open_button)
        for button in (self.rename_button, self.delete_button, self.open_button):
            button.setMinimumHeight(38)
        body.addWidget(actions)
        outer.addWidget(content, 0, Qt.AlignTop | Qt.AlignHCenter)
        outer.addStretch(1)
        self.picker.resized.connect(self._resize_profile_list)
        self.window._stack.addWidget(self.picker)

    def refresh_profiles(self):
        from PySide6.QtWidgets import QListWidgetItem

        profiles = self.use_cases.list_profiles()
        blocker = QSignalBlocker(self.selector)
        self.selector.clear()
        self.selector.addItem("No profile", None)
        self.profile_list.clear()
        for profile in profiles:
            self.selector.addItem(profile.name, profile.id)
            item = QListWidgetItem(profile.name)
            item.setData(Qt.UserRole, profile.id)
            item.setSizeHint(QSize(0, 52))
            self.profile_list.addItem(item)
            row = QWidget()
            row.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(20, 12, 20, 12)
            title = QLabel(profile.name)
            title.setObjectName("WorkflowRowTitle")
            layout.addWidget(title, 1)
            self.profile_list.setItemWidget(item, row)
        self.selector.setCurrentIndex(max(0, self.selector.findData(self.active.id if self.active else None)))
        self.selector.model().item(0).setEnabled(self.active is None)
        del blocker
        self.profile_search.setVisible(bool(profiles))
        self._filter_profiles()
        self.open_button.setEnabled(False)
        self._sync_picker_actions()
        for button in (self.save_button, self.save_as_button, self.close_button):
            button.setEnabled(self.active is not None)

    def _sync_picker_actions(self):
        item = self.profile_list.currentItem()
        selected = item is not None and item.isSelected() and not item.isHidden()
        self.open_button.setEnabled(selected)
        editable = selected and (self.active is None or item.data(Qt.UserRole) != self.active.id)
        self.rename_button.setEnabled(editable)
        self.delete_button.setEnabled(editable)

    def _filter_profiles(self):
        query = self.profile_search.text().strip().casefold()
        visible = 0
        for index in range(self.profile_list.count()):
            item = self.profile_list.item(index)
            item.setHidden(query not in item.text().casefold())
            visible += not item.isHidden()
        self.profile_list.setVisible(bool(visible))
        self.empty_label.setText("No matches" if self.profile_list.count() else "No saved workflows")
        self.empty_label.setVisible(not visible)
        self._resize_profile_list()
        self._sync_picker_actions()

    def _resize_profile_list(self):
        body = self._picker_body
        items = [body.itemAt(index) for index in range(body.count())
                 if not body.itemAt(index).isEmpty()]
        other_height = sum(item.sizeHint().height() for item in items if item.widget() is not self.profile_list)
        margins = self.picker.layout().contentsMargins()
        available = self.picker.height() - margins.top() - margins.bottom() - other_height
        available -= max(0, len(items) - 1) * body.spacing()
        visible = sum(not self.profile_list.item(index).isHidden() for index in range(self.profile_list.count()))
        self.profile_list.setFixedHeight(max(60, min(360, visible * 52 + 14, available)))

    def rename_selected(self, _checked=False):
        item = self.profile_list.currentItem()
        if item is None or not self.rename_button.isEnabled():
            return
        profile_id = item.data(Qt.UserRole)
        name, accepted = QInputDialog.getText(self.window, "Rename workflow", "Workflow name:", text=item.text())
        if not accepted or not name.strip():
            return
        try:
            self.use_cases.rename(profile_id, name.strip())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.window, "Could not rename workflow", str(exc))
            return
        if self.active is None:
            self.automatic.profiles._refresh_profiles()
        self.refresh_profiles()

    def delete_selected(self, _checked=False):
        item = self.profile_list.currentItem()
        if item is None or not self.delete_button.isEnabled():
            return
        if QMessageBox.question(self.window, "Delete workflow?",
            f'Delete “{item.text()}” and its saved settings and model copies? Source videos and CSVs stay on disk.',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel) != QMessageBox.Yes:
            return
        try:
            self.use_cases.delete(item.data(Qt.UserRole))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.window, "Could not delete workflow", str(exc))
            return
        if self.active is None:
            self.automatic.profiles._refresh_profiles()
        self.refresh_profiles()

    def ensure_profile(self, route):
        if self.active is not None:
            return True
        self.show_picker(route)
        return False

    def show_picker(self, route=None):
        self.pending_route = route
        self.profile_search.clear()
        self.refresh_profiles()
        self.window._active_tool = None
        self.window.navigation.tool_id = None
        self.window.navigation.automatic_active = False
        self.window.navigation.home_active = True
        self.window.animations._set_manual_pipeline_expanded(False)
        self.window._stack.setCurrentWidget(self.picker)
        self.window.setWindowTitle("DLC Gait Assembler - Load profile")
        self.window.routes._refresh_stage_navigation()
        if self.active is None:
            self._set_status("Open or create a workflow to begin")

    def _selected(self, index):
        profile_id = self.selector.itemData(index)
        if profile_id and (self.active is None or profile_id != self.active.id):
            if not self.open_profile(profile_id):
                blocker = QSignalBlocker(self.selector)
                self.selector.setCurrentIndex(max(0, self.selector.findData(self.active.id if self.active else None)))
                del blocker

    def _open_selected(self):
        item = self.profile_list.currentItem()
        if item is not None and self.open_button.isEnabled():
            self.open_profile(item.data(Qt.UserRole))

    def new(self, _checked=False, *, name=None):
        if not self._can_switch():
            return False
        if name is None:
            name, accepted = QInputDialog.getText(self.window, "New profile", "Profile name:")
            if not accepted:
                return False
        if not name.strip():
            return False
        try:
            profile = self.use_cases.save(name.strip(), None, None, {}, allow_incomplete=True,
                gait_analysis_enabled=True, workspace_state={"version": 1, "pages": {}})
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.window, "Could not create workflow", str(exc))
            return False
        self._activate(profile, restore_files=False)
        return True

    def open_profile(self, profile_id, *, restore_files=None):
        if not self._can_switch():
            return False
        try:
            profile = self.use_cases.load(profile_id)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self.window, "Could not open workflow", str(exc))
            return False
        if restore_files is None and has_previous_inputs(profile.workspace_state):
            dialog = QMessageBox(self.window)
            dialog.setWindowTitle("Reopen workflow")
            dialog.setText(f'Restore the videos and CSVs from “{profile.name}”?')
            dialog.setInformativeText("Settings are loaded with either choice. Missing files will be skipped.")
            restore = dialog.addButton("Restore files", QMessageBox.ButtonRole.AcceptRole)
            settings_only = dialog.addButton("Settings only", QMessageBox.ButtonRole.ActionRole)
            dialog.addButton(QMessageBox.StandardButton.Cancel)
            dialog.setDefaultButton(restore)
            dialog.exec()
            if dialog.clickedButton() not in (restore, settings_only):
                return False
            restore_files = dialog.clickedButton() == restore
        self._activate(profile, restore_files=bool(restore_files))
        return True

    def _activate(self, profile, *, restore_files):
        route = self.pending_route if self.window._stack.currentWidget() is self.picker else None
        self.loading = True
        try:
            self._release_pages()
            self.active = profile
            self.workspace_state = json.loads(json.dumps(profile.workspace_state or {"version": 1, "pages": {}}))
            self.workspace_state.setdefault("pages", {})
            self.restore_files = restore_files
            self.automatic.profiles._refresh_profiles(profile.id)
            self.automatic._video_paths.clear()
            self.automatic.video_list.clear()
            if restore_files:
                self.automatic.queue._add_video_paths([
                    Path(path) for path in self.workspace_state.get("automation_videos", ()) if Path(path).is_file()
                ])
            self.automatic.profile_state.saved_snapshot = self.automatic.profiles._snapshot()
            self.refresh_profiles()
            self.saved_snapshot = self._snapshot()
            self._set_status("Saved")
        finally:
            self.loading = False
        self.pending_route = None
        if route is not None:
            route()
        else:
            previous = self.workspace_state.get("route")
            tool_ids = {spec.id for spec in (*self.window._tool_specs, self.window._ladder_spec) if spec.enabled}
            if previous in tool_ids:
                self.window.routes._open_tool(previous)
            elif previous == "automation":
                self.window.routes._show_automated_pipeline()
            elif previous == "automation_settings":
                self.window.routes._show_automated_profiles()
            else:
                self.window.routes._open_manual_workspace()

    def attach_page(self, tool_id, page):
        saved = self.workspace_state.get("pages", {}).get(tool_id)
        if saved:
            apply_page(tool_id, page, saved, restore_files=self.restore_files)
        else:
            self._apply_legacy_settings(tool_id, page)
        self._apply_profile_calibration(tool_id, page)
        self._replace_manifest_controls(page)
        # Creating a page and applying saved settings is not an edit.
        self.workspace_state["pages"][tool_id] = capture_page(tool_id, page)
        baseline = json.loads(self.saved_snapshot)
        baseline[0].setdefault("pages", {})[tool_id] = self.workspace_state["pages"][tool_id]
        self.saved_snapshot = json.dumps(baseline, sort_keys=True, allow_nan=False)
        if tool_id == "manual_calibration":
            page.save_to_gait_requested.connect(self._save_calibration_to_gait)

    def _save_calibration_to_gait(self):
        gait_id = "gait_parameter_analysis"
        self.window.routes._open_tool(gait_id)
        if self.window.navigation.tool_id == gait_id:
            self.save(send_calibration_to_gait=True)

    def _apply_profile_calibration(self, tool_id, page):
        view = page_view(page)
        if self.active.calibration_map is None:
            return
        if tool_id == "knee_correction":
            view.controller._set_calibration_map(self.active.calibration_map)
        elif tool_id == "gait_parameter_analysis":
            view.state.calibration_map_path = self.active.calibration_map
            scale, source = view.analysis.settings.calibration_scale(self.active.calibration_map)
            view.state.calibration_map_pixels_per_cm = scale
            view.state.calibration_map_source = source
            view.calibration_map_label.setText(f"Profile calibration: {scale:g} px/cm")

    def _apply_legacy_settings(self, tool_id, page):
        """Existing automation profiles open in the same manual settings pages."""
        view = page_view(page)
        if tool_id == "gait_parameter_analysis" and self.active.analysis_manifest:
            view.apply_profile_settings(view.analysis.settings.load_settings(self.active.analysis_manifest))
        elif tool_id == "video_processing" and self.active.processing_manifest:
            options, trims = view.use_cases.load_settings(self.active.processing_manifest)
            view.preview.set_crop_regions(options.crop_regions)
            view.preview.set_invert_regions(options.invert_rects)
            view.preview.set_enhancements(options.enhancements)
            view.crf_spin.setValue(options.crf)
            view.preset_combo.setCurrentText(options.preset)
            view.trims._apply_imported_trim_ranges(trims)
            view.settings_panel.refresh()
        elif tool_id == "knee_correction" and self.active.knee_manifest:
            settings = self.use_cases.inspect_knee_settings(self.active.knee_manifest)
            view.hip_knee_length.setValue(settings.hip_knee_length_cm)
            view.knee_ankle_length.setValue(settings.knee_ankle_length_cm)
            view.likelihood_threshold.setValue(settings.likelihood_threshold)
            view.generated_knee_label_edit.setText(settings.output_knee_bodypart)
            view.knee_direction_combo.setCurrentIndex(view.knee_direction_combo.findData(settings.knee_direction))
            view.state.pixels_per_cm = settings.pixels_per_cm
            for combo, label in (
                (view.knee_label_combo, settings.knee_bodyparts[0] if settings.knee_bodyparts else None),
                (view.hip_label_combo, settings.hip_bodypart), (view.ankle_label_combo, settings.ankle_bodypart),
            ):
                if label is not None:
                    combo.addItem(label, label)
                    combo.setCurrentIndex(combo.count() - 1)

    def _replace_manifest_controls(self, page):
        view = page_view(page)
        view.setProperty("workflowProfileManaged", True)
        for name in ("import_manifest_button", "export_manifest_button", "import_video_manifest_button", "export_video_manifest_button"):
            button = getattr(view, name, None)
            if button is not None:
                button.hide()
        # The old per-tool export shortcut now saves the current workflow as well.
        for shortcut in getattr(view, "_shortcuts", ()):
            if shortcut.key().toString() == "Ctrl+Shift+E":
                shortcut.setEnabled(False)
        box = getattr(view, "saved_settings_box", None)
        if box is not None:
            box.hide()

    def _capture(self):
        state = json.loads(json.dumps(self.workspace_state))
        for tool_id, page in self.window._tool_widgets.items():
            state["pages"][tool_id] = capture_page(tool_id, page)
        state["automation_videos"] = [str(path) for path in self.automatic._video_paths]
        automatic_route = "automation_settings" if self.window.navigation.automatic_page == "profiles" else "automation"
        state["route"] = self.window.navigation.tool_id or (
            automatic_route if self.window.navigation.automatic_active else "manual"
        )
        return state

    def _snapshot(self):
        state = self._capture()
        state.pop("route", None)
        return json.dumps([state, self.automatic.profiles._snapshot()], sort_keys=True, allow_nan=False)

    def has_unsaved_changes(self) -> bool:
        return self.active is not None and self._snapshot() != self.saved_snapshot

    def confirm_save_before_run(self) -> bool:
        if not self.has_unsaved_changes():
            return True
        answer = QMessageBox.question(
            self.window,
            "Save before running?",
            f'Save changes to “{self.active.name}” before starting automation?',
            QMessageBox.Save | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        return answer == QMessageBox.Save and self.save()

    def refresh_dirty_state(self):
        if self.active is None or self.loading:
            return
        worker = self.automatic._pipeline_worker
        running = worker is not None and worker.isRunning()
        for control in (self.selector, self.new_button, self.save_button, self.save_as_button, self.close_button):
            control.setEnabled(not running)
        if running:
            self._set_status("Automation is running")
            return
        dirty = self.has_unsaved_changes()
        self._set_status("Unsaved changes" if dirty else "Saved")
        self.save_button.setText("Save *" if dirty else "Save")

    def save(self, _checked=False, *, name=None, send_calibration_to_gait=False):
        if self.active is None:
            return False
        automatic = self.automatic
        if automatic._pipeline_worker is not None and automatic._pipeline_worker.isRunning():
            self._set_status("Save after automation stops")
            return False
        snapshots = []
        cleared_assets = set()
        baseline_pages = json.loads(self.saved_snapshot)[0].get("pages", {})
        for spec in self.window._tool_specs:
            page = self.window._tool_widgets.get(spec.id)
            if page is not None and spec.snapshot_provider is not None:
                try:
                    current = spec.snapshot_provider(page)
                    if spec.id == "manual_calibration" and current.calibration is None and (
                        capture_page(spec.id, page) != baseline_pages.get(spec.id)
                    ):
                        current = replace(current, calibration_map=None)
                        cleared_assets.add("calibration_map")
                    snapshots.append(current)
                except ValueError:
                    # Incomplete settings still belong to the workspace; run preflight validates them later.
                    asset = {"gait_parameter_analysis": "analysis_manifest", "knee_correction": "knee_manifest"}.get(spec.id)
                    if asset:
                        cleared_assets.add(asset)
        snapshots.append(ManualProfileSnapshot(
            processing_manifest=automatic.profile_state.manifest_source,
            calibration_map=None if "calibration_map" in cleared_assets else automatic.profile_state.calibration_source,
            analysis_manifest=None if "analysis_manifest" in cleared_assets else automatic.profile_state.analysis_manifest_source,
            knee_manifest=None if "knee_manifest" in cleared_assets else automatic.profile_state.knee_manifest_source,
        ))
        snapshot = combine_manual_snapshots(snapshots)
        gait_page = self.window._tool_widgets.get("gait_parameter_analysis") if send_calibration_to_gait else None
        gait = page_view(gait_page) if gait_page is not None else None
        try:
            state = self._capture()
            if gait is not None:
                if snapshot.calibration is None:
                    raise ValueError("Create calibration sticks before saving to gait analysis.")
                snapshot = replace(snapshot, gait=replace(
                    gait.settings_snapshot(), calibration_method="map",
                    calibration_map_path=None, pixels_per_cm=None, view_calibration=None,
                ))
                combo = gait.calibration_method_combo
                state["pages"]["gait_parameter_analysis"]["controls"]["calibration_method_combo"] = {
                    "data": "map", "text": combo.itemText(combo.findData("map")),
                }
            with self.use_cases.manual_assets.materialize(snapshot, allow_incomplete=True) as assets:
                if gait is not None:
                    if assets.calibration_map is None:
                        raise ValueError("Could not create a usable calibration map.")
                    gait.analysis.settings.calibration_scale(assets.calibration_map)
                regions = self.use_cases.processing_regions(assets.processing_manifest) if assets.processing_manifest else ()
                profile = self.use_cases.save(
                    name or self.active.name, assets.processing_manifest, assets.calibration_map,
                    {region: path for region, path in automatic.profile_state.model_sources.items() if path is not None and region in regions},
                    profile_id=None if name else self.active.id,
                    analysis_manifest=assets.analysis_manifest, knee_manifest=assets.knee_manifest,
                    gait_analysis_enabled=automatic.include_gait_analysis_button.isChecked(),
                    knee_correction_enabled=automatic.include_knee_correction_button.isChecked(),
                    allow_incomplete=True, workspace_state=state,
                )
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self.window, "Could not save workflow", str(exc))
            return False
        self.active = profile
        self.workspace_state = state
        if gait is not None:
            self._apply_profile_calibration("gait_parameter_analysis", gait_page)
            combo = gait.calibration_method_combo
            combo.setCurrentIndex(combo.findData("map"))
            gait.settings_tabs.setCurrentWidget(gait.calibration_tab)
            gait.controller._invalidate_stickplot_preview()
            gait.controller._update_run_state()
            gait.status_label.setText("Calibration saved to gait analysis.")
        automatic.profiles._refresh_profiles(profile.id)
        self.refresh_profiles()
        self.saved_snapshot = self._snapshot()
        self.refresh_dirty_state()
        return True

    def save_as(self, _checked=False):
        if self.active is None:
            return
        name, accepted = QInputDialog.getText(self.window, "Save workflow as", "Workflow name:", text=f"{self.active.name} copy")
        if accepted and name.strip():
            self.save(name=name.strip())

    def _can_switch(self):
        if any(not page.can_close(self.window) for page in self.window._tool_widgets.values()):
            return False
        worker = self.automatic._pipeline_worker
        if worker is not None and worker.isRunning():
            QMessageBox.information(self.window, "Workflow is running", "Finish or stop automation before switching workflows.")
            return False
        if not self.has_unsaved_changes():
            return True
        answer = QMessageBox.question(self.window, "Save workflow changes?", f'Save changes to “{self.active.name}”?',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if answer == QMessageBox.Save:
            return self.save()
        return answer == QMessageBox.Discard

    def close_profile(self, _checked=False):
        if not self._can_switch():
            return False
        self._release_pages()
        self.active = None
        self.workspace_state = {"version": 1, "pages": {}}
        self.automatic._video_paths.clear()
        self.automatic.video_list.clear()
        self.show_picker()
        return True

    def _release_pages(self):
        for page in self.window._tool_widgets.values():
            page.release_resources()
            self.window._stack.removeWidget(page)
            page.deleteLater()
        self.window._tool_widgets.clear()
        self.window._active_tool = None

    def _automatic_saved(self, profile_id):
        if self.loading:
            return
        if self.active is not None and profile_id == self.active.id:
            self.active = self.use_cases.load(profile_id)
        self.refresh_profiles()

