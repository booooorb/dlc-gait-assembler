"""Present saved automatic runs and their resume or output actions."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from dlc_gait_assembly.runway.automatic.business.automatic_stage_definitions import AUTOMATED_STAGE_SPECS

STATUS_LABELS = {
    "ready": "Ready to resume",
    "running": "Interrupted",
    "review": "Awaiting review",
    "paused": "Paused",
    "failed": "Needs attention",
    "complete": "Complete",
    "outputs_only": "Outputs only",
}


class AutomaticRunHistoryDialog(QDialog):
    def __init__(self, parent, runs, *, open_outputs):
        super().__init__(parent)
        self.setWindowTitle("Automation run history")
        self.resize(630, 410)
        layout = QVBoxLayout(self)
        self.runs = QListWidget()
        self.runs.setAccessibleName("Saved automation runs")
        layout.addWidget(self.runs, 1)
        self.details = QLabel("Runs are saved automatically when you start automation.")
        self.details.setTextFormat(Qt.PlainText)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        if not runs:
            self.runs.hide()
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.open_button = buttons.addButton("Open outputs", QDialogButtonBox.ActionRole)
        self.resume_button = buttons.addButton("Resume run", QDialogButtonBox.AcceptRole)
        layout.addWidget(buttons)
        buttons.rejected.connect(self.reject)
        self.open_button.clicked.connect(lambda: open_outputs(self.selected_run.output_folder))
        self.resume_button.clicked.connect(self.accept)
        self.runs.currentItemChanged.connect(self.update_selection)
        for run in runs:
            updated = datetime.fromisoformat(run.updated_at).astimezone().strftime("%Y-%m-%d %H:%M")
            status = STATUS_LABELS.get(run.status, "Saved")
            item = QListWidgetItem(f"{run.profile_name}  ·  {status}  ·  {updated}")
            item.setData(Qt.UserRole, run)
            self.runs.addItem(item)
        self.runs.setCurrentRow(0)
        self.update_selection()

    @property
    def selected_run(self):
        item = self.runs.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def update_selection(self):
        run = self.selected_run
        self.open_button.setEnabled(run is not None)
        self.resume_button.setEnabled(run is not None and run.can_resume)
        if run is None:
            return
        details = []
        if run.video_count:
            details.append(f"{run.video_count} video(s)")
        if run.can_resume and 0 <= run.stage < len(AUTOMATED_STAGE_SPECS):
            details.append(f"Last saved stage: {AUTOMATED_STAGE_SPECS[run.stage].label}")
        if run.message:
            details.append(run.message)
        if run.status == "outputs_only":
            details.append("No checkpoint is available for this run.")
        self.details.setText("\n".join(details) or str(run.output_folder))
