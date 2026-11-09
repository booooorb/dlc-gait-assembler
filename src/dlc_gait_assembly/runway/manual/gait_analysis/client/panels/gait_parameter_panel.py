"""Present selectable measurements by source, limb scope, and availability."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_contracts import (
    GaitParameterDefinition,
    ParameterExtractionType,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.gait_parameter_registry import (
    gait_parameter_catalog,
)
from dlc_gait_assembly.runway.manual.gait_analysis.business.parameters.rustlab1_parameter_definitions import (
    RUSTLAB1_FORELIMB_PARAMETER_NAMES,
)


def display_parameter_name(name: str) -> str:
    """Turn exported column identifiers into readable labels without changing the output name."""
    (side, separator, remainder) = name.partition("__")
    is_side_prefix = separator and side.casefold() in {"left", "right"}
    readable = (remainder if is_side_prefix else name).replace("_", " ")
    readable = " ".join(readable.split())
    if is_side_prefix:
        readable = f"{side.title()} · {readable}"
    return readable[:1].upper() + readable[1:] if readable else name


def resize_parameter_rows(tree: QTreeWidget, columns: tuple[int, ...], *, checkable_column: int | None = None) -> None:
    """Give wrapped text enough height at the current column widths."""
    metrics = tree.fontMetrics()
    for row in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(row)
        if item.isHidden():
            continue
        height = 32
        for column in columns:
            width = tree.columnWidth(column) - (40 if column == checkable_column else 20)
            if width < 40:
                continue
            bounds = metrics.boundingRect(QRect(0, 0, width, 10000), Qt.TextWordWrap, item.text(column))
            height = max(height, bounds.height() + 14)
        item.setSizeHint(0, QSize(0, height))


class GaitParameterSelectionWidget(QWidget):
    def __init__(self, enabled_parameter_names: tuple[str, ...] | None = None, *, multiside: bool = True):
        super().__init__()
        self.setObjectName("GaitParameterSelection")
        self._definitions = gait_parameter_catalog()
        self._multiside = multiside
        self._include_forelimb = False
        self._source_filter: str | None = None
        self._complete_export = True
        self._items: list[tuple[GaitParameterDefinition, QTreeWidgetItem]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        controls = QHBoxLayout()
        self.extraction_type_filter = QComboBox()
        self.extraction_type_filter.setObjectName("GaitExtractionTypeFilter")
        self.extraction_type_filter.addItem("All extraction types")
        self.extraction_type_filter.addItems([kind.value for kind in ParameterExtractionType])
        self.extraction_type_filter.setToolTip("Browse by measurement type. This filter does not change which supported parameters are exported.")
        controls.addWidget(self.extraction_type_filter, 1)
        self.select_all_button = QPushButton("Select all")
        self.clear_button = QPushButton("Disable all")
        controls.addWidget(self.select_all_button)
        controls.addWidget(self.clear_button)
        layout.addLayout(controls)
        self.count_label = QLabel()
        self.count_label.setObjectName("MutedLabel")
        layout.addWidget(self.count_label)
        self.tree = QTreeWidget()
        self.tree.setObjectName("GaitParameterSelectionTree")
        self.tree.setHeaderLabels(("#", "Parameter", "Source"))
        self.tree.setRootIsDecorated(False)
        self.tree.setWordWrap(True)
        self.tree.setTextElideMode(Qt.ElideNone)
        self.tree.setUniformRowHeights(False)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        enabled = set(enabled_parameter_names) if enabled_parameter_names is not None else None
        for index, definition in enumerate(self._definitions, start=1):
            item = QTreeWidgetItem((str(index), definition.display_name or display_parameter_name(definition.name), definition.source))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(1, Qt.Checked if self._initially_enabled(definition, enabled) else Qt.Unchecked)
            item.setToolTip(1, f"{definition.name}\n{definition.extraction_type.value} · {definition.output_level} · {definition.unit}\n{definition.views}: {definition.markers}\n{definition.calculation}\n{definition.method_note}\n{definition.reference}")
            self.tree.addTopLevelItem(item)
            self._items.append((definition, item))
        layout.addWidget(self.tree, 1)
        self.select_all_button.clicked.connect(lambda: self._set_all(Qt.Checked))
        self.clear_button.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        self.tree.itemChanged.connect(self._update_count)
        self.tree.header().sectionResized.connect(lambda *_: resize_parameter_rows(self.tree, (1, 2), checkable_column=1))
        self.extraction_type_filter.currentTextChanged.connect(lambda _text: self.set_multiside(self._multiside))
        self.set_multiside(multiside)
        self.set_source_filter(None)

    @staticmethod
    def _initially_enabled(definition: GaitParameterDefinition, enabled: set[str] | None) -> bool:
        if enabled is None or definition.name in enabled:
            return True
        if definition.source != "ALMA":
            return False
        if definition.view_mode == "Multi-view":
            (_side, separator, base_name) = definition.name.partition("__")
            return bool(separator and base_name in enabled)
        return any(f"{side}__{definition.name}" in enabled for side in ("left", "right"))

    def set_multiside(self, multiside: bool) -> None:
        """Expose exactly the parameters generated by the selected input mode."""
        self._multiside = multiside
        kind = self.extraction_type_filter.currentText()
        visible_index = 0
        for definition, item in self._items:
            visible = (
                self._applicable(definition)
                and (kind == "All extraction types" or definition.extraction_type.value == kind)
            )
            item.setHidden(not visible)
            if visible:
                visible_index += 1
                item.setText(0, str(visible_index))
        self._update_count()
        resize_parameter_rows(self.tree, (1, 2), checkable_column=1)

    def _applicable(self, definition):
        return (
            definition.view_mode == ("Multi-view" if self._multiside else "Single-view")
            and (self._include_forelimb or not definition.forelimb and definition.name not in RUSTLAB1_FORELIMB_PARAMETER_NAMES)
            and (self._source_filter is None or definition.source == self._source_filter)
        )

    def set_limb_scope(self, include_forelimb: bool) -> None:
        self._include_forelimb = bool(include_forelimb)
        self.set_multiside(self._multiside)

    def set_source_filter(self, source: str | None) -> None:
        """Limit the selectable rows to one analysis source, or show all sources."""
        self._source_filter = source
        self._complete_export = source in {None, "ALMA"}
        self.select_all_button.setVisible(not self._complete_export)
        self.clear_button.setVisible(not self._complete_export)
        self.tree.setToolTip(
            "All ALMA side parameters are exported in the original ALMA CSV format, excluding multi-stride variability."
            if source == "ALMA" else
            "Stride files include swing-phase kinematics and hindlimb coordination. General parameters include bilateral symmetry, lesion-oriented asymmetry and stride variability, with valid-stride counts. The parameter dictionary explains units, formulas and paper references. Choose an extraction type to browse; all applicable measurements are exported. Set the lesion hemisphere in recording pairing for signed asymmetry."
            if self._complete_export
            else "Unchecked parameters are excluded from standalone RustLab1 outputs."
        )
        for _definition, item in self._items:
            flags = item.flags()
            item.setFlags(flags & ~Qt.ItemIsUserCheckable if self._complete_export else flags | Qt.ItemIsUserCheckable)
            if self._complete_export:
                item.setCheckState(1, Qt.Checked)
        self.set_multiside(self._multiside)

    def enabled_parameter_names(self) -> tuple[str, ...]:
        return tuple(
            definition.name
            for (definition, item) in self._items
            if self._applicable(definition) and (self._complete_export or item.checkState(1) == Qt.Checked)
        )

    def _set_all(self, state: Qt.CheckState) -> None:
        self.tree.blockSignals(True)
        for _definition, item in self._items:
            if not item.isHidden():
                item.setCheckState(1, state)
        self.tree.blockSignals(False)
        self._update_count()

    def _update_count(self, *_args) -> None:
        available = sum(self._applicable(definition) for (definition, _item) in self._items)
        if self._complete_export and self.extraction_type_filter.currentText() != "All extraction types":
            shown = sum(not item.isHidden() for _definition, item in self._items)
            self.count_label.setText(f"Showing {shown} of {available} exported parameters")
        else:
            self.count_label.setText(f"{len(self.enabled_parameter_names())} of {available} parameters enabled")
