from dlc_gait_assembly.gui import theme

AUTOMATED_PIPELINE_QSS = """
QWidget#AutomatedPipelineProfilesWidget {
    background: {theme.BACKGROUND};
    background-image: url({theme.BACKGROUND_TEXTURE});
    color: {theme.TEXT};
}
QFrame#ProfileHeader, QFrame#MainAutomationMenu {
    background: {theme.SURFACE};
    border: 0;
    border-radius: 7px;
}
QFrame#ProfileConfigurationToolbar, QFrame#ProfileManagementPanel,
QFrame#ProfileReadinessPanel {
    background: {theme.SURFACE};
    border: 0;
    border-radius: 7px;
}
QLabel#AutomatedProfileTitle, QLabel#MainAutomationTitle,
QLabel#ProfileConfigurationTitle, QLabel#ProfileStageTitle {
    color: {theme.TEXT};
    font-size: 16px;
    font-weight: 700;
}
QLabel#AutomatedProfileTitle {
    font-size: 20px;
}
QLabel#AutomatedProfileDescription, QLabel#ProfileStageDescription,
QLabel#DetectedRegionsLabel, QLabel#ModelsPlaceholder, QLabel#ProfileStatusLabel {
    color: {theme.CONNECTOR};
    font-size: 13px;
}
QLabel#ProfileReadinessTitle {
    color: {theme.TEXT};
    font-size: 15px;
    font-weight: 650;
}
QLabel#ProfileReadinessLabel {
    color: {theme.TEXT};
    font-size: 13px;
}
QLabel#ProfileReadinessValue {
    color: {theme.CONNECTOR};
    font-size: 13px;
    font-weight: 650;
}
QLabel#ProfileReadinessValue[readinessState="ready"] {
    color: {theme.STATUS_READY};
}
QLabel#ProfileReadinessValue[readinessState="missing"] {
    color: {theme.STATUS_ERROR};
}
QLabel#ProfileReadinessValue[readinessState="optional"] {
    color: {theme.CONNECTOR};
}
QLabel#AutomationPanelTitle {
    color: {theme.TEXT};
    font-size: 15px;
    font-weight: 700;
}
QLabel#VideoCountLabel {
    background: {theme.PANEL};
    border: 1px solid {theme.BORDER};
    border-radius: 3px;
    color: {theme.CONNECTOR};
    font-size: 11px;
    font-weight: 650;
    padding: 3px 7px;
}
QLabel#FieldLabel, QLabel#RegionName {
    color: {theme.TEXT};
    font-weight: 600;
    min-width: 48px;
}
QFrame#VideoDropPanel {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 5px;
}
QFrame#AutomationConsolePanel {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 5px;
}
QFrame#RunStatusBar {
    background: {theme.PANEL};
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
}
QLabel#RunStatusLabel {
    color: {theme.TEXT};
    font-size: 12px;
    font-weight: 700;
}
QLabel#ProfileStatusLabel, QLabel#RunReadinessBadge {
    background: transparent;
    border: 0;
    border-radius: 0;
    color: {theme.CONNECTOR};
    font-size: 11px;
    font-weight: 650;
    padding: 2px 0;
}
QLabel#RunReadinessBadge[readinessState="ready"],
QLabel#RunReadinessBadge[readinessState="complete"] {
    color: {theme.STATUS_READY};
}
QLabel#RunReadinessBadge[readinessState="running"],
QLabel#RunReadinessBadge[readinessState="review"] {
    color: {theme.STATUS_RUNNING};
}
QLabel#RunReadinessBadge[readinessState="error"] {
    color: {theme.STATUS_ERROR};
}
QFrame#PipelineStatusPanel {
    background: transparent;
    border: 0;
}
QFrame#PipelineActivityPanel {
    background: transparent;
    border: 0;
}
QStackedWidget#AutomationInputStack {
    background: {theme.BACKGROUND};
    background-image: url({theme.BACKGROUND_TEXTURE});
    border: 0;
}
QFrame#PipelineStageCard {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
}
QFrame#PipelineStageCard[pipelineState="active"] {
    background: {theme.PANEL};
    border: 1px solid {theme.STATUS_RUNNING};
}
QFrame#PipelineStageCard[pipelineState="complete"] {
    background: {theme.SURFACE};
    border: 1px solid {theme.STATUS_READY};
}
QFrame#PipelineStageCard[pipelineState="skipped"] {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
}
QFrame#PipelineStageCard[pipelineState="blocked"] {
    background: {theme.PANEL};
    border: 1px solid {theme.STATUS_ERROR};
}
QProgressBar#PipelineStageProgress {
    background: transparent;
    border: 0;
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
}
QLabel#PipelineStageName {
    color: {theme.TEXT};
    font-size: 13px;
    font-weight: 650;
}
QLabel#PipelineStageStatus, QLabel#PipelineVideoProgress {
    color: {theme.CONNECTOR};
    font-size: 12px;
}
QFrame#PipelineConnector {
    background: {theme.CONNECTOR};
    border: 0;
}
QLabel#PipelineCurrentStage {
    color: {theme.TEXT};
    font-size: 17px;
    font-weight: 700;
}
QLabel#PipelineStagePosition {
    color: {theme.CONNECTOR};
    font-size: 14px;
}
QProgressBar#PipelineProgressBar {
    min-height: 28px;
    text-align: center;
    font-weight: 650;
}
QProgressBar#PipelineProgressBar::chunk {
    background: {theme.PRIMARY};
}
QFrame#PipelineReviewPanel {
    background: {theme.SURFACE};
    border: 1px solid {theme.PRIMARY};
    border-radius: 3px;
}
QStackedWidget#PipelineReviewPreviewStack,
QListWidget#PipelineReviewVideoList,
QLabel#PipelineStickplotPreview {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
    color: {theme.CANVAS_TEXT};
    font-size: 10px;
}
QListWidget#PipelineReviewVideoList::item {
    background: {theme.CANVAS};
    color: {theme.CANVAS_TEXT};
    padding: 6px;
    border-bottom: 1px solid {theme.BORDER};
}
QListWidget#PipelineReviewVideoList::item:selected {
    background: {theme.SOFT};
    color: {theme.TEXT};
}
QTabWidget#PipelineComponentTabs::pane {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
}
QTabWidget#PipelineComponentTabs QTabBar::tab {
    padding: 4px 8px;
    font-size: 10px;
}
QLabel#PipelineReviewTitle {
    color: {theme.TEXT};
    font-size: 15px;
    font-weight: 700;
}
QLabel#PipelineReviewDescription {
    color: {theme.CONNECTOR};
    font-size: 13px;
}
QFrame#VideoHoverCard {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 5px;
}
QLabel#VideoHoverPreview {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
    border-radius: 2px;
    color: {theme.CANVAS_TEXT};
    font-size: 11px;
}
QLabel#VideoHoverName {
    color: {theme.TEXT};
    font-size: 11px;
    font-weight: 650;
}
QLabel#VideoHoverDetails {
    color: {theme.CONNECTOR};
    font-size: 10px;
}
QListWidget#AutomationVideoDropList {
    background: {theme.BACKGROUND};
    border: 2px dashed {theme.BORDER};
    border-radius: 5px;
    color: {theme.TEXT};
    padding: 8px;
    outline: 0;
}
QListWidget#AutomationVideoDropList:focus {
    border-color: {theme.TOOL_1};
}
QListWidget#AutomationVideoDropList[dropActive="true"] {
    background: {theme.PANEL};
    border-color: {theme.TOOL_1};
}
QListWidget#AutomationVideoDropList::item {
    background: {theme.SURFACE};
    border: 0;
    border-bottom: 1px solid {theme.BORDER};
    padding: 9px 10px;
}
QListWidget#AutomationVideoDropList::item:selected {
    background: {theme.SOFT};
    border-left: 3px solid {theme.TOOL_1};
}
QPlainTextEdit#AutomationConsole {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
    color: {theme.CANVAS_TEXT};
    font-size: 12px;
    padding: 12px;
    selection-background-color: {theme.PANEL};
    selection-color: {theme.TEXT};
}
QLabel#PipelineLogState {
    background: transparent;
    border: 0;
    border-radius: 0;
    color: {theme.CONNECTOR};
    font-size: 11px;
    font-weight: 650;
    padding: 2px 0;
}
QLabel#PipelineLogState[logState="running"],
QLabel#PipelineLogState[logState="review"] {
    color: {theme.STATUS_RUNNING};
}
QLabel#PipelineLogState[logState="paused"],
QLabel#PipelineLogState[logState="error"] {
    color: {theme.STATUS_ERROR};
}
QLabel#PipelineLogState[logState="ready"],
QLabel#PipelineLogState[logState="complete"] {
    color: {theme.STATUS_READY};
}
QPushButton#RunPipelineButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-size: 14px;
    font-weight: 700;
    min-width: 160px;
    padding: 9px 16px;
}
QPushButton#AddVideosButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-weight: 650;
}
QPushButton#AddVideosButton:hover {
    background: {theme.PRIMARY_HOVER};
    border-color: {theme.PRIMARY_HOVER};
    color: {theme.PRIMARY_TEXT};
}
QPushButton#RemoveButton, QPushButton#ClearButton {
    background: {theme.SURFACE};
    border: 1px solid {theme.STATUS_ERROR};
    border-radius: 2px;
    color: {theme.STATUS_ERROR};
    font-weight: 650;
}
QPushButton#RemoveButton:hover, QPushButton#ClearButton:hover {
    background: {theme.PANEL};
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
QPushButton#RemoveButton:pressed, QPushButton#ClearButton:pressed {
    background: {theme.SOFT};
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
QPushButton#RemoveButton:disabled, QPushButton#ClearButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
QPushButton#RunPipelineButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
QTabWidget#ProfileConfigurationTabs::pane {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
}
QTabWidget#ProfileConfigurationTabs QTabBar::tab {
    background: {theme.PANEL};
}
QTabWidget#ProfileConfigurationTabs QTabBar::tab:selected {
    background: {theme.SURFACE};
    color: {theme.TEXT};
    border-bottom-color: transparent;
    font-weight: 650;
}
QScrollArea#ProfileModelsScroll {
    background: transparent;
    border: 0;
}
QWidget#ProfileStagePage {
    background: {theme.SURFACE};
}
QFrame#RegionModelRow {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
    border-radius: 2px;
}
QLabel#AssetPath {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
    border-radius: 2px;
    color: {theme.CONNECTOR};
    font-size: 12px;
    padding: 4px 6px;
}
QLabel#AssetPath:disabled {
    background: {theme.PANEL};
    color: {theme.BORDER};
}
QPushButton#NewProfileButton {
    background: {theme.PRIMARY};
    border: 1px solid {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-weight: 700;
    min-height: 22px;
    padding: 6px 11px;
}
QPushButton#NewProfileButton:hover {
    background: {theme.PRIMARY_HOVER};
    border-color: {theme.PRIMARY_HOVER};
    color: {theme.PRIMARY_TEXT};
}
QPushButton#DuplicateProfileButton {
    background: {theme.SOFT};
    border: 1px solid {theme.TOOL_1};
    color: {theme.TOOL_1};
    font-weight: 650;
    min-height: 22px;
    padding: 6px 9px;
}
QPushButton#DuplicateProfileButton:hover {
    background: {theme.SURFACE};
    border-color: {theme.TEXT};
    color: {theme.TEXT};
}
QPushButton#DuplicateProfileButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
QPushButton#DeleteProfileButton {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    color: {theme.STATUS_ERROR};
    font-weight: 650;
    min-height: 22px;
    padding: 6px 9px;
}
QPushButton#DeleteProfileButton:hover {
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
QPushButton#DeleteProfileButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
QPushButton#OpenProfileConfigurationButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-weight: 650;
}
QPushButton#OpenProfileConfigurationButton:hover {
    background: {theme.PRIMARY_HOVER};
    border-color: {theme.PRIMARY_HOVER};
    color: {theme.PRIMARY_TEXT};
}
QPushButton#OpenManualToolButton {
    background: {theme.SOFT};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY};
    font-size: 11px;
    font-weight: 650;
}
QPushButton#OpenManualToolButton:hover {
    background: {theme.SURFACE};
    border-color: {theme.TEXT};
    color: {theme.TEXT};
}
QPushButton#ProfileUploadButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-size: 11px;
    font-weight: 650;
}
QPushButton#ProfileUploadButton:hover {
    background: {theme.SOFT};
    border-color: {theme.TEXT};
    color: {theme.TEXT};
}
QPushButton#OpenManualToolButton:disabled,
QPushButton#ProfileUploadButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
QPushButton#ProfileStageToggle {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    color: {theme.CONNECTOR};
    font-size: 12px;
    padding: 7px 12px;
}
QPushButton#ProfileStageToggle:checked {
    background: {theme.SOFT};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY};
    font-weight: 650;
}
QPushButton#BackToAutomationButton {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
    color: {theme.TEXT};
    font-weight: 650;
}
QPushButton#BackToAutomationButton:hover {
    background: {theme.SOFT};
    border-color: {theme.TOOL_1};
    color: {theme.TOOL_1};
}
QWidget#MainAutomationPage, QWidget#ProfileConfigurationPage,
QStackedWidget#AutomationWorkspaceStack {
    background: {theme.BACKGROUND};
    background-image: url({theme.BACKGROUND_TEXTURE});
}
"""


def automated_pipeline_stylesheet() -> str:
    return theme.stylesheet(AUTOMATED_PIPELINE_QSS)
