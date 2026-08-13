from pathlib import Path


def _background_texture_url() -> str:
    from dlc_gait_assembly.gui import theme

    filename = "carbon-dark.png" if theme.IS_DARK else "carbon-light.png"
    return (Path(__file__).resolve().parents[4] / "assets" / "images" / "backgrounds" / filename).as_posix()


def application_stylesheet() -> str:
    return stylesheet(
        """
        QWidget {
            font-family: "Noto Sans";
            font-size: 13px;
        }
        QToolTip {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            padding: 5px 7px;
        }
        QMenuBar, QMenu {
            background: {theme.SURFACE};
            color: {theme.TEXT};
        }
        QMenu {
            border: 1px solid {theme.BORDER};
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 22px 6px 8px;
        }
        QMenuBar::item:selected, QMenu::item:selected {
            background: {theme.PANEL};
            color: {theme.TEXT};
        }
        QMenu::separator {
            background: {theme.BORDER};
            height: 1px;
            margin: 4px 8px;
        }
        QDialog, QMessageBox {
            background: {theme.BACKGROUND};
            background-image: url({theme.BACKGROUND_TEXTURE});
            color: {theme.TEXT};
        }
        QPushButton, QToolButton {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            padding: 7px 10px;
            min-height: 20px;
        }
        QPushButton:hover, QToolButton:hover {
            background: {theme.PANEL};
            border-color: {theme.CONNECTOR};
        }
        QPushButton:pressed, QToolButton:pressed {
            background: {theme.SOFT};
        }
        QPushButton:disabled, QToolButton:disabled {
            background: {theme.PANEL};
            color: {theme.CONNECTOR};
            border-color: {theme.BORDER};
        }
        QPushButton#PrimaryButton, QPushButton#ExportButton {
            background: {theme.PRIMARY};
            border-color: {theme.PRIMARY};
            color: {theme.PRIMARY_TEXT};
            font-weight: 600;
        }
        QPushButton#PrimaryButton:hover, QPushButton#ExportButton:hover {
            background: {theme.PRIMARY_HOVER};
            border-color: {theme.PRIMARY_HOVER};
            color: {theme.PRIMARY_TEXT};
        }
        QPushButton#PrimaryButton:disabled, QPushButton#ExportButton:disabled {
            background: {theme.PANEL};
            border-color: {theme.BORDER};
            color: {theme.CONNECTOR};
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
        QSpinBox, QDoubleSpinBox, QListWidget, QTreeWidget, QTableWidget {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 3px;
            padding: 5px 7px;
            selection-background-color: {theme.SOFT};
            selection-color: {theme.TEXT};
        }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
            min-height: 20px;
        }
        QListWidget::item, QTreeWidget::item, QTableWidget::item {
            padding: 4px 6px;
        }
        QListWidget::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {
            background: {theme.PANEL};
        }
        QGroupBox {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 4px;
            margin-top: 14px;
            padding: 14px 10px 10px 10px;
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 8px;
            padding: 0 4px;
            background: {theme.SURFACE};
            color: {theme.TEXT};
        }
        QTabWidget::pane {
            background: {theme.SURFACE};
            border: 1px solid {theme.BORDER};
            border-radius: 0;
            top: -1px;
        }
        QTabBar::tab {
            background: transparent;
            color: {theme.CONNECTOR};
            border: 0;
            border-bottom: 2px solid transparent;
            padding: 8px 12px;
        }
        QTabBar::tab:hover {
            color: {theme.TEXT};
            background: {theme.PANEL};
        }
        QTabBar::tab:selected {
            color: {theme.TEXT};
            border-bottom-color: {theme.TOOL_1};
            font-weight: 600;
        }
        QHeaderView::section {
            background: {theme.PANEL};
            color: {theme.TEXT};
            border: 0;
            border-right: 1px solid {theme.BORDER};
            border-bottom: 1px solid {theme.BORDER};
            padding: 7px 8px;
            font-weight: 600;
            text-align: left;
        }
        QProgressBar {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            border-radius: 3px;
            min-height: 18px;
            text-align: center;
        }
        QProgressBar::chunk {
            background: {theme.TOOL_1};
            border-radius: 1px;
        }
        QScrollArea {
            border: 0;
            background: transparent;
        }
        QSplitter::handle {
            background: {theme.BORDER};
            width: 1px;
            height: 1px;
        }
        QCheckBox, QRadioButton {
            color: {theme.TEXT};
            spacing: 6px;
        }
        QCheckBox::indicator, QRadioButton::indicator {
            width: 16px;
            height: 16px;
        }
        QComboBox QAbstractItemView {
            background: {theme.SURFACE};
            color: {theme.TEXT};
            border: 1px solid {theme.BORDER};
            selection-background-color: {theme.SOFT};
            selection-color: {theme.TEXT};
        }
        QScrollBar:vertical {
            background: transparent;
            width: 10px;
            margin: 2px;
        }
        QScrollBar:horizontal {
            background: transparent;
            height: 10px;
            margin: 2px;
        }
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
            background: {theme.BORDER};
            border-radius: 2px;
            min-height: 24px;
            min-width: 24px;
        }
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
            background: {theme.CONNECTOR};
        }
        QScrollBar::add-line, QScrollBar::sub-line,
        QScrollBar::add-page, QScrollBar::sub-page {
            background: transparent;
            border: 0;
            width: 0;
            height: 0;
        }
        QSlider::groove:horizontal {
            height: 5px;
            border: 1px solid {theme.BORDER};
            border-radius: 2px;
            background: {theme.PANEL};
        }
        QSlider::handle:horizontal {
            width: 14px;
            margin: -5px 0;
            border: 1px solid {theme.TEXT};
            border-radius: 3px;
            background: {theme.SURFACE};
        }
        QSlider::handle:horizontal:hover {
            background: {theme.SOFT};
        }
        QPushButton:focus, QToolButton:focus,
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QListWidget:focus {
            border: 1px solid {theme.TOOL_1};
        }
        """
    )


