"""Persist appearance, geometry, and automatic update preferences in QSettings."""

from PySide6.QtCore import QSettings

THEME_SETTING_KEY = "appearance/theme"
WINDOW_GEOMETRY_SETTING_KEY = "window/geometry"
AUTOMATIC_UPDATES_SETTING_KEY = "updates/automatic"


class AppPreferencesStore:
    def __init__(self, settings=None):
        self.settings = settings if settings is not None else QSettings("DLC Gait Assembler", "DLC Gait Assembler")

    def theme(self):
        return str(self.settings.value(THEME_SETTING_KEY, "")).strip().lower()

    def save_theme(self, mode):
        self.settings.setValue(THEME_SETTING_KEY, mode)
        self.settings.sync()

    def geometry(self):
        return self.settings.value(WINDOW_GEOMETRY_SETTING_KEY)

    def save_geometry(self, geometry):
        self.settings.setValue(WINDOW_GEOMETRY_SETTING_KEY, geometry)
        self.settings.sync()

    def automatic_updates(self):
        return self.settings.value(AUTOMATIC_UPDATES_SETTING_KEY, True, type=bool)

    def save_automatic_updates(self, enabled):
        self.settings.setValue(AUTOMATIC_UPDATES_SETTING_KEY, bool(enabled))
        self.settings.sync()
