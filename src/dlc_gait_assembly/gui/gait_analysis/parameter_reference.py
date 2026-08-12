from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.services.pipeline.gait_parameter_catalog import (
    GaitParameterDefinition,
    gait_parameter_catalog,
)


class GaitParameterReferenceWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("GaitParameterReference")
        self._definitions = gait_parameter_catalog()
        self._visible_definitions: list[GaitParameterDefinition] = []
        self._build_ui()
        self._connect_signals()
        self._apply_filter()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        controls = QHBoxLayout()
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
        root.addLayout(controls)

        self.count_label = QLabel()
        self.count_label.setObjectName("MutedLabel")
        root.addWidget(self.count_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        self.parameter_tree = QTreeWidget()
        self.parameter_tree.setObjectName("GaitParameterTree")
        self.parameter_tree.setHeaderLabels(("#", "Parameter", "Calculation", "Source", "View type", "Required view"))
        self.parameter_tree.setRootIsDecorated(False)
        self.parameter_tree.setAlternatingRowColors(True)
        self.parameter_tree.setWordWrap(True)
        self.parameter_tree.setTextElideMode(Qt.ElideNone)
        self.parameter_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.parameter_tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.parameter_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.parameter_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.parameter_tree.header().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.parameter_tree.header().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        splitter.addWidget(self.parameter_tree)

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
        self.badge_label = QLabel()
        self.badge_label.setObjectName("ParameterBadge")
        self.badge_label.setWordWrap(True)
        details_layout.addWidget(self.badge_label)
        self.views_label = _detail_label(details_layout, "Views")
        self.markers_label = _detail_label(details_layout, "Required markers")
        details_layout.addStretch(1)
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((1040, 340))

    def _connect_signals(self) -> None:
        self.search_edit.textChanged.connect(self._apply_filter)
        self.view_filter.currentTextChanged.connect(self._apply_filter)
        self.source_filter.currentTextChanged.connect(self._apply_filter)
        self.parameter_tree.currentItemChanged.connect(self._selection_changed)

    def _apply_filter(self) -> None:
        query = self.search_edit.text().strip().casefold()
        view_filter = self.view_filter.currentText()
        source_filter = self.source_filter.currentText()
        selected_name = self.parameter_tree.currentItem().text(1) if self.parameter_tree.currentItem() else ""
        self.parameter_tree.clear()
        self._visible_definitions = []
        selected_item = None
        for catalog_index, definition in enumerate(self._definitions, start=1):
            if view_filter != "All views" and definition.view_mode != view_filter:
                continue
            if source_filter != "All sources" and definition.source != source_filter:
                continue
            searchable = " ".join(
                (
                    str(catalog_index),
                    definition.name,
                    definition.source,
                    definition.view_mode,
                    definition.views,
                    definition.markers,
                    definition.calculation,
                )
            ).casefold()
            if query and query not in searchable:
                continue
            self._visible_definitions.append(definition)
            item = QTreeWidgetItem(
                (
                    str(catalog_index),
                    definition.name,
                    definition.calculation,
                    definition.source,
                    definition.view_mode,
                    definition.views,
                )
            )
            item.setToolTip(1, definition.name)
            item.setToolTip(2, definition.calculation)
            line_count = min(3, max(1, (len(definition.calculation) + 54) // 55))
            item.setSizeHint(2, QSize(0, 22 + (line_count - 1) * 16))
            self.parameter_tree.addTopLevelItem(item)
            if definition.name == selected_name:
                selected_item = item
        total = len(self._definitions)
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
            self.badge_label.clear()
            self.views_label.clear()
            self.markers_label.clear()
            self.calculation_label.clear()
            return
        self.name_label.setText(definition.name)
        self.badge_label.setText(f"{definition.source}  •  {definition.view_mode}")
        self.views_label.setText(definition.views)
        self.markers_label.setText(definition.markers)
        self.calculation_label.setText(definition.calculation)


def _detail_label(layout: QVBoxLayout, title: str) -> QLabel:
    heading = QLabel(title)
    heading.setObjectName("ParameterDetailHeading")
    layout.addWidget(heading)
    value = QLabel()
    value.setObjectName("ParameterDetailValue")
    value.setWordWrap(True)
    value.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(value)
    return value


class GaitParameterSelectionWidget(QWidget):
    def __init__(self, enabled_parameter_names: tuple[str, ...] | None = None):
        super().__init__()
        self.setObjectName("GaitParameterSelection")
        self._definitions = gait_parameter_catalog()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.clear_button = QPushButton("Disable all")
        controls.addWidget(self.select_all_button)
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)
        self.count_label = QLabel()
        self.count_label.setObjectName("MutedLabel")
        layout.addWidget(self.count_label)
        guidance = QLabel("Unchecked parameters are excluded from generated parameter tables and downstream analysis.")
        guidance.setObjectName("MutedLabel")
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        self.tree = QTreeWidget()
        self.tree.setObjectName("GaitParameterSelectionTree")
        self.tree.setHeaderLabels(("#", "Parameter", "Source"))
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        enabled = set(enabled_parameter_names) if enabled_parameter_names is not None else None
        for index, definition in enumerate(self._definitions, start=1):
            item = QTreeWidgetItem((str(index), definition.name, definition.source))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                1,
                Qt.Checked if enabled is None or definition.name in enabled else Qt.Unchecked,
            )
            item.setToolTip(1, definition.calculation)
            self.tree.addTopLevelItem(item)
        layout.addWidget(self.tree, 1)
        self.select_all_button.clicked.connect(lambda: self._set_all(Qt.Checked))
        self.clear_button.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        self.tree.itemChanged.connect(self._update_count)
        self._update_count()

    def enabled_parameter_names(self) -> tuple[str, ...]:
        return tuple(
            self.tree.topLevelItem(index).text(1)
            for index in range(self.tree.topLevelItemCount())
            if self.tree.topLevelItem(index).checkState(1) == Qt.Checked
        )

    def _set_all(self, state: Qt.CheckState) -> None:
        self.tree.blockSignals(True)
        for index in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(index).setCheckState(1, state)
        self.tree.blockSignals(False)
        self._update_count()

    def _update_count(self, *_args) -> None:
        self.count_label.setText(
            f"{len(self.enabled_parameter_names())} of {len(self._definitions)} parameters enabled"
        )


__all__ = ["GaitParameterReferenceWidget", "GaitParameterSelectionWidget"]
