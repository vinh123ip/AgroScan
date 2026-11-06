"""Catalog & Criteria page — step 2: goods categories, products and defect criteria.

Admin only (``navigation.py``). Left: products filtered by goods category.
Right: editor for the selected product — general data, the YOLO model file
(D-024), Needs-Review thresholds and per-defect criteria (D-023), plus a live
plain-English preview of how the rule engine will read them.

UI-shell phase: changes are stored in ``MockRepository`` (RAM only). The
editor configures thresholds; it does not change how they are evaluated.
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import DefectCriterion, Product
from agroscan.services.catalog_validation import parse_class_list, validate_product
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, SectionCard, make_hint

_ALL_CATEGORIES = "All categories"


def describe_rules(product: Product) -> list[str]:
    """Plain-English reading of a product's criteria, in rule-engine order (D-023)."""
    lines: list[str] = []
    critical = [c for c in product.criteria if c.is_critical]
    ratio = [c for c in product.criteria if not c.is_critical]
    for c in critical:
        lines.append(f"FAIL immediately if any '{c.defect_class}' is detected (critical defect).")
    for c in ratio:
        lines.append(f"FAIL if '{c.defect_class}' exceeds {c.max_ratio:.1%} of detected objects.")
    lines.append(
        f"NEEDS REVIEW if fewer than {product.min_objects} objects are detected "
        f"or mean confidence is below {product.min_confidence:.0%}."
    )
    lines.append("PASS otherwise. The reviewer always confirms the final decision.")
    configured = {c.defect_class for c in product.criteria}
    unchecked = [c for c in product.detect_classes[1:] if c not in configured]
    if unchecked:
        lines.append(f"Not evaluated (no criterion): {', '.join(unchecked)}.")
    return lines


