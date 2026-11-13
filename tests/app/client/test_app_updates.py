"""Verify update preferences, nonblocking checks, save cancellation, and restart outcomes."""

from dataclasses import replace
from threading import Event

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QWidget

import dlc_gait_assembly
from dlc_gait_assembly.app.business.app_update_contracts import AppUpdateInfo
from dlc_gait_assembly.app.client.app_update_controller import AppUpdateController
from dlc_gait_assembly.app.infrastructure.app_preferences_store import AppPreferencesStore


class UpdateWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._settings_menu = QMenu(self)
        self.allow_close = True

    def closeEvent(self, event):
        if self.allow_close:
            self.updates.shutdown()
            event.accept()
        else:
            event.ignore()


class UpdateOperations:
    def __init__(self):
        self.result = AppUpdateInfo("0.1.0", available=True, latest_revision="a" * 40, latest_version="0.2.0")
        self.checks = 0
        self.installs = []
        self.restarts = 0
        self.error = ""

    def check(self):
        self.checks += 1
        if self.error:
            raise RuntimeError(self.error)
        return self.result

    def install(self, update, progress):
        self.installs.append(update)
        progress("Installing…")
        if self.error:
            raise RuntimeError(self.error)

    def restart(self):
        self.restarts += 1


@pytest.fixture
def update_ui(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = UpdateWindow()
    operations = UpdateOperations()
    preferences = AppPreferencesStore(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    window.updates = AppUpdateController(window, operations, preferences)
    yield window, operations, preferences
    window.allow_close = True
    window.close()
    app.processEvents()


def wait_until(predicate):
    for _ in range(200):
        QApplication.processEvents()
        if predicate():
            return
        QTest.qWait(5)
    assert predicate()


def test_automatic_checks_default_on_and_opt_out_persists(update_ui):
    window, _, preferences = update_ui
    updates = window.updates
    assert preferences.automatic_updates()
    updates.start()
    assert updates.startup_timer.isActive() and updates.timer.isActive()
    updates.auto_action.setChecked(False)
    assert not updates.startup_timer.isActive() and not updates.timer.isActive()
    assert not AppPreferencesStore(preferences.settings).automatic_updates()
    updates.start()
    assert not updates.timer.isActive()
    updates.auto_action.setChecked(True)
    assert preferences.automatic_updates() and updates.timer.isActive()


def test_background_fetch_does_not_block_ui_or_duplicate_notifications(update_ui, monkeypatch):
    window, operations, _ = update_ui
    offers = []
    monkeypatch.setattr(window.updates, "_offer_latest", lambda: offers.append(True))
    window.updates.check()
    wait_until(lambda: not window.updates._checking)
    assert offers == [True]
    assert window.updates.install_action.isVisible()
    window.updates.check()
    wait_until(lambda: not window.updates._checking)
    assert offers == [True]
    window.updates.check(manual=True)
    wait_until(lambda: not window.updates._checking)
    assert offers == [True, True]
    assert not operations.installs


def test_opening_app_automatically_checks_and_shows_update_choices(update_ui, monkeypatch):
    window, operations, _ = update_ui
    prompts = []

    def respond_later(message):
        prompts.append((message.text(), [button.text() for button in message.buttons()]))
        later = next(button for button in message.buttons() if button.text() == "Later")
        later.click()
        return 0

    monkeypatch.setattr(QMessageBox, "exec", respond_later)
    window.updates.startup_timer.setInterval(1)
    window.show()
    window.updates.start()
    wait_until(lambda: bool(prompts))
    assert operations.checks == 1
    assert "0.2.0" in prompts[0][0]
    assert set(prompts[0][1]) == {"Install and restart", "View changes", "Later"}
    assert window.isVisible()
    assert window.updates.pending_update is None
    assert not operations.installs


def test_offline_automatic_checks_are_quiet_and_manual_checks_explain(update_ui, monkeypatch):
    window, operations, _ = update_ui
    operations.error = "Connection unavailable"
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    window.updates.check()
    wait_until(lambda: not window.updates._checking)
    assert not messages
    assert window.updates.check_action.isEnabled()
    window.updates.check(manual=True)
    wait_until(lambda: not window.updates._checking)
    assert messages == ["Connection unavailable"]


def test_blocked_update_is_explained_without_offering_install(update_ui, monkeypatch):
    window, operations, _ = update_ui
    operations.result = replace(operations.result, blocked_reason="Commit your local edits first.")
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[-1]))
    window.updates.check(manual=True)
    wait_until(lambda: not window.updates._checking)
    assert len(messages) == 1
    assert "A newer version is available: 0.2.0" in messages[0]
    assert "Commit your local edits first." in messages[0]
    assert not window.updates.install_action.isVisible()


