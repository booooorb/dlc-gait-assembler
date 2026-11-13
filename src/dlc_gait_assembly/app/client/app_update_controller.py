"""Present background update checks, saved preferences, and installation after window cleanup."""

from __future__ import annotations

from threading import Thread

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QProgressBar, QVBoxLayout

import dlc_gait_assembly
from dlc_gait_assembly.app.business.app_update_contracts import PROJECT_URL, AppUpdateInfo, AppUpdateOperations

CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000


class AppUpdateController(QObject):
    checked = Signal(object)
    failed = Signal(str)
    progress = Signal(str)
    installed = Signal(str)

    def __init__(self, window, operations: AppUpdateOperations, preferences):
        super().__init__(window)
        self.window = window
        self.operations = operations
        self.preferences = preferences
        self.pending_update: AppUpdateInfo | None = None
        self._checking = False
        self._manual = False
        self._closing = False
        self._notified_revision = ""
        self._latest: AppUpdateInfo | None = None
        self._install_dialog = None
        self._install_error = ""
        self.checked.connect(self._checked)
        self.failed.connect(self._failed)
        self.installed.connect(self._installed)
        menu = window._settings_menu
        menu.addSeparator()
        self.version_action = menu.addAction(f"Version {dlc_gait_assembly.__version__}")
        self.version_action.setToolTip("Version of the application currently running.")
        self.version_action.setEnabled(False)
        self.check_action = menu.addAction("Check for updates…")
        self.check_action.setToolTip("Check whether a newer application version is available.")
        self.check_action.triggered.connect(lambda: self.check(manual=True))
        self.install_action = menu.addAction("Install available update and restart…")
        self.install_action.setToolTip("Install the downloaded application update and restart after saving your work.")
        self.install_action.setVisible(False)
        self.install_action.triggered.connect(self._offer_latest)
        self.auto_action = menu.addAction("Check for updates automatically")
        self.auto_action.setToolTip("Check for new application versions at startup and periodically while the app is open.")
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(preferences.automatic_updates())
        self.auto_action.toggled.connect(self._set_automatic)
        self.timer = QTimer(self)
        self.timer.setInterval(CHECK_INTERVAL_MS)
        self.timer.timeout.connect(self._automatic_check)
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.setInterval(2500)
        self.startup_timer.timeout.connect(self._automatic_check)

    def start(self) -> None:
        if self.auto_action.isChecked():
            self.timer.start()
            self.startup_timer.start()

    def shutdown(self) -> None:
        self._closing = True
        self.timer.stop()
        self.startup_timer.stop()

    def _set_automatic(self, enabled: bool) -> None:
        self.preferences.save_automatic_updates(enabled)
        if enabled:
            self.start()
        else:
            self.timer.stop()
            self.startup_timer.stop()

    def _automatic_check(self) -> None:
        if self.auto_action.isChecked():
            self.check()

    def check(self, *, manual: bool = False) -> None:
        if self._closing:
            return
        self._manual = self._manual or manual
        if self._checking:
            return
        self._checking = True
        self.check_action.setEnabled(False)
        self.check_action.setText("Checking for updates…")
        # A daemon thread lets a slow/offline check finish without holding app shutdown.
        Thread(target=self._check_in_background, daemon=True).start()

    def _check_in_background(self) -> None:
        try:
            result = self.operations.check()
        except Exception as error:
            if not self._closing:
                self.failed.emit(str(error))
        else:
            if not self._closing:
                self.checked.emit(result)

    def _finish_check(self) -> bool:
        manual = self._manual
        self._checking = False
        self._manual = False
        self.check_action.setEnabled(True)
        self.check_action.setText("Check for updates…")
        return manual

    @Slot(object)
    def _checked(self, update: AppUpdateInfo) -> None:
        if self._closing:
            return
        manual = self._finish_check()
        self._latest = update
        self.version_action.setText(f"Version {update.current_label}")
        self.install_action.setVisible(update.available and not update.blocked_reason)
        if update.blocked_reason:
            if manual or (update.available and update.latest_revision != self._notified_revision):
                message = update.blocked_reason
                if update.available:
                    self._notified_revision = update.latest_revision
                    message = (
                        f"A newer version is available: {update.latest_label}\n"
                        f"Installed version: {update.current_label}\n\n{update.blocked_reason}"
                    )
                QMessageBox.information(self.window, "Application updates", message)
        elif update.available:
            if manual or update.latest_revision != self._notified_revision:
                self._notified_revision = update.latest_revision
                self._offer_latest()
        elif manual:
            QMessageBox.information(
                self.window, "Application updates", f"You are up to date.\nInstalled version: {update.current_label}"
            )

    @Slot(str)
    def _failed(self, message: str) -> None:
        if self._closing:
            return
        if self._finish_check():
            QMessageBox.warning(self.window, "Could not check for updates", message)

    def _offer_latest(self) -> None:
        update = self._latest
        if self._closing or update is None or not update.available or update.blocked_reason:
            return
        message = QMessageBox(self.window)
        message.setWindowTitle("Application update available")
        message.setIcon(QMessageBox.Information)
        message.setText(f"A newer version is available: {update.latest_label}")
        message.setInformativeText(
            f"Installed version: {update.current_label}\n\n"
            "Save your work before continuing. The app will close, install the update, and restart."
        )
        install = message.addButton("Install and restart", QMessageBox.AcceptRole)
        notes = message.addButton("View changes", QMessageBox.ActionRole)
        message.addButton("Later", QMessageBox.RejectRole)
        message.setDefaultButton(install)
        message.exec()
        if message.clickedButton() == notes:
            suffix = (
                f"/compare/{update.current_revision}...{update.latest_revision}"
                if update.checkout is not None else "/releases/latest"
            )
            QDesktopServices.openUrl(QUrl(PROJECT_URL + suffix))
        elif message.clickedButton() == install:
            self.request_install(update)

    def request_install(self, update: AppUpdateInfo) -> None:
        if self._closing or self._checking or not update.available or update.blocked_reason:
            return
        self.pending_update = update
        # MainWindow.closeEvent runs the existing save and active-analysis guards.
        if not self.window.close():
            self.pending_update = None

    def install_pending(self) -> bool:
        """Run only after the main event loop has exited and all tools have released resources."""
        if self.pending_update is None:
            return False
        self._install_dialog = AppUpdateInstallDialog()
        self.progress.connect(self._install_dialog.label.setText)
        Thread(target=self._install_in_background, daemon=True).start()
        self._install_dialog.exec()
        self.progress.disconnect(self._install_dialog.label.setText)
        self._install_dialog = None
        if self._install_error:
            QMessageBox.warning(None, "Update could not be completed", self._install_error)
            return False
        try:
            self.operations.restart()
        except Exception as error:
            QMessageBox.warning(None, "Reopen the application", str(error))
            return False
        return True

    def _install_in_background(self) -> None:
        try:
            self.operations.install(self.pending_update, self.progress.emit)
        except Exception as error:
            self.installed.emit(str(error))
        else:
            self.installed.emit("")

    @Slot(str)
    def _installed(self, error: str) -> None:
        self._install_error = error
        if self._install_dialog is not None:
            self._install_dialog.done(0)


class AppUpdateInstallDialog(QDialog):
    """Keep installation progress visible until the environment update has finished."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Updating DLC Gait Assembler")
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        self.label = QLabel("Preparing the update…")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)

    def reject(self) -> None:
        pass

    def closeEvent(self, event) -> None:
        event.ignore()
