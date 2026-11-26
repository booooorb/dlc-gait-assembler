"""Present saved automatic runs and their resume or output actions."""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QSizePolicy,
    QSplitter,
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
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setAccessibleName("Filter runs")
        self.search.setPlaceholderText("Filter by workflow, status, or date")
        self.search.setClearButtonEnabled(True)
        self.search.setVisible(bool(runs))
        layout.addWidget(self.search)

        panes = QSplitter(Qt.Vertical)
        panes.setChildrenCollapsible(False)
        self.runs = QListWidget()
        self.runs.setAccessibleName("Saved automation runs")
        self.runs.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.runs.setTextElideMode(Qt.ElideRight)
        self.runs.setUniformItemSizes(True)
        self.runs.setVisible(bool(runs))
        panes.addWidget(self.runs)

        self.details = QPlainTextEdit()
        self.details.setAccessibleName("Selected run details")
        self.details.setReadOnly(True)
        self.details.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        panes.addWidget(self.details)
        for pane in (self.runs, self.details):
            pane.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Ignored)
            pane.setMinimumHeight(56)
        panes.setSizes([200, 130])
        layout.addWidget(panes, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.open_button = buttons.addButton("Open outputs", QDialogButtonBox.ActionRole)
        self.resume_button = buttons.addButton("Resume run", QDialogButtonBox.AcceptRole)
        for button in buttons.buttons():
            button.setAutoDefault(False)
        layout.addWidget(buttons)
        buttons.rejected.connect(self.reject)
        self.open_button.clicked.connect(lambda: open_outputs(self.selected_run.output_folder))
        self.resume_button.clicked.connect(self.accept)
        self.runs.currentItemChanged.connect(self.update_selection)
        self.search.textChanged.connect(self.filter_runs)
        self.search.returnPressed.connect(self.runs.setFocus)
        for run in runs:
            updated = datetime.fromisoformat(run.updated_at).astimezone().strftime("%Y-%m-%d %H:%M")
            status = STATUS_LABELS.get(run.status, "Saved")
            item = QListWidgetItem(f"{run.profile_name}  ·  {status}  ·  {updated}")
            item.setToolTip(item.text())
            item.setData(Qt.UserRole, run)
            self.runs.addItem(item)
        self.runs.setCurrentRow(0)
        self.update_selection()
        if runs:
            self.runs.setFocus()

        screen = parent.screen() if parent is not None else self.screen()
        available = screen.availableGeometry()
        self.resize(min(620, available.width() - 32), min(400 if runs else 150, available.height() - 64))

    def filter_runs(self, text):
        query = text.strip().casefold()
        first_match = -1
        for row in range(self.runs.count()):
            item = self.runs.item(row)
            matches = query in item.text().casefold()
            item.setHidden(not matches)
            if matches and first_match == -1:
                first_match = row
        if self.selected_run is None:
            self.runs.setCurrentRow(first_match)

    @property
    def selected_run(self):
        item = self.runs.currentItem()
        return item.data(Qt.UserRole) if item is not None and not item.isHidden() else None

    def update_selection(self):
        run = self.selected_run
        self.open_button.setEnabled(run is not None)
        self.resume_button.setEnabled(run is not None and run.can_resume)
        if run is None:
            message = "No saved runs match your filter." if self.runs.count() else (
                "Runs are saved automatically when you start automation."
            )
            self.details.setPlainText(message)
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
        summary = self.runs.currentItem().text()
        self.details.setPlainText("\n\n".join([summary, *details, str(run.output_folder)]))