def workspace_stylesheet(root_object_name: str, extra: str = "") -> str:
    """Shared visual contract for every full-size tool workspace."""

    base = """
        QWidget#ROOT_OBJECT {
            background: {theme.BACKGROUND};
            background-image: url({theme.BACKGROUND_TEXTURE});
            color: {theme.TEXT};
            font-size: 13px;
        }
        QLabel {
            background: transparent;
            color: {theme.TEXT};
        }
        QLabel#TitleLabel, QLabel#PreviewTitle {
            color: {theme.TEXT};
            font-size: 16px;
            font-weight: 650;
        }
        QLabel#MutedLabel, QLabel#StatusLabel, QLabel#SettingsPlaceholder,
        QLabel#DimensionLabel {
            color: {theme.CONNECTOR};
            font-size: 12px;
        }
        QWidget#WorkspaceSidebar {
            background: {theme.PANEL};
            border: 0;
            border-radius: 7px;
        }
        QWidget#WorkspaceCanvas {
            background: {theme.BACKGROUND};
            background-image: url({theme.BACKGROUND_TEXTURE});
            border: 0;
            border-radius: 7px;
        }
        QWidget#WorkspaceHeader {
            background: {theme.SURFACE};
            border: 0;
            border-radius: 7px;
        }
        QFrame#OperationsBar, QFrame#TerminalToolbar {
            background: {theme.SURFACE};
            border: 0;
            border-radius: 7px;
        }
        QFrame#InlineSettings, QFrame#MarkerGapInline {
            background: transparent;
            border: 0;
        }
        QPushButton#RemoveButton, QPushButton#ClearButton,
        QPushButton#DeleteButton {
            background: {theme.SURFACE};
            border-color: {theme.STATUS_ERROR};
            border-radius: 2px;
            color: {theme.STATUS_ERROR};
            font-weight: 600;
        }
        QPushButton#RemoveButton:hover, QPushButton#ClearButton:hover,
        QPushButton#DeleteButton:hover {
            background: {theme.PANEL};
            border-color: {theme.STATUS_ERROR};
            color: {theme.STATUS_ERROR};
        }
    """.replace("ROOT_OBJECT", root_object_name)
    return stylesheet(base + extra)


def stylesheet(template: str) -> str:
    from dlc_gait_assembly.gui import theme

    return (
        template.replace(
            "{theme.mix_hex(theme.SOFT, theme.SURFACE, 0.35)}", theme.mix_hex(theme.SOFT, theme.SURFACE, 0.35)
        )
        .replace("{theme.BACKGROUND_TEXTURE}", _background_texture_url())
        .replace("{theme.BACKGROUND}", theme.BACKGROUND)
        .replace("{theme.SURFACE}", theme.SURFACE)
        .replace("{theme.PANEL}", theme.PANEL)
        .replace("{theme.SOFT}", theme.SOFT)
        .replace("{theme.BORDER}", theme.BORDER)
        .replace("{theme.ACCENT}", theme.ACCENT)
        .replace("{theme.TEXT}", theme.TEXT)
        .replace("{theme.CONNECTOR}", theme.CONNECTOR)
        .replace("{theme.PRIMARY}", theme.PRIMARY)
        .replace("{theme.PRIMARY_HOVER}", theme.PRIMARY_HOVER)
        .replace("{theme.PRIMARY_TEXT}", theme.PRIMARY_TEXT)
        .replace("{theme.CANVAS}", theme.CANVAS)
        .replace("{theme.CANVAS_TEXT}", theme.CANVAS_TEXT)
        .replace("{theme.BRAND_SURFACE}", theme.BRAND_SURFACE)
        .replace("{theme.STATUS_READY}", theme.STATUS_READY)
        .replace("{theme.STATUS_RUNNING}", theme.STATUS_RUNNING)
        .replace("{theme.STATUS_ERROR}", theme.STATUS_ERROR)
        .replace("{theme.STATUS_OTHER}", theme.STATUS_OTHER)
        .replace("{theme.TOOL_1}", theme.TOOL_1)
        .replace("{theme.TOOL_2}", theme.TOOL_2)
        .replace("{theme.TOOL_3}", theme.TOOL_3)
        .replace("{theme.NUMBER_ICON}", theme.NUMBER_ICON)
        .replace("{theme.LIGHT}", theme.LIGHT)
        .replace("{theme.PALE}", theme.PALE)
        .replace("{theme.MID}", theme.MID)
        .replace("{theme.DARK}", theme.DARK)
    )