class CatalogPage(QWidget):
    """Goods Category & Criteria Editor."""

    catalog_changed = Signal()

    _COL_CLASS, _COL_RATIO, _COL_CRITICAL = range(3)

    def __init__(self, repo: MockRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("CatalogPage")
        self._repo = repo
        self._original: Optional[Product] = None   # Product being edited (None = new)
        self._baseline: Optional[Product] = None   # Form state at load, for dirty check
        self._loading = False
        self._init_ui()
        self._connect_signals()
        self.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 28)
        root.setSpacing(20)
        root.addWidget(PageHeader(
            "Catalog & Criteria",
            "Goods categories, products, their dedicated YOLO model and the defect "
            "criteria used by the rule engine.",
        ))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ReviewSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setSizes([520, 820])
        root.addWidget(splitter, 1)

    def _build_list_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        filter_row = QHBoxLayout()
        filter_label = QLabel("Goods Category")
        filter_label.setObjectName("FormLabel")
        self.category_filter = QComboBox()
        self.category_filter.setObjectName("FormCombo")
        filter_row.addWidget(filter_label)
        filter_row.addWidget(self.category_filter, 1)
        layout.addLayout(filter_row)

        self.search_field = QLineEdit()
        self.search_field.setObjectName("FormField")
        self.search_field.setPlaceholderText("Search by code, product name, or YOLO model…")
        self.search_field.setClearButtonEnabled(True)
        layout.addWidget(self.search_field)

        self.count_label = QLabel("")
        self.count_label.setObjectName("FormSectionTitle")
        layout.addWidget(self.count_label)

        self.product_table = DataTable(["Code", "Name", "Category", "YOLO Model", "Criteria"])
        layout.addWidget(self.product_table, 1)

        buttons = QHBoxLayout()
        self.btn_new = QPushButton("+  New Product")
        self.btn_new.setObjectName("SecondaryButton")
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("DangerButton")
        for btn in (self.btn_new, self.btn_delete):
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            buttons.addWidget(btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        return panel

    def _build_editor_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("PageScrollArea")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("ScrollContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 0, 12, 0)
        layout.setSpacing(18)

        self.editor_title = QLabel("")
        self.editor_title.setObjectName("PageTitleSmall")
        layout.addWidget(self.editor_title)
        self.usage_label = QLabel("")
        self.usage_label.setObjectName("WarningNote")
        self.usage_label.setWordWrap(True)
        layout.addWidget(self.usage_label)

        # General
        general = SectionCard("Product")
        form = QFormLayout()
        form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.code_field = self._line("e.g.  BANANA")
        self.name_field = self._line("e.g.  Banana")
        self.category_field = QComboBox()
        self.category_field.setObjectName("FormCombo")
        self.category_field.setEditable(True)
        self.category_field.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category_field.lineEdit().setPlaceholderText("Choose or type a new category")
        self.model_field = self._line("e.g.  banana_defect.onnx")
        self.classes_field = self._line("e.g.  fresh, bruised, rotten")
        form.addRow(self._label("Code"), self.code_field)
        form.addRow(self._label("Name"), self.name_field)
        form.addRow(self._label("Goods Category"), self.category_field)
        form.addRow(self._label("YOLO Model File"), self.model_field)
        form.addRow(self._label("Detect Classes"), self.classes_field)
        general.body.addLayout(form)
        general.body.addWidget(make_hint(
            "Detect classes must match the classes the YOLO model returns. "
            "List the healthy class first, then the defect classes (comma separated)."
        ))
        layout.addWidget(general)

        # Needs Review thresholds
        review = SectionCard("Needs Review Thresholds")
        review_form = QFormLayout()
        review_form.setSpacing(14)
        self.min_objects_spin = QSpinBox()
        self.min_objects_spin.setObjectName("FormSpin")
        self.min_objects_spin.setRange(1, 500)
        self.min_objects_spin.setSuffix("  objects")
        self.min_conf_spin = QSpinBox()
        self.min_conf_spin.setObjectName("FormSpin")
        self.min_conf_spin.setRange(0, 100)
        self.min_conf_spin.setSuffix("  %")
        review_form.addRow(self._label("Minimum Objects"), self.min_objects_spin)
        review_form.addRow(self._label("Minimum Mean Confidence"), self.min_conf_spin)
        review.body.addLayout(review_form)
        review.body.addWidget(make_hint(
            "Below either threshold the box is sent to the reviewer as Needs Review "
            "instead of Pass, and deep analysis is suggested."
        ))
        layout.addWidget(review)

        # Defect criteria
        criteria = SectionCard("Defect Criteria")
        self.criteria_table = QTableWidget(0, 3)
        self.criteria_table.setObjectName("DataTable")
        self.criteria_table.setHorizontalHeaderLabels(["Defect Class", "Max Ratio", "Critical"])
        self.criteria_table.verticalHeader().setVisible(False)
        self.criteria_table.verticalHeader().setDefaultSectionSize(48)
        self.criteria_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.criteria_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.criteria_table.setShowGrid(False)
        self.criteria_table.setMinimumHeight(190)
        header = self.criteria_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        criteria.body.addWidget(self.criteria_table)
        crit_buttons = QHBoxLayout()
        self.btn_add_criterion = QPushButton("+  Add Criterion")
        self.btn_add_criterion.setObjectName("SecondaryButton")
        self.btn_remove_criterion = QPushButton("Remove Selected")
        self.btn_remove_criterion.setObjectName("SecondaryButton")
        for btn in (self.btn_add_criterion, self.btn_remove_criterion):
            btn.setFixedHeight(38)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            crit_buttons.addWidget(btn)
        crit_buttons.addStretch()
        criteria.body.addLayout(crit_buttons)
        self.conflict_label = QLabel("")
        self.conflict_label.setObjectName("WarningNote")
        self.conflict_label.setWordWrap(True)
        self.conflict_label.setVisible(False)
        criteria.body.addWidget(self.conflict_label)
        criteria.body.addWidget(make_hint(
            "Max ratio: the box is proposed as Fail when that defect's share of detected "
            "objects exceeds the limit. Critical: any occurrence proposes Fail immediately "
            "(max ratio is ignored)."
        ))
        layout.addWidget(criteria)

        # Preview
        preview = SectionCard("Rule Preview")
        self.preview_label = QLabel("")
        self.preview_label.setObjectName("VlmValue")
        self.preview_label.setWordWrap(True)
        preview.body.addWidget(self.preview_label)
        layout.addWidget(preview)

        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("HintLabel")
        actions.addWidget(self.status_label, 1)
        self.btn_revert = QPushButton("Revert")
        self.btn_revert.setObjectName("SecondaryButton")
        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setObjectName("PrimaryButton")
        for btn in (self.btn_revert, self.btn_save):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(140)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(btn)
        layout.addLayout(actions)
        layout.addStretch()

        scroll.setWidget(content)
        return scroll

    @staticmethod
    def _line(placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("FormField")
        field.setPlaceholderText(placeholder)
        return field

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FormLabel")
        return label

    def _connect_signals(self) -> None:
        self.category_filter.currentIndexChanged.connect(lambda _: self._fill_table())
        self.search_field.textChanged.connect(lambda _: self._fill_table())
        self.product_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_new.clicked.connect(self._on_new)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_add_criterion.clicked.connect(lambda: self._add_criterion_row())
        self.btn_remove_criterion.clicked.connect(self._on_remove_criterion)
        self.btn_revert.clicked.connect(self._on_revert)
        self.btn_save.clicked.connect(self._on_save)

        for field in (self.code_field, self.name_field, self.model_field):
            field.textChanged.connect(self._on_form_changed)
        self.classes_field.textChanged.connect(self._on_classes_changed)
        self.category_field.currentTextChanged.connect(self._on_form_changed)
        self.min_objects_spin.valueChanged.connect(self._on_form_changed)
        self.min_conf_spin.valueChanged.connect(self._on_form_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        return self._baseline is not None and self.form_product() != self._baseline

    def confirm_discard_changes(self) -> bool:
        """Ask the user before leaving the page when unsaved edits exist."""
        return self._confirm_discard()

    def refresh(self, select_code: Optional[str] = None) -> None:
        """Reload categories and products; keep or set the selected product."""
        current = select_code or (self._original.code if self._original else None)
        self.category_filter.blockSignals(True)
        wanted = self.category_filter.currentText() or _ALL_CATEGORIES
        self.category_filter.clear()
        self.category_filter.addItem(_ALL_CATEGORIES)
        self.category_filter.addItems(self._repo.categories())
        index = self.category_filter.findText(wanted)
        self.category_filter.setCurrentIndex(max(index, 0))
        self.category_filter.blockSignals(False)
        self._fill_table(current)

    def form_product(self) -> Product:
        """Product built from the current form values (not validated)."""
        criteria = []
        for row in range(self.criteria_table.rowCount()):
            combo: QComboBox = self.criteria_table.cellWidget(row, self._COL_CLASS)
            spin: QDoubleSpinBox = self.criteria_table.cellWidget(row, self._COL_RATIO)
            check = self._row_checkbox(row)
            criteria.append(DefectCriterion(
                defect_class=combo.currentText().strip(),
                max_ratio=round(spin.value() / 100, 4),
                is_critical=check.isChecked(),
            ))
        return Product(
            code=self.code_field.text().strip().upper(),
            name=self.name_field.text().strip(),
            category=self.category_field.currentText().strip(),
            model_file=self.model_field.text().strip(),
            detect_classes=parse_class_list(self.classes_field.text()),
            criteria=criteria,
            min_objects=self.min_objects_spin.value(),
            min_confidence=round(self.min_conf_spin.value() / 100, 2),
        )

    # ------------------------------------------------------------------
    # Product list
    # ------------------------------------------------------------------

    def _visible_products(self) -> list[Product]:
        category = self.category_filter.currentText()
        items = (
            list(self._repo.products)
            if not category or category == _ALL_CATEGORIES
            else [p for p in self._repo.products if p.category == category]
        )
        needle = self.search_field.text().strip().lower()
        if not needle:
            return items
        return [
            p for p in items
            if needle in p.code.lower()
            or needle in p.name.lower()
            or needle in p.category.lower()
            or needle in p.model_file.lower()
        ]

    def _fill_table(self, select_code: Optional[str] = None) -> None:
        products = self._visible_products()
        self.count_label.setText(f"{len(products)} PRODUCTS")
        self.product_table.blockSignals(True)
        self.product_table.set_rows([
            [p.code, p.name, p.category, p.model_file, str(len(p.criteria))] for p in products
        ], products)
        self.product_table.blockSignals(False)

        codes = [p.code for p in products]
        if select_code in codes:
            self._select_row(codes.index(select_code))
        elif self._original is None and self._baseline is not None:
            return                                  # Keep a "new product" form open
        elif products:
            self._select_row(0)
        else:
            self._load_product(None)

    def _select_row(self, row: int) -> None:
        self.product_table.blockSignals(True)
        self.product_table.selectRow(row)
        self.product_table.blockSignals(False)
        product: Optional[Product] = self.product_table.payload_at(row)
        if product is not None and (self._original is None or product.code != self._original.code
                                    or self._baseline is None):
            self._load_product(product)

    def _on_selection_changed(self) -> None:
        product: Optional[Product] = self.product_table.selected_payload()
        if product is None or (self._original is not None and product.code == self._original.code):
            return
        if not self._confirm_discard():
            self._reselect_current()
            return
        self._load_product(product)

    def _reselect_current(self) -> None:
        self.product_table.blockSignals(True)
        self.product_table.clearSelection()
        if self._original is not None:
            for row in range(self.product_table.rowCount()):
                payload = self.product_table.payload_at(row)
                if payload is not None and payload.code == self._original.code:
                    self.product_table.selectRow(row)
                    break
        self.product_table.blockSignals(False)

    def _confirm_discard(self) -> bool:
        if not self.is_dirty:
            return True
        answer = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes to this product. Discard them?",
        )
        return answer == QMessageBox.StandardButton.Yes

    # ------------------------------------------------------------------
    # Editor
    # ------------------------------------------------------------------

    def _load_product(self, product: Optional[Product]) -> None:
        """Fill the editor with ``product``; ``None`` opens an empty new-product form."""
        self._loading = True
        self._original = product
        is_new = product is None
        draft = product or Product(
            code="", name="",
            category=(self.category_filter.currentText()
                      if self.category_filter.currentText() != _ALL_CATEGORIES else ""),
            model_file="", detect_classes=["fresh"], criteria=[],
        )

        self.editor_title.setText("New Product" if is_new else f"{draft.name}  ·  {draft.code}")
        self.code_field.setText(draft.code)
        self.code_field.setReadOnly(not is_new)
        self.code_field.setObjectName("FormField" if is_new else "ReadOnlyField")
        self.code_field.style().unpolish(self.code_field)
        self.code_field.style().polish(self.code_field)
        self.name_field.setText(draft.name)
        self.category_field.clear()
        self.category_field.addItems(self._repo.categories())
        self.category_field.setEditText(draft.category)
        self.model_field.setText(draft.model_file)
        self.classes_field.setText(", ".join(draft.detect_classes))
        self.min_objects_spin.setValue(draft.min_objects)
        self.min_conf_spin.setValue(round(draft.min_confidence * 100))

        self.criteria_table.setRowCount(0)
        for criterion in draft.criteria:
            self._add_criterion_row(criterion)

        orders = [] if is_new else self._repo.orders_for_product(draft.code)
        self.usage_label.setVisible(bool(orders))
        if orders:
            self.usage_label.setText(
                f"▲  Used by {len(orders)} order(s): {', '.join(o.order_code for o in orders)}. "
                "Saved changes apply to every inspection started afterwards."
            )
        self.btn_delete.setEnabled(not is_new)
        self.error_label.setVisible(False)
        self.status_label.setText("")
        self._loading = False
        self._baseline = self.form_product()
        self._on_form_changed()
        if is_new:
            QTimer.singleShot(0, self.code_field.setFocus)

    def _defect_options(self) -> list[str]:
        return parse_class_list(self.classes_field.text())[1:]

    def _add_criterion_row(self, criterion: Optional[DefectCriterion] = None) -> None:
        options = self._defect_options()
        if criterion is None:
            used = {self.criteria_table.cellWidget(r, self._COL_CLASS).currentText()
                    for r in range(self.criteria_table.rowCount())}
            free = [o for o in options if o not in used]
            if not free:
                self._show_errors(["Every defect class already has a criterion. "
                                   "Add a defect class to Detect Classes first."])
                return
            criterion = DefectCriterion(free[0], 0.10)

        row = self.criteria_table.rowCount()
        self.criteria_table.insertRow(row)

        combo = QComboBox()
        combo.setObjectName("FormCombo")
        self._set_combo_options(combo, options, criterion.defect_class)
        combo.currentTextChanged.connect(self._on_form_changed)

        spin = QDoubleSpinBox()
        spin.setObjectName("FormSpin")
        spin.setRange(0.0, 100.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix("  %")
        spin.setValue(criterion.max_ratio * 100)
        spin.valueChanged.connect(self._on_form_changed)

        check = QCheckBox("Fail immediately")
        check.setChecked(criterion.is_critical)
        check.toggled.connect(lambda checked, s=spin: s.setEnabled(not checked))
        check.toggled.connect(self._on_form_changed)
        spin.setEnabled(not criterion.is_critical)
        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(8, 0, 0, 0)
        holder_layout.addWidget(check)

        self.criteria_table.setCellWidget(row, self._COL_CLASS, combo)
        self.criteria_table.setCellWidget(row, self._COL_RATIO, spin)
        self.criteria_table.setCellWidget(row, self._COL_CRITICAL, holder)
        self._on_form_changed()

    def _row_checkbox(self, row: int) -> QCheckBox:
        return self.criteria_table.cellWidget(row, self._COL_CRITICAL).findChild(QCheckBox)

    @staticmethod
    def _set_combo_options(combo: QComboBox, options: list[str], current: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(options)
        if current and current not in options:
            combo.addItem(current)               # Keep invalid value visible; validation flags it
        combo.setCurrentText(current)
        combo.blockSignals(False)

    def _on_remove_criterion(self) -> None:
        row = self.criteria_table.currentRow()
        if row < 0 and self.criteria_table.rowCount():
            row = self.criteria_table.rowCount() - 1
        if row >= 0:
            self.criteria_table.removeRow(row)
            self._on_form_changed()

    def _on_classes_changed(self) -> None:
        options = self._defect_options()
        for row in range(self.criteria_table.rowCount()):
            combo: QComboBox = self.criteria_table.cellWidget(row, self._COL_CLASS)
            self._set_combo_options(combo, options, combo.currentText())
        self._on_form_changed()

    def _on_form_changed(self) -> None:
        if self._loading:
            return
        product = self.form_product()
        self.preview_label.setText("\n".join(f"•  {line}" for line in describe_rules(product)))
        seen_classes: list[str] = []
        duplicates: list[str] = []
        for criterion in product.criteria:
            if criterion.defect_class in seen_classes and criterion.defect_class not in duplicates:
                duplicates.append(criterion.defect_class)
            seen_classes.append(criterion.defect_class)
        self.conflict_label.setVisible(bool(duplicates))
        if duplicates:
            self.conflict_label.setText(
                f"▲  Duplicate criterion row(s) for {', '.join(repr(d) for d in duplicates)}. "
                "Each defect class must have at most one threshold."
            )
        dirty = self.is_dirty
        self.btn_save.setEnabled(dirty or self._original is None)
        self.btn_revert.setEnabled(dirty)
        if dirty:
            self.status_label.setText("●  Unsaved changes")
        elif self.status_label.text().startswith("●"):
            self.status_label.setText("")

    def _existing_codes(self) -> list[str]:
        original = self._original.code if self._original else None
        return [p.code for p in self._repo.products if p.code != original]

    def _show_errors(self, errors: list[str]) -> None:
        self.error_label.setText("\n".join(f"⚠   {e}" for e in errors))
        self.error_label.setVisible(bool(errors))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_new(self) -> None:
        if not self._confirm_discard():
            return
        self.product_table.blockSignals(True)
        self.product_table.clearSelection()
        self.product_table.blockSignals(False)
        self._load_product(None)

    def _on_revert(self) -> None:
        self._load_product(self._original)

    def _on_save(self) -> None:
        product = self.form_product()
        errors = validate_product(product, self._existing_codes())
        if errors:
            self._show_errors(errors)
            return
        original_code = self._original.code if self._original else None
        try:
            saved = self._repo.save_product(product, original_code)
        except ValueError as exc:
            self._show_errors(str(exc).splitlines())
            return
        self._show_errors([])
        self._original = saved
        self._baseline = None
        self.refresh(select_code=saved.code)
        self._load_product(saved)
        self.status_label.setText(f"✔  {saved.name} saved.")
        self.catalog_changed.emit()

    def _on_delete(self) -> None:
        if self._original is None:
            return
        product = self._original
        answer = QMessageBox.question(
            self, "Delete Product",
            f"Delete {product.name} ({product.code}) and its defect criteria?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._repo.delete_product(product.code)
        except ValueError as exc:
            self._show_errors([str(exc)])
            return
        self._original, self._baseline = None, None
        self.refresh()
        self.status_label.setText(f"✔  {product.name} deleted.")
        self.catalog_changed.emit()

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        if not self.is_dirty:
            self.refresh()

