"""Persist theme and serialized window geometry in the existing QSettings namespace."""

from PySide6.QtCore import QSettings

THEME_SETTING_KEY = "appearance/theme"
WINDOW_GEOMETRY_SETTING_KEY = "window/geometry"


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
