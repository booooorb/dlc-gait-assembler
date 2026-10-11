"""Own review stylesheet rules and their original cascade positions."""

AUTOMATIC_REVIEW_RULES = (
    (
        39,
        """QFrame#PipelineReviewPanel {
    background: {theme.SURFACE};
    border: 1px solid {theme.PRIMARY};
    border-radius: 3px;
}
""",
    ),
    (
        40,
        """QStackedWidget#PipelineReviewPreviewStack,
QListWidget#PipelineReviewVideoList,
QLabel#PipelineStickplotPreview {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
    color: {theme.CANVAS_TEXT};
    font-size: 10px;
}
""",
    ),
    (
        41,
        """QLabel#PipelineStickplotPreview {
    background: white;
}
""",
    ),
    (
        42,
        """QListWidget#PipelineReviewVideoList::item {
    background: {theme.CANVAS};
    color: {theme.CANVAS_TEXT};
    padding: 6px;
    border-bottom: 1px solid {theme.BORDER};
}
""",
    ),
    (
        43,
        """QListWidget#PipelineReviewVideoList::item:selected {
    background: {theme.SOFT};
    color: {theme.TEXT};
}
""",
    ),
    (
        44,
        """QTabWidget#PipelineComponentTabs::pane {
    background: {theme.CANVAS};
    border: 1px solid {theme.BORDER};
}
""",
    ),
    (
        45,
        """QTabWidget#PipelineComponentTabs QTabBar::tab {
    padding: 4px 8px;
    font-size: 10px;
}
""",
    ),
    (
        46,
        """QLabel#PipelineReviewTitle {
    color: {theme.TEXT};
    font-size: 15px;
    font-weight: 700;
}
""",
    ),
    (
        47,
        """QLabel#PipelineReviewDescription {
    color: {theme.CONNECTOR};
    font-size: 13px;
}
""",
    ),
)
