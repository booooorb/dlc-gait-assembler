"""Present saved profiles and their selection, creation, duplication, and deletion actions."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton


def build_automatic_profile_list(self, configuration_layout):
    configuration_toolbar = QFrame()
    configuration_toolbar.setObjectName("ProfileConfigurationToolbar")
    toolbar_layout = QHBoxLayout(configuration_toolbar)
    toolbar_layout.setContentsMargins(12, 10, 12, 10)
    self.back_to_automation_button = QPushButton("Back to automation")
    self.back_to_automation_button.setObjectName("BackToAutomationButton")
    self.back_to_automation_button.setToolTip(
        "Return to the video queue. Unsaved profile edits remain in this window until you close the application or select another profile."
    )
    toolbar_layout.addWidget(self.back_to_automation_button)
    configuration_title = QLabel("Manage automated profiles")
    configuration_title.setObjectName("ProfileConfigurationTitle")
    toolbar_layout.addWidget(configuration_title)
    toolbar_layout.addStretch(1)
    configuration_layout.addWidget(configuration_toolbar)
    management = QFrame()
    management.setObjectName("ProfileManagementPanel")
    management_layout = QHBoxLayout(management)
    management_layout.setContentsMargins(12, 10, 12, 10)
    management_layout.setSpacing(8)
    self.new_profile_button = QPushButton("New profile")
    self.new_profile_button.setObjectName("NewProfileButton")
    self.new_profile_button.setToolTip(
        "Clear the profile form so you can build a new reusable automation setup. This does not delete existing profiles."
    )
    management_layout.addWidget(self.new_profile_button)
    management_layout.addWidget(self._field_label("Profile"))
    self.configuration_profile_selector = QComboBox()
    self.configuration_profile_selector.setObjectName("ConfigurationProfileSelector")
    self.configuration_profile_selector.setToolTip("Load an existing profile into the form for inspection or editing.")
    management_layout.addWidget(self.configuration_profile_selector, 1)
    self.duplicate_profile_button = QPushButton("Duplicate profile")
    self.duplicate_profile_button.setObjectName("DuplicateProfileButton")
    self.duplicate_profile_button.setToolTip(
        "Copy the selected profile under a new name. The original profile and all of its saved input files remain unchanged."
    )
    management_layout.addWidget(self.duplicate_profile_button)
    management_layout.addWidget(self._field_label("Name"))
    self.profile_name = QLineEdit()
    self.profile_name.setObjectName("ProfileNameInput")
    self.profile_name.setPlaceholderText("Example: Treadmill camera setup")
    self.profile_name.setToolTip(
        "Enter a recognizable name for this complete automation setup, such as the camera position, animal group, or experiment type."
    )
    management_layout.addWidget(self.profile_name, 1)
    self.delete_profile_button = QPushButton("Delete profile")
    self.delete_profile_button.setObjectName("DeleteProfileButton")
    self.delete_profile_button.setToolTip(
        "Permanently delete the selected saved profile after confirmation. Source manifests, models, and videos are not deleted."
    )
    management_layout.addWidget(self.delete_profile_button)
    configuration_layout.addWidget(management)
