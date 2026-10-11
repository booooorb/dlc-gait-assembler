"""Own run stylesheet rules and their original cascade positions."""

AUTOMATIC_RUN_RULES = (
    (
        13,
        """QLabel#VideoCountLabel {
    background: {theme.PANEL};
    border: 1px solid {theme.BORDER};
    border-radius: 3px;
    color: {theme.CONNECTOR};
    font-size: 11px;
    font-weight: 650;
    padding: 3px 7px;
}
""",
    ),
    (
        15,
        """QFrame#VideoDropPanel {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 5px;
}
""",
    ),
    (
        16,
        """QFrame#AutomationConsolePanel {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 5px;
}
""",
    ),
    (
        17,
        """QFrame#RunStatusBar {
    background: {theme.PANEL};
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
}
""",
    ),
    (
        18,
        """QLabel#RunStatusLabel {
    color: {theme.TEXT};
    font-size: 12px;
    font-weight: 700;
}
""",
    ),
    (
        20,
        """QLabel#RunReadinessBadge[readinessState="ready"],
QLabel#RunReadinessBadge[readinessState="complete"] {
    color: {theme.STATUS_READY};
}
""",
    ),
    (
        21,
        """QLabel#RunReadinessBadge[readinessState="running"],
QLabel#RunReadinessBadge[readinessState="review"] {
    color: {theme.STATUS_RUNNING};
}
""",
    ),
    (
        22,
        """QLabel#RunReadinessBadge[readinessState="error"] {
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        23,
        """QFrame#PipelineStatusPanel {
    background: transparent;
    border: 0;
}
""",
    ),
    (
        24,
        """QFrame#PipelineActivityPanel {
    background: transparent;
    border: 0;
}
""",
    ),
    (
        25,
        """QStackedWidget#AutomationInputStack {
    background: {theme.BACKGROUND};
    background-image: url({theme.BACKGROUND_TEXTURE});
    border: 0;
}
""",
    ),
    (
        26,
        """QFrame#PipelineStageCard {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
}
""",
    ),
    (
        27,
        """QFrame#PipelineStageCard[pipelineState="active"] {
    background: {theme.PANEL};
    border: 1px solid {theme.STATUS_RUNNING};
}
""",
    ),
    (
        28,
        """QFrame#PipelineStageCard[pipelineState="complete"] {
    background: {theme.SURFACE};
    border: 1px solid {theme.STATUS_READY};
}
""",
    ),
    (
        29,
        """QFrame#PipelineStageCard[pipelineState="skipped"] {
    background: {theme.BACKGROUND};
    border: 1px solid {theme.BORDER};
}
""",
    ),
    (
        30,
        """QFrame#PipelineStageCard[pipelineState="blocked"] {
    background: {theme.PANEL};
    border: 1px solid {theme.STATUS_ERROR};
}
""",
    ),
    (
        31,
        """QProgressBar#PipelineStageProgress {
    background: transparent;
    border: 0;
    min-width: 44px;
    max-width: 44px;
    min-height: 44px;
    max-height: 44px;
}
""",
    ),
    (
        32,
        """QLabel#PipelineStageName {
    color: {theme.TEXT};
    font-size: 13px;
    font-weight: 650;
}
""",
    ),
    (
        33,
        """QLabel#PipelineStageStatus, QLabel#PipelineVideoProgress {
    color: {theme.CONNECTOR};
    font-size: 12px;
}
""",
    ),
    (
        34,
        """QFrame#PipelineConnector {
    background: {theme.CONNECTOR};
    border: 0;
}
""",
    ),
    (
        35,
        """QLabel#PipelineCurrentStage {
    color: {theme.TEXT};
    font-size: 17px;
    font-weight: 700;
}
""",
    ),
    (
        36,
        """QLabel#PipelineStagePosition {
    color: {theme.CONNECTOR};
    font-size: 14px;
}
""",
    ),
    (
        37,
        """QProgressBar#PipelineProgressBar {
    min-height: 28px;
    text-align: center;
    font-weight: 650;
}
""",
    ),
    (
        38,
        """QProgressBar#PipelineProgressBar::chunk {
    background: {theme.PRIMARY};
}
""",
    ),
    (
        48,
        """QFrame#VideoHoverCard {
    background: {theme.SURFACE};
    border: 1px solid {theme.BORDER};
    border-radius: 5px;
}
""",
    ),
    (
        49,
        """QLabel#VideoHoverPreview {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
    border-radius: 2px;
    color: {theme.CANVAS_TEXT};
    font-size: 11px;
}
""",
    ),
    (
        50,
        """QLabel#VideoHoverName {
    color: {theme.TEXT};
    font-size: 11px;
    font-weight: 650;
}
""",
    ),
    (
        51,
        """QLabel#VideoHoverDetails {
    color: {theme.CONNECTOR};
    font-size: 10px;
}
""",
    ),
    (
        52,
        """QListWidget#AutomationVideoDropList {
    background: {theme.BACKGROUND};
    border: 2px dashed {theme.BORDER};
    border-radius: 5px;
    color: {theme.TEXT};
    padding: 8px;
    outline: 0;
}
""",
    ),
    (
        53,
        """QListWidget#AutomationVideoDropList:focus {
    border-color: {theme.TOOL_1};
}
""",
    ),
    (
        54,
        """QListWidget#AutomationVideoDropList[dropActive="true"] {
    background: {theme.PANEL};
    border-color: {theme.TOOL_1};
}
""",
    ),
    (
        55,
        """QListWidget#AutomationVideoDropList::item {
    background: {theme.SURFACE};
    border: 0;
    border-bottom: 1px solid {theme.BORDER};
    padding: 9px 10px;
}
""",
    ),
    (
        56,
        """QListWidget#AutomationVideoDropList::item:selected {
    background: {theme.SOFT};
    border-left: 3px solid {theme.TOOL_1};
}
""",
    ),
    (
        57,
        """QPlainTextEdit#AutomationConsole {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
    border-radius: 4px;
    color: {theme.CANVAS_TEXT};
    font-size: 12px;
    padding: 12px;
    selection-background-color: {theme.PANEL};
    selection-color: {theme.TEXT};
}
""",
    ),
    (
        58,
        """QLabel#PipelineLogState {
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
        59,
        """QLabel#PipelineLogState[logState="running"],
QLabel#PipelineLogState[logState="review"] {
    color: {theme.STATUS_RUNNING};
}
""",
    ),
    (
        60,
        """QLabel#PipelineLogState[logState="paused"],
QLabel#PipelineLogState[logState="error"] {
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        61,
        """QLabel#PipelineLogState[logState="ready"],
QLabel#PipelineLogState[logState="complete"] {
    color: {theme.STATUS_READY};
}
""",
    ),
    (
        62,
        """QPushButton#RunPipelineButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-size: 14px;
    font-weight: 700;
    min-width: 160px;
    padding: 9px 16px;
}
""",
    ),
    (
        63,
        """QPushButton#AddVideosButton {
    background: {theme.PRIMARY};
    border-color: {theme.PRIMARY};
    color: {theme.PRIMARY_TEXT};
    font-weight: 650;
}
""",
    ),
    (
        64,
        """QPushButton#AddVideosButton:hover {
    background: {theme.PRIMARY_HOVER};
    border-color: {theme.PRIMARY_HOVER};
    color: {theme.PRIMARY_TEXT};
}
""",
    ),
    (
        65,
        """QPushButton#RemoveButton, QPushButton#ClearButton {
    background: {theme.SURFACE};
    border: 1px solid {theme.STATUS_ERROR};
    border-radius: 2px;
    color: {theme.STATUS_ERROR};
    font-weight: 650;
}
""",
    ),
    (
        66,
        """QPushButton#RemoveButton:hover, QPushButton#ClearButton:hover {
    background: {theme.PANEL};
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        67,
        """QPushButton#RemoveButton:pressed, QPushButton#ClearButton:pressed {
    background: {theme.SOFT};
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        68,
        """QPushButton#RemoveButton:disabled, QPushButton#ClearButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.STATUS_ERROR};
    color: {theme.STATUS_ERROR};
}
""",
    ),
    (
        69,
        """QPushButton#RunPipelineButton:disabled {
    background: {theme.PANEL};
    border-color: {theme.BORDER};
    color: {theme.CONNECTOR};
}
""",
    ),
)
