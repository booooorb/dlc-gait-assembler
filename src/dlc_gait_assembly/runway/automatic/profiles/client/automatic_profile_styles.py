"""Own profile stylesheet rules and their original cascade positions."""

AUTOMATIC_PROFILE_RULES = (
    (
        0,
        """
QWidget#AutomatedPipelineProfilesWidget {
    background: {theme.BACKGROUND};
    background-image: url({theme.BACKGROUND_TEXTURE});
    color: {theme.TEXT};
}
""",
    ),
    (
        1,
        """QFrame#ProfileHeader, QFrame#MainAutomationMenu {
    background: {theme.SURFACE};
    border: 0;
    border-radius: 7px;
}
""",
    ),
    (
        2,
        """QFrame#ProfileConfigurationToolbar, QFrame#ProfileManagementPanel,
QFrame#ProfileReadinessPanel {
    background: {theme.SURFACE};
    border: 0;
    border-radius: 7px;
}
""",
    ),
    (
        3,
        """QLabel#AutomatedProfileTitle, QLabel#MainAutomationTitle,
QLabel#ProfileConfigurationTitle, QLabel#ProfileStageTitle {
    color: {theme.TEXT};
    font-size: 16px;
    font-weight: 700;
}
""",
    ),
    (
        4,
        """QLabel#AutomatedProfileTitle {
    font-size: 20px;
}
""",
    ),
    (
        5,
        """QLabel#AutomatedProfileDescription, QLabel#ProfileStageDescription,
QLabel#DetectedRegionsLabel, QLabel#ModelsPlaceholder, QLabel#ProfileStatusLabel {
    color: {theme.CONNECTOR};
    font-size: 13px;
}
""",
    ),
    (
        6,
        """QLabel#ProfileReadinessTitle {
    color: {theme.TEXT};
    font-size: 15px;
    font-weight: 650;
}
""",
    ),
    (
        7,
        """QLabel#ProfileReadinessLabel {
    color: {theme.TEXT};
    font-size: 13px;
}
""",
    ),
    (
        8,
        """QLabel#ProfileReadinessValue {
    color: {theme.CONNECTOR};
    font-size: 13px;
    font-weight: 650;
}
""",
    ),
    (
        9,
        """QLabel#ProfileReadinessValue[readinessState="ready"] {
    color: {theme.STATUS_READY};
}
""",
    ),
    (
        10,
        """QLabel#ProfileReadinessValue[readinessState="missing"] {
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        11,
        """QLabel#ProfileReadinessValue[readinessState="optional"] {
    color: {theme.CONNECTOR};
}
""",
    ),
    (
        14,
        """QLabel#FieldLabel, QLabel#RegionName {
    color: {theme.TEXT};
    font-weight: 600;
    min-width: 48px;
}
""",
    ),
    (
        19,
        """QLabel#ProfileStatusLabel, QLabel#RunReadinessBadge {
    background: transparent;
    border: 0;
    border-radius: 0;
    color: {theme.CONNECTOR};
    font-size: 11px;
    font-weight: 650;
    padding: 2px 0;
}
""",
    ),
    (
        70,
        """QTabWidget#ProfileConfigurationTabs::pane {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
}
""",
    ),
    (
        71,
        """QTabWidget#ProfileConfigurationTabs QTabBar::tab {
    background: {theme.PANEL};
}
""",
    ),
    (
        72,
        """QTabWidget#ProfileConfigurationTabs QTabBar::tab:selected {
    background: {theme.SURFACE};
    color: {theme.TEXT};
    border-bottom-color: transparent;
    font-weight: 650;
}
""",
    ),
    (
        73,
        """QScrollArea#ProfileModelsScroll {
    background: transparent;
    border: 0;
}
""",
    ),
    (
        74,
        """QWidget#ProfileStagePage {
    background: {theme.SURFACE};
}
""",
    ),
    (
        75,
        """QFrame#RegionModelRow {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
    border-radius: 2px;
}
""",
    ),
    (
        76,
        """QLabel#AssetPath {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
    border-radius: 2px;
    color: {theme.CONNECTOR};
    font-size: 12px;
    padding: 4px 6px;
}
""",
    ),
    (
        77,
        """QLabel#AssetPath:disabled {
    background: {theme.PANEL};
    color: {theme.BORDER};
}
""",
    ),
    (
        78,
        """QPushButton#NewProfileButton {
    background: {theme.PRIMARY};
    border: 1px solid {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-weight: 700;
    min-height: 22px;
    padding: 6px 11px;
}
""",
    ),
    (
        79,
        """QPushButton#NewProfileButton:hover {
    background: {theme.PRIMARY_HOVER};
    border-color: {theme.PRIMARY_HOVER};
    color: {theme.PRIMARY_TEXT};
}
""",
    ),
    (
        80,
        """QPushButton#DuplicateProfileButton {
    background: {theme.SOFT};
    border: 1px solid {theme.TOOL_1};
    color: {theme.TOOL_1};
    font-weight: 650;
    min-height: 22px;
    padding: 6px 9px;
}
""",
    ),
    (
        81,
        """QPushButton#DuplicateProfileButton:hover {
    background: {theme.SURFACE};
    border-color: {theme.TEXT};
    color: {theme.TEXT};
}
""",
    ),
    (
        82,
        """QPushButton#DuplicateProfileButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
