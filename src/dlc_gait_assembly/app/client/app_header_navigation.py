"""Assemble primary and workflow navigation, branding, and theme controls."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QActionGroup, QGuiApplication, QIcon, QPixmap, QRegion
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import dlc_gait_assembly.shared.client.theme.theme_application_state as theme
from dlc_gait_assembly.app.client.app_branding_widgets import (
    BRAND_LOGO_FILENAMES,
    BRAND_LOGO_HEIGHT,
    BRAND_LOGO_MAX_WIDTH,
    main_menu_logo_label,
    menu_asset_pixmap,
    navigation_icon,
)
from dlc_gait_assembly.app.client.app_shell_styles import APP_TOOLBAR_HEIGHT
from dlc_gait_assembly.runway.manual.business.manual_stage_definitions import (
    MANUAL_STAGE_DISPLAY_LABELS,
    MANUAL_STAGE_MENU_ASSETS,
)
from dlc_gait_assembly.shared.client.theme.theme_icon_provider import interface_icon
from dlc_gait_assembly.shared.client.theme.theme_menu_graphics import menu_colors, menu_icon
from dlc_gait_assembly.shared.infrastructure.packaged_resource_reader import resource_path


class AppHeaderNavigation:
    """AppHeaderNavigation operates on its explicitly supplied MainWindow view."""

    def __init__(self, view):
        self.view = view

    def _build_shell(self, initial_theme_mode: str) -> None:
        shell = QWidget()
        shell.setObjectName("AppShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        toolbar = QFrame()
        toolbar.setObjectName("AppToolbar")
        toolbar.setMinimumHeight(APP_TOOLBAR_HEIGHT)
        toolbar.setMaximumHeight(APP_TOOLBAR_HEIGHT)
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)
        primary_row = QFrame()
        primary_row.setObjectName("PrimaryToolbarRow")
        primary_row.setFixedHeight(APP_TOOLBAR_HEIGHT)
        primary_layout = QHBoxLayout(primary_row)
        primary_layout.setContentsMargins(20, 0, 16, 0)
        primary_layout.setSpacing(10)
        home_button = QPushButton()
        home_button.setObjectName("HomeNavigationButton")
        home_button.setAccessibleName("DLC Gait Assembler home")
        home_button.setCursor(Qt.PointingHandCursor)
        home_button.setFixedSize(BRAND_LOGO_MAX_WIDTH + 8, 44)
        home_button.setToolTip("Open the main menu")
        home_button.clicked.connect(self.view.routes._show_home_menu)
        self.view._home_button = home_button
        primary_layout.addWidget(home_button)
        divider = QFrame()
        divider.setObjectName("ToolbarDivider")
        divider.setFrameShape(QFrame.VLine)
        primary_layout.addWidget(divider)
        primary_navigation = QFrame()
        primary_navigation.setObjectName("PrimaryNavigation")
        primary_navigation.setAccessibleName("Primary navigation")
        navigation_layout = QHBoxLayout(primary_navigation)
        navigation_layout.setContentsMargins(0, 0, 0, 0)
        navigation_layout.setSpacing(4)
        runway_button = QToolButton()
        runway_button.setObjectName("RunwayNavigationButton")
        runway_button.setText("Runway  ›")
        runway_button.setProperty("activeNavigation", False)
        runway_button.setProperty("navigationRole", "runway")
        runway_button.setCursor(Qt.PointingHandCursor)
        runway_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        runway_button.setToolTip("Show automated, profile, and manual runway workflows.")
        runway_button.clicked.connect(lambda _checked=False: self.view.animations._toggle_runway_options())
        navigation_layout.addWidget(runway_button)
        self.view._runway_button = runway_button
        runway_options = QFrame()
        runway_options.setObjectName("RunwayOptions")
        runway_options_layout = QHBoxLayout(runway_options)
        runway_options_layout.setContentsMargins(9, 0, 9, 0)
        runway_options_layout.setSpacing(4)
        automation_group_label = QLabel("AUTOMATION")
        automation_group_label.setObjectName("RunwayGroupLabel")
        automation_group_label.hide()
        automated_button = QPushButton("Automated")
        automated_button.setObjectName("RunwayOptionButton")
        automated_button.setProperty("runwayOption", "automated")
        automated_button.setCursor(Qt.PointingHandCursor)
        automated_button.setToolTip("Select a profile and process a batch of runway videos.")
        automated_button.clicked.connect(self.view.routes._show_automated_pipeline)
        runway_options_layout.addWidget(automated_button)
        self.view._automation_run_button = automated_button
        profiles_button = QPushButton("Profiles")
        profiles_button.setObjectName("RunwayOptionButton")
        profiles_button.setProperty("runwayOption", "profiles")
        profiles_button.setCursor(Qt.PointingHandCursor)
        profiles_button.setToolTip("Create, edit, and manage reusable runway automation profiles.")
        profiles_button.clicked.connect(self.view.routes._show_automated_profiles)
        runway_options_layout.addWidget(profiles_button)
        self.view._automation_profiles_button = profiles_button
        runway_group_divider = QFrame()
        runway_group_divider.setObjectName("RunwayGroupDivider")
        runway_group_divider.setFrameShape(QFrame.VLine)
        runway_options_layout.addWidget(runway_group_divider)
        manual_group_label = QLabel("MANUAL")
        manual_group_label.setObjectName("RunwayManualLabel")
        manual_group_label.hide()
        manual_button = QToolButton()
        manual_button.setObjectName("RunwayManualButton")
        manual_button.setText("Manual")
        manual_button.setCursor(Qt.PointingHandCursor)
        manual_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        manual_button.setToolTip("Slide down the manual runway stages.")
        manual_button.clicked.connect(self.view.routes._show_main_menu)
        runway_options_layout.addWidget(manual_button)
        self.view._runway_manual_button = manual_button
        runway_mode_highlight = QFrame(runway_options)
        runway_mode_highlight.setObjectName("RunwayModeHighlight")
        runway_mode_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        runway_mode_highlight.hide()
        self.view._runway_mode_highlight = runway_mode_highlight
        self.view._runway_mode_highlight_animation = QPropertyAnimation(runway_mode_highlight, b"geometry", self.view)
        self.view._runway_mode_highlight_animation.setDuration(220)
        self.view._runway_mode_highlight_animation.finished.connect(self.view.animations._snap_runway_mode_highlight)
        self.view._runway_mode_highlight_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        runway_options.setFixedHeight(46)
        runway_options.setMaximumWidth(0)
        runway_options.hide()
        navigation_layout.addWidget(runway_options, 0, Qt.AlignVCenter)
        self.view._runway_options = runway_options
        self.view._runway_options_expanded = False
        self.view._runway_options_animation = QPropertyAnimation(runway_options, b"maximumWidth", self.view)
        self.view._runway_options_animation.setDuration(230)
        self.view._runway_options_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.view._runway_options_animation.finished.connect(self.view.animations._runway_options_animation_finished)
        ladder_button = QPushButton("Ladder")
        ladder_button.setObjectName("LadderNavigationButton")
        ladder_button.setProperty("activeNavigation", False)
        ladder_button.setProperty("navigationRole", "ladder")
        ladder_button.setCursor(Qt.PointingHandCursor)
        ladder_button.setToolTip("Open ladder analysis.")
        ladder_button.clicked.connect(lambda _checked=False: self.view.routes._open_tool(self.view._ladder_spec.id))
        navigation_layout.addWidget(ladder_button)
        self.view._ladder_button = ladder_button
        primary_layout.addWidget(primary_navigation)
        self.view._primary_navigation = primary_navigation
        manual_pipeline_group = QFrame(primary_row)
        manual_pipeline_group.setObjectName("ManualPipelineGroup")
        manual_pipeline_layout = QHBoxLayout(manual_pipeline_group)
        manual_pipeline_layout.setContentsMargins(0, 0, 0, 0)
        manual_pipeline_layout.setSpacing(0)
        manual_tools_button = QToolButton(manual_pipeline_group)
        manual_tools_button.setObjectName("ManualPipelineButton")
        manual_tools_button.setText("Manual")
        manual_tools_button.setProperty("navigationRole", "manual")
        manual_tools_button.setToolTip("Open the manual pipeline and its stages.")
        manual_tools_button.setCursor(Qt.PointingHandCursor)
        manual_tools_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        manual_tools_button.setFixedWidth(106)
        manual_tools_button.clicked.connect(lambda _checked=False: self.view.routes._manual_navigation_clicked())
        self.view._manual_tools_button = manual_tools_button
        manual_tools_button.hide()
        navigation_highlight = QFrame(primary_row)
        navigation_highlight.setObjectName("PrimaryNavigationHighlight")
        navigation_highlight.setProperty("navigationRole", "automated")
        navigation_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        navigation_highlight.hide()
        navigation_highlight.lower()
        self.view._primary_navigation_highlight = navigation_highlight
        self.view._primary_navigation_animation = QPropertyAnimation(navigation_highlight, b"geometry", self.view)
        self.view._primary_navigation_animation.setDuration(230)
        self.view._primary_navigation_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.view._primary_row = primary_row
        self.view._primary_layout = primary_layout
        self.view._primary_navigation_layout = navigation_layout
        manual_stage_frame = QFrame(toolbar)
        manual_stage_frame.setObjectName("ManualStageExpansion")
        manual_stage_layout = QHBoxLayout(manual_stage_frame)
        manual_stage_layout.setContentsMargins(8, 2, 8, 2)
        manual_stage_layout.setSpacing(0)
        self.view._manual_stage_buttons: dict[str, QPushButton] = {}
        for index, spec in enumerate(self.view._tool_specs):
            button = QPushButton(MANUAL_STAGE_DISPLAY_LABELS[spec.id])
            button.setObjectName("ManualStageButton")
            button.setProperty("manualStage", spec.id)
            button.setProperty("activeStage", False)
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            button.setMinimumWidth(0)
            button.setEnabled(spec.enabled)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(spec.label)
            button.setIcon(QIcon(menu_asset_pixmap(MANUAL_STAGE_MENU_ASSETS[spec.id], 20)))
            button.setIconSize(QSize(20, 20))
            if spec.enabled:
                button.clicked.connect(lambda _checked=False, tool_id=spec.id: self.view.routes._open_tool(tool_id))
            self.view._manual_stage_buttons[spec.id] = button
            manual_stage_layout.addWidget(button, 1)
            if index < len(self.view._tool_specs) - 1:
                separator = QLabel(">")
                separator.setObjectName("ManualStageSeparator")
                separator.setAlignment(Qt.AlignCenter)
                manual_stage_layout.addWidget(separator)
        profile_separator = QLabel(">", manual_stage_frame)
        profile_separator.setObjectName("ManualStageSeparator")
        profile_separator.setAlignment(Qt.AlignCenter)
        manual_stage_layout.addWidget(profile_separator)
        create_profile_button = QPushButton("Create\nprofile", manual_stage_frame)
        create_profile_button.setObjectName("ManualPresetProfileButton")
        create_profile_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        create_profile_button.setMinimumWidth(0)
        create_profile_button.setCursor(Qt.PointingHandCursor)
        create_profile_button.setToolTip(
            "Create a profile draft from manifests exported in the manual pipeline. Settings without a manifest are left blank."
        )
        create_profile_button.clicked.connect(self.view.routes._create_profile_from_manual_presets)
        manual_stage_layout.addWidget(create_profile_button, 1)
        self.view._manual_preset_profile_button = create_profile_button
        manual_stage_highlight = QFrame(manual_stage_frame)
        manual_stage_highlight.setObjectName("ManualStageHighlight")
        manual_stage_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        manual_stage_highlight.hide()
        self.view._manual_stage_highlight = manual_stage_highlight
        self.view._manual_stage_highlight_animation = QPropertyAnimation(manual_stage_highlight, b"geometry", self.view)
        self.view._manual_stage_highlight_animation.setDuration(220)
        self.view._manual_stage_highlight_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        manual_stage_frame.hide()
        manual_stage_frame.setMaximumHeight(0)
        self.view._manual_stage_frame = manual_stage_frame
        self.view._manual_stage_expanded = False
        manual_pipeline_group.hide()
        self.view._manual_pipeline_group = manual_pipeline_group
        self.view._manual_stage_animation = QPropertyAnimation(manual_stage_frame, b"maximumHeight", self.view)
        self.view._manual_stage_animation.setDuration(210)
        self.view._manual_stage_animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        self.view._manual_stage_animation.finished.connect(self.view.animations._manual_stage_animation_finished)
        self.view._toolbar_height_animation = QPropertyAnimation(toolbar, b"minimumHeight", self.view)
        self.view._toolbar_height_animation.setDuration(210)
        self.view._toolbar_height_animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        self.view._toolbar_max_height_animation = QPropertyAnimation(toolbar, b"maximumHeight", self.view)
        self.view._toolbar_max_height_animation.setDuration(210)
        self.view._toolbar_max_height_animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        primary_layout.addStretch(1)
        credits_button = QToolButton()
        credits_button.setObjectName("CreditsButton")
        credits_button.setText("Credits")
        credits_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        credits_button.setAccessibleName("Artwork credits and software citations")
        credits_button.setCursor(Qt.PointingHandCursor)
        credits_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        credits_menu = QMenu(credits_button)
        credits_menu.setToolTipsVisible(True)
        self.view.credits._build_credit_actions(credits_menu)
        credits_button.setMenu(credits_menu)
        self.view._credits_button = credits_button
        self.view._credits_menu = credits_menu
        primary_layout.addWidget(credits_button)
        settings_button = QToolButton()
        settings_button.setObjectName("SettingsButton")
        settings_button.setText("Settings")
        settings_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        settings_button.setAccessibleName("Application settings")
        settings_button.setCursor(Qt.PointingHandCursor)
        settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_menu = QMenu(settings_button)
        self._build_theme_actions(settings_menu, initial_theme_mode)
        settings_button.setMenu(settings_menu)
        self.view._settings_button = settings_button
        self.view._settings_menu = settings_menu
        primary_layout.addWidget(settings_button)
        partner_marks = QFrame()
        partner_marks.setObjectName("PartnerMarks")
        partner_layout = QHBoxLayout(partner_marks)
        partner_layout.setContentsMargins(8, 4, 8, 4)
        partner_layout.setSpacing(12)
        partner_layout.addWidget(main_menu_logo_label("choforcelab.png"))
        partner_layout.addWidget(main_menu_logo_label("NERVES_Logo.png"))
        primary_layout.addWidget(partner_marks)
        self.view._partner_marks = partner_marks
        toolbar_layout.addWidget(primary_row, 0)
        toolbar_layout.addWidget(manual_stage_frame, 0)
        shell_layout.addWidget(toolbar)
        shell_layout.addWidget(self.view._stack, 1)
        self.view.setCentralWidget(shell)
        self.view._shell = shell
        self.view._toolbar = toolbar
        self.view.styling._apply_shell_style()
        for widget in (
            self.view._runway_options,
            self.view._automation_run_button,
            self.view._automation_profiles_button,
            self.view._runway_manual_button,
        ):
            widget.installEventFilter(self.view)

    def _apply_navigation_icons(self) -> None:
        self._apply_brand_logo()
        c = menu_colors(theme.IS_DARK)
        navigation_icons = (
            (self.view._runway_button, "runway", c["text"]),
            (self.view._automation_run_button, "automated", theme.TOOL_1),
            (self.view._automation_profiles_button, "profiles", theme.TOOL_2),
            (self.view._ladder_button, "ladder", theme.TOOL_2),
            (self.view._runway_manual_button, "manual", c["accent"]),
        )
        for button, icon_name, color in navigation_icons:
            button.setIcon(navigation_icon(icon_name, color))
            button.setIconSize(QSize(18, 18))
        stage_icons = ("ruler-measure", "movie", "topology-star-3", "angle", "walk", "chart-dots-3")
        for button, name in zip(self.view._manual_stage_buttons.values(), stage_icons, strict=True):
            button.setIcon(menu_icon(name, c["muted"], 20))
            button.setIconSize(QSize(20, 20))
        self.view._manual_preset_profile_button.setIcon(menu_icon("file-settings", theme.TOOL_2, 15))
        self.view._manual_preset_profile_button.setIconSize(QSize(15, 15))
        self.view._settings_button.setIcon(interface_icon("gear", c["muted"]))
        self.view._settings_button.setIconSize(QSize(16, 16))
        self.view._credits_button.setIcon(menu_icon("arrow-up-right", c["muted"], 16))
        self.view._credits_button.setIconSize(QSize(16, 16))

    def _apply_brand_logo(self) -> None:
        logo_theme = "dark" if theme.IS_DARK else "light"
        filename = BRAND_LOGO_FILENAMES[logo_theme]
        path = resource_path("branding", filename)
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.view._home_button.setIcon(QIcon())
            return
        content_bounds = QRegion(pixmap.mask()).boundingRect()
        if content_bounds.isValid() and (not content_bounds.isEmpty()):
            pixmap = pixmap.copy(content_bounds)
        screen = QGuiApplication.primaryScreen()
        scale = max(1.0, screen.devicePixelRatio() if screen is not None else 1.0)
        scaled = pixmap.scaled(
            round(BRAND_LOGO_MAX_WIDTH * scale),
            round(BRAND_LOGO_HEIGHT * scale),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(scale)
        self.view._home_button.setIcon(QIcon(scaled))
        self.view._home_button.setIconSize(QSize(round(scaled.width() / scale), round(scaled.height() / scale)))
        self.view._brand_logo_filename = filename

    def _build_theme_actions(self, settings_menu: QMenu, initial_theme_mode: str) -> None:
        theme_group = QActionGroup(self.view)
        theme_group.setExclusive(True)
        self.view._theme_actions = {}
        for label, mode in (("Light mode", "light"), ("Dark mode", "dark")):
            action = settings_menu.addAction(label)
            action.setCheckable(True)
            action.setData(mode)
            action.setChecked(mode == initial_theme_mode)
            action.triggered.connect(
                lambda checked=False, selected_mode=mode: self._request_theme_mode(selected_mode, checked)
            )
            theme_group.addAction(action)
            self.view._theme_actions[mode] = action
        self.view._theme_action_group = theme_group

    def _request_theme_mode(self, mode: str, checked: bool) -> None:
        if checked:
            self.view.theme_mode_requested.emit(mode)
