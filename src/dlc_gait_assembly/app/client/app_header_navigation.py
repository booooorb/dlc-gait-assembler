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
    PartnerLogoLabel,
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
        primary_layout.addWidget(self.view.workflows.bar)
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
        destinations = (
            ("_manual_tools_button", "Manual", "manual", "Open the manual tools.",
             self.view.routes._open_manual_workspace),
            ("_automation_run_button", "Automated", "automated", "Run a batch with the active profile.",
             self.view.routes._show_automated_pipeline),
            ("_automation_profiles_button", "Automation settings", "profiles", "Configure the active profile.",
             self.view.routes._show_automated_profiles),
            ("_ladder_button", "Ladder", "ladder", "Open ladder analysis.",
             lambda: self.view.routes._open_tool(self.view._ladder_spec.id)),
        )
        self.view._primary_navigation_buttons = []
        for attribute, label, role, tooltip, route in destinations:
            button = QPushButton(label)
            button.setObjectName("PrimaryNavigationButton")
            button.setProperty("navigationRole", role)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tooltip)
            button.clicked.connect(route)
            navigation_layout.addWidget(button)
            setattr(self.view, attribute, button)
            self.view._primary_navigation_buttons.append(button)
        primary_layout.addWidget(primary_navigation)
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
        self._update_header_layout()

    def _update_header_layout(self) -> None:
        compact = self.view.width() < 1440
        row = self.view._primary_row
        changed = row.property("compactHeader") != compact
        row.setProperty("compactHeader", compact)
        layout = self.view._primary_layout
        layout.setContentsMargins(12 if compact else 20, 0, 12 if compact else 16, 0)
        layout.setSpacing(2 if compact else 10)
        workflows = self.view.workflows
        workflows.selector.setFixedWidth(114 if compact else 180)
        workflows.save_button.setFixedWidth(52 if compact else 60)
        workflows.bar.layout().setSpacing(2 if compact else 5)
        for button in (workflows.new_button, workflows.save_as_button, workflows.close_button):
            button.setFixedWidth(28 if compact else 30)
        style = Qt.ToolButtonIconOnly if self.view.width() < 1600 else Qt.ToolButtonTextBesideIcon
        self.view._settings_button.setToolButtonStyle(style)
        self.view._credits_button.setToolButtonStyle(style)
        partner_layout = self.view._partner_marks.layout()
        partner_layout.setContentsMargins(0 if compact else 8, 0 if compact else 4, 0 if compact else 8, 0 if compact else 4)
        partner_layout.setSpacing(4 if compact else 12)
        for logo in self.view._partner_marks.findChildren(PartnerLogoLabel):
            pixmap = logo.pixmap()
            size = pixmap.deviceIndependentSize().toSize()
            if compact:
                size.scale(40, 24, Qt.KeepAspectRatio)
            logo.setScaledContents(True)
            logo.setFixedSize(size)
        if changed:
            self._apply_navigation_icons()
            for button in row.findChildren(QPushButton) + row.findChildren(QToolButton):
                button.style().unpolish(button)
                button.style().polish(button)
                button.updateGeometry()

    def _apply_navigation_icons(self) -> None:
        self._apply_brand_logo()
        c = menu_colors(theme.IS_DARK)
        navigation_icons = (
            (self.view._manual_tools_button, "manual", theme.TOOL_3),
            (self.view._automation_run_button, "automated", theme.TOOL_1),
            (self.view._automation_profiles_button, "profiles", theme.TOOL_2),
            (self.view._ladder_button, "ladder", theme.TOOL_2),
        )
        for button, icon_name, color in navigation_icons:
            compact_option = self.view.width() < 1440 and button in (
                self.view._automation_run_button, self.view._automation_profiles_button,
                self.view._manual_tools_button,
            )
            button.setIcon(QIcon() if compact_option else navigation_icon(icon_name, color))
            button.setIconSize(QSize(18, 18))
        stage_icons = ("ruler-measure", "movie", "topology-star-3", "angle", "walk", "chart-dots-3")
        for button, name in zip(self.view._manual_stage_buttons.values(), stage_icons, strict=True):
            button.setIcon(menu_icon(name, c["muted"], 20))
            button.setIconSize(QSize(20, 20))
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