""",
    ),
    (
        83,
        """QPushButton#DeleteProfileButton {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    color: {theme.STATUS_ERROR};
    font-weight: 650;
    min-height: 22px;
    padding: 6px 9px;
}
""",
    ),
    (
        84,
        """QPushButton#DeleteProfileButton:hover {
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        85,
        """QPushButton#DeleteProfileButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
""",
    ),
    (
        86,
        """QPushButton#OpenProfileConfigurationButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-weight: 650;
}
""",
    ),
    (
        87,
        """QPushButton#OpenProfileConfigurationButton:hover {
    background: {theme.PRIMARY_HOVER};
    border-color: {theme.PRIMARY_HOVER};
    color: {theme.PRIMARY_TEXT};
}
""",
    ),
    (
        88,
        """QPushButton#OpenManualToolButton {
    background: {theme.SOFT};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY};
    font-size: 11px;
    font-weight: 650;
}
""",
    ),
    (
        89,
        """QPushButton#OpenManualToolButton:hover {
    background: {theme.SURFACE};
    border-color: {theme.TEXT};
    color: {theme.TEXT};
}
""",
    ),
    (
        90,
        """QPushButton#ProfileUploadButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-size: 11px;
    font-weight: 650;
}
""",
    ),
    (
        91,
        """QPushButton#ProfileUploadButton:hover {
    background: {theme.SOFT};
    border-color: {theme.TEXT};
    color: {theme.TEXT};
}
""",
    ),
    (
        92,
        """QPushButton#OpenManualToolButton:disabled,
QPushButton#ProfileUploadButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
""",
    ),
    (
        93,
        """QPushButton#ProfileStageToggle {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    color: {theme.CONNECTOR};
    font-size: 12px;
    padding: 7px 12px;
}
""",
    ),
    (
        94,
        """QPushButton#ProfileStageToggle:checked {
    background: {theme.SOFT};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY};
    font-weight: 650;
}
""",
    ),
    (
        95,
        """QPushButton#BackToAutomationButton {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
    color: {theme.TEXT};
    font-weight: 650;
}
""",
    ),
    (
        96,
        """QPushButton#BackToAutomationButton:hover {
    background: {theme.SOFT};
    border-color: {theme.TOOL_1};
    color: {theme.TOOL_1};
}
""",
    ),
    (
        97,
        """QWidget#MainAutomationPage, QWidget#ProfileConfigurationPage,
QStackedWidget#AutomationWorkspaceStack {
    background: {theme.BACKGROUND};
    background-image: url({theme.BACKGROUND_TEXTURE});
}
""",
    ),
)