def test_startup_notifies_about_blocked_update_once_and_preserves_edits(update_ui, monkeypatch):
    window, operations, _ = update_ui
    operations.result = replace(operations.result, blocked_reason="Commit your local edits first.")
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[-1]))
    window.updates.startup_timer.setInterval(1)
    window.updates.start()
    wait_until(lambda: bool(messages))
    assert "A newer version is available: 0.2.0" in messages[0]
    assert operations.result.blocked_reason in messages[0]
    window.updates.check()
    wait_until(lambda: not window.updates._checking)
    assert len(messages) == 1
    assert not window.updates.install_action.isVisible()
    assert not operations.installs


def test_automatic_checks_stay_quiet_when_no_newer_version_exists(update_ui, monkeypatch):
    window, operations, _ = update_ui
    operations.result = replace(operations.result, available=False, blocked_reason="Local edits are present.")
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[-1]))
    window.updates.check()
    wait_until(lambda: not window.updates._checking)
    assert not messages


def test_canceling_window_save_keeps_app_open_and_cancels_install(update_ui):
    window, operations, _ = update_ui
    window.show()
    window.allow_close = False
    window.updates.request_install(operations.result)
    assert window.isVisible()
    assert window.updates.pending_update is None
    assert not window.updates._closing
    assert not operations.installs


def test_accepted_close_stages_update_and_install_restarts_only_on_success(update_ui):
    window, operations, _ = update_ui
    window.show()
    window.updates.request_install(operations.result)
    assert not window.isVisible()
    assert window.updates._closing
    assert window.updates.pending_update == operations.result
    assert not operations.installs
    assert window.updates.install_pending()
    assert operations.installs == [operations.result]
    assert operations.restarts == 1


def test_install_failure_explains_error_without_restarting(update_ui, monkeypatch):
    window, operations, _ = update_ui
    operations.error = "Dependency installation failed"
    window.updates.pending_update = operations.result
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    assert not window.updates.install_pending()
    assert messages == [operations.error]
    assert not operations.restarts


def test_slow_check_allows_shutdown_and_discards_late_results(update_ui, monkeypatch):
    window, operations, _ = update_ui
    started, release, finished = Event(), Event(), Event()

    def check():
        started.set()
        release.wait(timeout=5)
        finished.set()
        return operations.result

    monkeypatch.setattr(operations, "check", check)
    offers = []
    monkeypatch.setattr(window.updates, "_offer_latest", lambda: offers.append(True))
    window.updates.check()
    assert started.wait(timeout=1)
    window.show()
    assert window.close()
    release.set()
    assert finished.wait(timeout=1)
    QApplication.processEvents()
    assert not offers


def test_main_window_exposes_update_settings_without_starting_network(tmp_path):
    from dlc_gait_assembly.app.app_bootstrap import create_main_window

    app = QApplication.instance() or QApplication([])
    operations = UpdateOperations()
    preferences = AppPreferencesStore(QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat))
    window = create_main_window(update_service=operations, preferences=preferences)
    try:
        assert window.updates.check_action in window._settings_menu.actions()
        assert f"Version {dlc_gait_assembly.__version__}" == window.updates.version_action.text()
        app.processEvents()
        assert operations.checks == 0
    finally:
        window.close()
