"""Present parameter definitions and scientific figure explanations."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_contracts import (
    GaitParameterDefinition,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    gait_parameter_catalog,
)
from dlc_gait_assembly.runway.manual.gait_analysis.client.panels.gait_parameter_panel import display_parameter_name
from dlc_gait_assembly.runway.manual.gait_analysis.client.previews.gait_reference_catalog import (
    FigureDefinition,
    gait_figure_catalog,
)
from dlc_gait_assembly.shared.client.qt_svg_preview import ClickableSvgWidget, SvgPreviewDialog


class GaitParameterReferenceWidget(QWidget):
    def __init__(self, *, reader):
        super().__init__()
        self.setObjectName("GaitParameterReference")
        self._definitions = gait_parameter_catalog()
        self.reader = reader
        self._figure_definitions = gait_figure_catalog(reader.preview_root)
        self._visible_definitions: list[GaitParameterDefinition] = []
        self._visible_figures: list[FigureDefinition] = []
        self._selected_figure: FigureDefinition | None = None
        self._large_figure_dialog: SvgPreviewDialog | None = None
        self._build_ui()
        self._connect_signals()
        self._apply_figure_filter()
        self._apply_filter()

    def set_multiside(self, multiside: bool) -> None:
        """Show only the parameter definitions valid for the active input mode."""
        self.view_filter.setCurrentText("Multi-view" if multiside else "Single-view")

    def show_figure_documentation(self) -> None:
        self.documentation_stack.setCurrentWidget(self.figure_documentation)

    def show_parameter_documentation(self) -> None:
        self.documentation_stack.setCurrentWidget(self.parameter_documentation)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.documentation_stack = QStackedWidget()
        self.documentation_stack.setObjectName("GaitDocumentationStack")
        root.addWidget(self.documentation_stack, 1)
        self.figure_documentation = self._build_figure_documentation()
        self.parameter_documentation = QWidget()
        self.parameter_documentation.setObjectName("ParameterDocumentation")
        self.documentation_stack.addWidget(self.figure_documentation)
        self.documentation_stack.addWidget(self.parameter_documentation)
        self.show_parameter_documentation()
        documentation = QVBoxLayout(self.parameter_documentation)
        documentation.setContentsMargins(20, 18, 20, 20)
        documentation.setSpacing(10)
        title = QLabel("Gait parameter reference")
        title.setObjectName("ParameterReferenceTitle")
        documentation.addWidget(title)
        subtitle = QLabel(
            "Browse the measurements available in generated parameter tables. Select a row to see its calculation and input requirements."
        )
        subtitle.setObjectName("ParameterReferenceSubtitle")
        subtitle.setWordWrap(True)
        documentation.addWidget(subtitle)
        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("ParameterSearch")
        self.search_edit.setPlaceholderText("Search parameters, calculations, sources, or markers")
        self.search_edit.setClearButtonEnabled(True)
        controls.addWidget(self.search_edit, 1)
        self.view_filter = QComboBox()
        self.view_filter.setObjectName("ParameterViewFilter")
        self.view_filter.addItems(("All views", "Single-view", "Multi-view"))
        controls.addWidget(self.view_filter)
        self.source_filter = QComboBox()
        self.source_filter.setObjectName("ParameterSourceFilter")
        self.source_filter.addItems(("All sources", "ALMA", "RustLab1", "Custom SOP"))
        controls.addWidget(self.source_filter)
        documentation.addLayout(controls)
        self.count_label = QLabel()
        self.count_label.setObjectName("MutedLabel")
        documentation.addWidget(self.count_label)
        self.parameter_splitter = QSplitter(Qt.Horizontal)
        self.parameter_splitter.setChildrenCollapsible(False)
        documentation.addWidget(self.parameter_splitter, 1)
        self.parameter_tree = QTreeWidget()
        self.parameter_tree.setObjectName("GaitParameterTree")
        self.parameter_tree.setHeaderLabels(("#", "Parameter", "Calculation", "Source", "View type", "Required view"))
        self.parameter_tree.setRootIsDecorated(False)
        self.parameter_tree.setAlternatingRowColors(True)
        self.parameter_tree.setWordWrap(True)
        self.parameter_tree.setTextElideMode(Qt.ElideNone)
        self.parameter_tree.setUniformRowHeights(False)
        self.parameter_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.parameter_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.parameter_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.parameter_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.parameter_tree.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.parameter_tree.header().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.parameter_splitter.addWidget(self.parameter_tree)
        details = QFrame()
        details.setObjectName("ParameterDetails")
        details.setMinimumWidth(330)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(18, 18, 18, 18)
        details_layout.setSpacing(12)
        self.name_label = QLabel("Select a parameter")
        self.name_label.setObjectName("ParameterName")
        self.name_label.setWordWrap(True)
        details_layout.addWidget(self.name_label)
        calculation_heading = QLabel("Calculation")
        calculation_heading.setObjectName("ParameterDetailHeading")
        details_layout.addWidget(calculation_heading)
        self.calculation_label = QLabel()
        self.calculation_label.setObjectName("ParameterCalculationFocus")
        self.calculation_label.setWordWrap(True)
        self.calculation_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        details_layout.addWidget(self.calculation_label)
        self.identifier_label = detail_label(details_layout, "Output column")
        self.views_label = detail_label(details_layout, "Views")
        self.markers_label = detail_label(details_layout, "Required markers")
        details_layout.addStretch(1)
        self.parameter_splitter.addWidget(details)
        self.parameter_splitter.setStretchFactor(0, 4)
        self.parameter_splitter.setStretchFactor(1, 1)
        self.parameter_splitter.setSizes((1040, 340))

    def _build_figure_documentation(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("FigureDocumentation")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(10)
        heading = QLabel("Figure creator documentation")
        heading.setObjectName("FigureCreatorTitle")
        layout.addWidget(heading)
        intro = QLabel(
            "Preview every ALMA and RustLab1 figure created by the gait workflow. Each preview uses real project sample data and opens at full size when clicked. PCA and random-forest figures are excluded."
        )
        intro.setObjectName("FigureCreatorIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.figure_source_filter = QComboBox()
        self.figure_source_filter.setObjectName("FigureSourceFilter")
        self.figure_source_filter.addItems(("All figures", "ALMA", "RustLab1"))
        filter_row.addWidget(self.figure_source_filter, 1)
        self.figure_count_label = QLabel()
        self.figure_count_label.setObjectName("FigureCountLabel")
        filter_row.addWidget(self.figure_count_label)
        layout.addLayout(filter_row)
        content = QSplitter(Qt.Horizontal)
        content.setObjectName("FigureDocumentationSplitter")
        content.setChildrenCollapsible(False)
        layout.addWidget(content, 1)
        index_panel = QFrame()
        index_panel.setObjectName("FigureCreatorIndex")
        index_panel.setMinimumWidth(330)
        index_layout = QVBoxLayout(index_panel)
        index_layout.setContentsMargins(12, 12, 12, 12)
        index_layout.setSpacing(8)
        index_heading = QLabel("Available figures")
        index_heading.setObjectName("FigureIndexHeading")
        index_layout.addWidget(index_heading)
        self.figure_list = QListWidget()
        self.figure_list.setObjectName("FigureCreatorList")
        self.figure_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.figure_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.figure_list.setTextElideMode(Qt.ElideRight)
        index_layout.addWidget(self.figure_list, 1)
        content.addWidget(index_panel)
        detail_panel = QFrame()
        detail_panel.setObjectName("FigureCreatorDetails")
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(16, 14, 16, 14)
        detail_layout.setSpacing(9)
        detail_header = QHBoxLayout()
        self.figure_title_label = QLabel("Select a figure")
        self.figure_title_label.setObjectName("FigureExplanationTitle")
        self.figure_title_label.setWordWrap(True)
        detail_header.addWidget(self.figure_title_label, 1)
        self.figure_source_badge = QLabel()
        self.figure_source_badge.setObjectName("FigureSourceBadge")
        detail_header.addWidget(self.figure_source_badge)
        detail_layout.addLayout(detail_header)
        self.figure_preview = ClickableSvgWidget()
        self.figure_preview.setObjectName("FigureCreatorPreview")
        self.figure_preview.setMinimumSize(360, 210)
        self.figure_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail_layout.addWidget(self.figure_preview, 3)
        preview_actions = QHBoxLayout()
        preview_note = QLabel("Original proportions preserved")
        preview_note.setObjectName("FigurePreviewNote")
        preview_actions.addWidget(preview_note)
        preview_actions.addStretch(1)
        self.open_figure_button = QPushButton("Open large preview")
        self.open_figure_button.setObjectName("OpenFigurePreview")
        preview_actions.addWidget(self.open_figure_button)
        detail_layout.addLayout(preview_actions)
        explanation_scroll = QScrollArea()
        explanation_scroll.setObjectName("FigureExplanationScroll")
        explanation_scroll.setWidgetResizable(True)
        explanation_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        explanation_scroll.setMinimumHeight(110)
        explanation = QWidget()
        explanation_layout = QVBoxLayout(explanation)
        explanation_layout.setContentsMargins(0, 0, 7, 0)
        explanation_layout.setSpacing(6)
        self.figure_purpose_label = figure_detail_label(explanation_layout, "Purpose")
        self.figure_shows_label = figure_detail_label(explanation_layout, "What it shows")
        self.figure_interpretation_label = figure_detail_label(explanation_layout, "How to read it")
        self.figure_provenance_label = figure_detail_label(explanation_layout, "Real-data source")
        explanation_layout.addStretch(1)
        explanation_scroll.setWidget(explanation)
        detail_layout.addWidget(explanation_scroll, 1)
        self.figure_docs_button = QPushButton("Open source documentation")
        self.figure_docs_button.setObjectName("FigureDocsButton")
        detail_layout.addWidget(self.figure_docs_button)
        content.addWidget(detail_panel)
        content.setStretchFactor(0, 0)
        content.setStretchFactor(1, 1)
        content.setSizes((350, 990))
        return panel

    def _connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self._apply_filter)
        self.view_filter.currentTextChanged.connect(self._apply_filter)
        self.source_filter.currentTextChanged.connect(self._apply_filter)
        self.parameter_tree.currentItemChanged.connect(self._selection_changed)
        self.figure_source_filter.currentTextChanged.connect(self._apply_figure_filter)
        self.figure_list.currentItemChanged.connect(self._figure_selection_changed)
        self.figure_preview.clicked.connect(self._show_large_figure)
        self.open_figure_button.clicked.connect(self._show_large_figure)
        self.figure_docs_button.clicked.connect(self._open_figure_documentation)

    def _apply_figure_filter(self) -> None:
        source = self.figure_source_filter.currentText()
        current_filename = self._selected_figure.filename if self._selected_figure else ""
        self.figure_list.clear()
        self._visible_figures = []
        selected_item = None
        for figure in self._figure_definitions:
            if source != "All figures" and figure.source != source:
                continue
            self._visible_figures.append(figure)
            item = QListWidgetItem(f"{figure.source}  ·  {figure.title}")
            item.setData(Qt.UserRole, figure.filename)
            item.setToolTip(figure.purpose)
            self.figure_list.addItem(item)
            if figure.filename == current_filename:
                selected_item = item
        self.figure_count_label.setText(f"{len(self._visible_figures)} figures")
        if selected_item is None and self.figure_list.count():
            selected_item = self.figure_list.item(0)
        if selected_item is not None:
            self.figure_list.setCurrentItem(selected_item)
        else:
            self._show_figure(None)

    def _figure_selection_changed(self, current, _previous) -> None:
        if current is None:
            self._show_figure(None)
            return
        index = self.figure_list.row(current)
        figure = self._visible_figures[index] if 0 <= index < len(self._visible_figures) else None
        self._show_figure(figure)

    def _show_figure(self, figure: FigureDefinition | None) -> None:
        self._selected_figure = figure
        if figure is None:
            self.figure_title_label.setText("No matching figure")
            self.figure_source_badge.clear()
            self.figure_purpose_label.clear()
            self.figure_shows_label.clear()
            self.figure_interpretation_label.clear()
            self.figure_provenance_label.clear()
            self.open_figure_button.setEnabled(False)
            self.figure_docs_button.setEnabled(False)
            return
        self.figure_title_label.setText(figure.title)
        self.figure_source_badge.setText(figure.source)
        self.figure_purpose_label.setText(figure.purpose)
        self.figure_shows_label.setText(figure.shows)
        self.figure_interpretation_label.setText(figure.interpretation)
        self.figure_provenance_label.setText(figure.provenance)
        available = self.reader.exists(figure.asset_path)
        self.open_figure_button.setEnabled(available)
        self.figure_docs_button.setEnabled(True)
        if available:
            self.figure_preview.load(QByteArray(self.reader.svg_bytes(figure.asset_path)))

    def _show_large_figure(self) -> None:
        figure = self._selected_figure
        if figure is None or not self.reader.exists(figure.asset_path):
            return
        if self._large_figure_dialog is not None:
            self._large_figure_dialog.close()
        dialog = SvgPreviewDialog(
            f"{figure.source} · {figure.title}", ((figure.title, self.reader.svg_bytes(figure.asset_path)),), self
        )
        self._large_figure_dialog = dialog
        dialog.finished.connect(lambda _result, closed=dialog: self._figure_dialog_closed(closed))
        dialog.show()

    def _figure_dialog_closed(self, dialog: SvgPreviewDialog) -> None:
        if self._large_figure_dialog is dialog:
            self._large_figure_dialog = None

    def _open_figure_documentation(self) -> None:
        if self._selected_figure is not None:
            QDesktopServices.openUrl(QUrl(self._selected_figure.documentation_url))

    def _apply_filter(self) -> None:
        query_terms = self.search_edit.text().strip().casefold().split()
        view_filter = self.view_filter.currentText()
        source_filter = self.source_filter.currentText()
        current_item = self.parameter_tree.currentItem()
        selected_name = current_item.data(0, Qt.UserRole) if current_item else ""
        self.parameter_tree.clear()
        self._visible_definitions = []
        selected_item = None
        for catalog_index, definition in enumerate(self._definitions, start=1):
            if view_filter != "All views" and definition.view_mode != view_filter:
                continue
            if source_filter != "All sources" and definition.source != source_filter:
                continue
            display_name = definition.display_name or display_parameter_name(definition.name)
            searchable = " ".join(
                (
                    str(catalog_index),
                    definition.name,
                    definition.source,
                    definition.view_mode,
                    definition.views,
                    definition.markers,
                    definition.calculation,
                    display_name,
                )
            ).casefold()
            if any(term not in searchable for term in query_terms):
                continue
            self._visible_definitions.append(definition)
            item = QTreeWidgetItem(
                (
                    str(catalog_index),
                    display_name,
                    definition.calculation,
                    definition.source,
                    definition.view_mode,
                    definition.views,
                )
            )
            item.setData(0, Qt.UserRole, definition.name)
            item.setToolTip(1, definition.name)
            item.setToolTip(2, definition.calculation)
            line_count = min(3, max(1, (len(definition.calculation) + 54) // 55))
            item.setSizeHint(2, QSize(0, 22 + (line_count - 1) * 16))
            self.parameter_tree.addTopLevelItem(item)
            if definition.name == selected_name:
                selected_item = item
        total = sum(
            (view_filter == "All views" or definition.view_mode == view_filter)
            and (source_filter == "All sources" or definition.source == source_filter)
            for definition in self._definitions
        )
        self.count_label.setText(f"Showing {len(self._visible_definitions)} of {total} gait parameters")
        if selected_item is None and self.parameter_tree.topLevelItemCount():
            selected_item = self.parameter_tree.topLevelItem(0)
        if selected_item is not None:
            self.parameter_tree.setCurrentItem(selected_item)
        else:
            self._show_definition(None)

    def _selection_changed(self, current, _previous) -> None:
        if current is None:
            self._show_definition(None)
            return
        index = self.parameter_tree.indexOfTopLevelItem(current)
        definition = self._visible_definitions[index] if 0 <= index < len(self._visible_definitions) else None
        self._show_definition(definition)

    def _show_definition(self, definition: GaitParameterDefinition | None) -> None:
        if definition is None:
            self.name_label.setText("No matching parameter")
            self.identifier_label.clear()
            self.views_label.clear()
            self.markers_label.clear()
            self.calculation_label.clear()
            return
        self.name_label.setText(definition.display_name or display_parameter_name(definition.name))
        self.identifier_label.setText(definition.name)
        self.views_label.setText(definition.views)
        self.markers_label.setText(definition.markers)
        self.calculation_label.setText(definition.calculation)


def detail_label(layout: QVBoxLayout, title: str) -> QLabel:
    heading = QLabel(title)
    heading.setObjectName("ParameterDetailHeading")
    layout.addWidget(heading)
    value = QLabel()
    value.setObjectName("ParameterDetailValue")
    value.setWordWrap(True)
    value.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(value)
    return value


def figure_detail_label(layout: QVBoxLayout, title: str) -> QLabel:
    heading = QLabel(title)
    heading.setObjectName("FigureDetailHeading")
    layout.addWidget(heading)
    value = QLabel()
    value.setObjectName("FigureDetailValue")
    value.setWordWrap(True)
    value.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(value)
    return value
