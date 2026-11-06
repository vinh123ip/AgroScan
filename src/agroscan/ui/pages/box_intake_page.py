"""Box Intake page — step 3: scan a box QR code or look up an order manually.

A USB 2D scanner behaves like a HID keyboard: it types the payload and sends
Enter, so ``scan_field`` reacts to ``returnPressed`` with anti-bounce debouncing
(D-019). Displays Order metadata, Lot Size, Declared Category, Quality Criteria,
defect thresholds, and categorized scan/lookup errors before starting a session.
"""

import re
import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from agroscan.models.inspection_models import (
    BoxCode,
    InspectionRecord,
    InspectionSession,
    Order,
    Product,
)
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import (
    KeyValueGrid,
    PageHeader,
    ScrollPage,
    SectionCard,
    make_hint,
)
from agroscan.ui.components.qr_label_dialog import QrLabelDialog
from agroscan.ui.pages.catalog_page import describe_rules

_RETAIL_BARCODE_RE = re.compile(r"^\d{8,14}$")
_BARE_BOX_RE       = re.compile(r"^[A-Z0-9]+-\d{1,4}/\d{1,4}$")


def classify_intake_error(raw_text: str, exc_message: str) -> tuple[str, str]:
    """Classify a box scan / lookup error into ``(error_code, user_message)``."""
    cleaned = raw_text.strip()
    if not cleaned:
        return (
            "ERR_EMPTY_CODE",
            "Enter or scan a box QR code (e.g. AGS:DH00123-03/10), or look up by Order Code below.",
        )
    if _RETAIL_BARCODE_RE.match(cleaned):
        return (
            "ERR_RETAIL_BARCODE",
            f"Retail EAN/GTIN barcode '{cleaned}' detected. Retail barcodes identify a product "
            "SKU, not an individual shipment box — scan the AgroScan box QR label "
            "(AGS:<ORDER>-<BOX>/<TOTAL>) or search by Order Code below.",
        )
    if _BARE_BOX_RE.match(cleaned.upper()):
        return (
            "ERR_MISSING_PREFIX",
            f"Missing 'AGS:' prefix. Expected 'AGS:{cleaned.upper()}' "
            "(or enter it in 'Find Manually by Order Code' below).",
        )
    lower = exc_message.lower()
    if "out of range" in lower:
        return ("ERR_BOX_OUT_OF_RANGE", exc_message)
    if "was not found" in lower:
        return ("ERR_ORDER_NOT_FOUND", exc_message)
    if "box code says" in lower:
        return ("ERR_LOT_MISMATCH", exc_message)
    return ("ERR_INVALID_FORMAT", exc_message)


class BoxIntakePage(ScrollPage):
    """Box intake screen supporting USB 2D QR scan, manual order lookup, and criteria preview."""

    session_requested = Signal(object, object, str)   # BoxCode, Order, notes
    resume_requested  = Signal()

    _SCAN_DEBOUNCE_S = 0.35

    def __init__(self, repo: MockRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__("BoxIntakePage", parent)
        self._repo = repo
        self._box_code: Optional[BoxCode] = None
        self._order: Optional[Order] = None
        self._active_session: Optional[InspectionSession] = None
        self._last_hw_scan_code: str = ""
        self._last_hw_scan_ts: float = 0.0
        self._starting_session: bool = False
        self.suppressed_scan_bounces: int = 0
        self.last_error_code: Optional[str] = None

        self._init_ui()
        self._connect_signals()
        self.reset_form()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.body.addWidget(PageHeader(
            "Box Intake",
            "Scan the QR label on the box or search by order code to review declared "
            "category, lot size, and quality criteria before opening an inspection session.",
        ))

        # Active session banner (step 12: unfinished session remains tracked)
        self.resume_banner = QFrame()
        self.resume_banner.setObjectName("InfoBanner")
        banner_layout = QHBoxLayout(self.resume_banner)
        banner_layout.setContentsMargins(20, 14, 20, 14)
        self.resume_label = QLabel("")
        self.resume_label.setObjectName("InfoBannerText")
        self.btn_resume = QPushButton("Resume Inspection  →")
        self.btn_resume.setObjectName("PrimaryButton")
        self.btn_resume.setFixedHeight(38)
        self.btn_resume.setCursor(Qt.CursorShape.PointingHandCursor)
        banner_layout.addWidget(self.resume_label, 1)
        banner_layout.addWidget(self.btn_resume)
        self.resume_banner.setVisible(False)
        self.body.addWidget(self.resume_banner)

        # 1. QR / Barcode scanner input
        scan_card = SectionCard("Scan Box QR / Barcode")
        scan_row = QHBoxLayout()
        scan_row.setSpacing(12)
        self.scan_field = QLineEdit()
        self.scan_field.setObjectName("ScanField")
        self.scan_field.setPlaceholderText(
            "Scan QR code or type  AGS:DH00123-03/10  then press Enter"
        )
        self.scan_field.setClearButtonEnabled(True)
        self.btn_scan = QPushButton("Verify Code")
        self.btn_scan.setObjectName("PrimaryButton")
        self.btn_scan.setFixedHeight(44)
        self.btn_scan.setMinimumWidth(130)
        self.btn_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_qr_preview = QPushButton("QR Labels && Test…")
        self.btn_qr_preview.setObjectName("SecondaryButton")
        self.btn_qr_preview.setFixedHeight(44)
        self.btn_qr_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        scan_row.addWidget(self.scan_field, 1)
        scan_row.addWidget(self.btn_scan)
        scan_row.addWidget(self.btn_qr_preview)
        scan_card.body.addLayout(scan_row)
        scan_card.body.addWidget(make_hint(
            "A USB 2D scanner types the box code into this field and sends Enter automatically "
            "(duplicate trigger bounces within 350 ms are filtered out)."
        ))
        self.body.addWidget(scan_card)

        # 2. Manual lookup by Order Code or Order selector
        lookup_card = SectionCard("Or Find Manually by Order Code")

        code_search_row = QHBoxLayout()
        code_search_row.setSpacing(12)
        self.order_code_field = QLineEdit()
        self.order_code_field.setObjectName("FormField")
        self.order_code_field.setPlaceholderText(
            "Enter Order Code (e.g.  DH00123) and press Enter…"
        )
        self.order_code_field.setClearButtonEnabled(True)
        self.btn_find_order = QPushButton("Find Order")
        self.btn_find_order.setObjectName("SecondaryButton")
        self.btn_find_order.setFixedHeight(42)
        self.btn_find_order.setMinimumWidth(130)
        self.btn_find_order.setCursor(Qt.CursorShape.PointingHandCursor)
        code_search_row.addWidget(self.order_code_field, 1)
        code_search_row.addWidget(self.btn_find_order)
        lookup_card.body.addLayout(code_search_row)

        lookup_row = QHBoxLayout()
        lookup_row.setSpacing(12)
        self.order_combo = QComboBox()
        self.order_combo.setObjectName("FormCombo")
        self.box_spin = QSpinBox()
        self.box_spin.setObjectName("FormSpin")
        self.box_spin.setPrefix("Box  ")
        self.box_spin.setMinimumWidth(150)
        self.btn_lookup = QPushButton("Load Box")
        self.btn_lookup.setObjectName("SecondaryButton")
        self.btn_lookup.setFixedHeight(42)
        self.btn_lookup.setMinimumWidth(130)
        self.btn_lookup.setCursor(Qt.CursorShape.PointingHandCursor)
        lookup_row.addWidget(self.order_combo, 1)
        lookup_row.addWidget(self.box_spin)
        lookup_row.addWidget(self.btn_lookup)
        lookup_card.body.addLayout(lookup_row)
        self.body.addWidget(lookup_card)

        # Error feedback banner
        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.setVisible(False)
        self.body.addWidget(self.error_label)

        # 3. Order, Lot Size, & Declared Category card
        self.info_card = SectionCard("Order, Lot Size & Declared Category")
        self.info_grid = KeyValueGrid(columns=3)
        self.info_card.body.addWidget(self.info_grid)

        self.active_box_label = QLabel("")
        self.active_box_label.setObjectName("InlineErrorLabel")
        self.active_box_label.setWordWrap(True)
        self.active_box_label.setVisible(False)
        self.info_card.body.addWidget(self.active_box_label)

        self.reinspect_label = QLabel("")
        self.reinspect_label.setObjectName("WarningNote")
        self.reinspect_label.setWordWrap(True)
        self.reinspect_label.setVisible(False)
        self.info_card.body.addWidget(self.reinspect_label)

        self.notes_field = QPlainTextEdit()
        self.notes_field.setObjectName("NotesField")
        self.notes_field.setPlaceholderText("Optional intake notes about this box…")
        self.notes_field.setFixedHeight(76)
        self.info_card.body.addWidget(self.notes_field)
        self.body.addWidget(self.info_card)

        # 4. Declared Quality Criteria & Defect Thresholds card
        self.criteria_card = SectionCard("Declared Quality Criteria & Defect Thresholds")
        self.criteria_summary_grid = KeyValueGrid(columns=3)
        self.criteria_card.body.addWidget(self.criteria_summary_grid)

        self.criteria_table = DataTable(
            ["Defect Class", "Max Allowed Ratio", "Severity", "Evaluation Rule"]
        )
        self.criteria_table.setMinimumHeight(140)
        self.criteria_card.body.addWidget(self.criteria_table)

        self.rules_summary_label = QLabel("")
        self.rules_summary_label.setObjectName("HintLabel")
        self.rules_summary_label.setWordWrap(True)
        self.criteria_card.body.addWidget(self.rules_summary_label)
        self.body.addWidget(self.criteria_card)

        actions = QHBoxLayout()
        actions.addStretch()
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("SecondaryButton")
        self.btn_start = QPushButton("Start Inspection  →")
        self.btn_start.setObjectName("PrimaryButton")
        for btn, width in ((self.btn_clear, 120), (self.btn_start, 210)):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(width)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(btn)
        self.body.addLayout(actions)
        self.body.addStretch()

    def _connect_signals(self) -> None:
        self.scan_field.returnPressed.connect(self._on_scan_return_pressed)
        self.scan_field.textEdited.connect(self._hide_error)
        self.btn_scan.clicked.connect(lambda: self.load_code(self.scan_field.text()))
        self.btn_qr_preview.clicked.connect(self._on_open_qr_dialog)

        self.order_code_field.returnPressed.connect(self._on_find_order_clicked)
        self.order_code_field.textEdited.connect(self._hide_error)
        self.btn_find_order.clicked.connect(self._on_find_order_clicked)

        self.order_combo.currentIndexChanged.connect(self._on_order_changed)
        self.btn_lookup.clicked.connect(self._on_lookup)
        self.btn_clear.clicked.connect(self.reset_form)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_resume.clicked.connect(self.resume_requested)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def current_box_code(self) -> Optional[BoxCode]:
        return self._box_code

    @property
    def current_order(self) -> Optional[Order]:
        return self._order

    def reset_form(self) -> None:
        self._box_code, self._order = None, None
        self._starting_session = False
        self._last_hw_scan_code = ""
        self._last_hw_scan_ts = 0.0
        self.scan_field.clear()
        self.order_code_field.clear()
        self.notes_field.clear()
        self._hide_error()
        self.active_box_label.setVisible(False)
        self.reinspect_label.setVisible(False)
        self.info_card.setVisible(False)
        self.criteria_card.setVisible(False)
        self.btn_start.setEnabled(False)
        self._fill_orders()
        QTimer.singleShot(0, self.scan_field.setFocus)

    def set_active_session(self, session: Optional[InspectionSession]) -> None:
        """Display the active-session banner and refresh duplicate-open guards."""
        self._active_session = session
        self.resume_banner.setVisible(session is not None)
        if session is not None:
            self.resume_label.setText(
                f"Session {session.session_id} for box {session.box_code} "
                f"({session.product.name}) is currently in progress."
            )
        if self._box_code is not None and self._order is not None:
            self._render_loaded_box(self._box_code, self._order)

    def refresh_catalog_data(self) -> None:
        """Refresh order dropdown and any currently loaded box after Catalog edits."""
        selected_order_code = (
            self.order_combo.currentData().order_code
            if self.order_combo.currentData() is not None
            else None
        )
        self._fill_orders(select_order_code=selected_order_code)
        if self._box_code is not None and self._order is not None:
            self._render_loaded_box(self._box_code, self._order)

    def lookup_by_order_code(self, order_code_text: str, box_number: Optional[int] = None) -> bool:
        """Look up an order manually by typed ``order_code_text`` and load a box."""
        raw = order_code_text.strip().upper()
        if raw.startswith("AGS:") and "-" in raw:
            return self.load_code(raw)
        if raw.startswith("AGS:"):
            raw = raw[4:].strip()
        if _BARE_BOX_RE.match(raw):
            return self.load_code(f"AGS:{raw}")
        if not raw:
            self._show_error(
                "Enter an Order Code (e.g. DH00123) to look up.",
                code="ERR_EMPTY_CODE",
            )
            self._clear_loaded_cards()
            return False

        order = self._repo.orders.get(raw)
        if order is None:
            self._show_error(
                f"Order {raw} was not found. Available orders: "
                + ", ".join(sorted(self._repo.orders.keys())) + ".",
                code="ERR_ORDER_NOT_FOUND",
            )
            self._clear_loaded_cards()
            return False

        for idx in range(self.order_combo.count()):
            item_order: Optional[Order] = self.order_combo.itemData(idx)
            if item_order is not None and item_order.order_code == order.order_code:
                self.order_combo.blockSignals(True)
                self.order_combo.setCurrentIndex(idx)
                self.order_combo.blockSignals(False)
                self._on_order_changed()
                break

        target_box = box_number if box_number is not None else self.box_spin.value()
        if not 1 <= target_box <= order.total_boxes:
            target_box = 1
        self.box_spin.setValue(target_box)
        self.order_code_field.setText(order.order_code)
        return self.load_code(BoxCode(order.order_code, target_box, order.total_boxes).text)

    def load_code(self, text: str) -> bool:
        """Validate ``text`` against active orders and populate Order/Lot/Criteria cards."""
        self._starting_session = False
        try:
            box_code, order = self._repo.resolve_box(text)
        except ValueError as exc:
            err_code, err_msg = classify_intake_error(text, str(exc))
            self._show_error(err_msg, code=err_code)
            self._clear_loaded_cards()
            return False

        self._box_code, self._order = box_code, order
        self.scan_field.setText(box_code.text)
        self._hide_error()
        self._render_loaded_box(box_code, order)
        if self.btn_start.isEnabled():
            self.btn_start.setFocus()
        return True

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------

    def _clear_loaded_cards(self) -> None:
        self._box_code, self._order = None, None
        self.info_card.setVisible(False)
        self.criteria_card.setVisible(False)
        self.active_box_label.setVisible(False)
        self.reinspect_label.setVisible(False)
        self.btn_start.setEnabled(False)

    def _render_loaded_box(self, box_code: BoxCode, order: Order) -> None:
        product = order.product
        approx_per_box = max(1, round(order.expected_quantity / max(1, order.total_boxes)))
        healthy = product.detect_classes[0] if product.detect_classes else "—"
        defects = ", ".join(product.detect_classes[1:]) if len(product.detect_classes) > 1 else "none"
        progress_text = self._order_progress_text(order.order_code)

        self.info_grid.set_items([
            ("Order",             order.order_code),
            ("Box",               f"{box_code.box_number} of {order.total_boxes}  ({box_code.text})"),
            ("Lot Size",          f"{order.total_boxes} boxes · {order.expected_quantity} units (~{approx_per_box}/box)"),
            ("Declared Category", product.category),
            ("Declared Product",  f"{product.name} ({product.code})"),
            ("Supplier",          order.supplier),
            ("YOLO Model",        product.model_file),
            ("Detect Classes",    f"{healthy} (healthy) · defects: {defects}"),
            ("Lot Progress",      progress_text),
        ])

        self._populate_criteria_card(product)

        previous = self._repo.records_for_box(box_code)
        self.reinspect_label.setVisible(bool(previous))
        if previous:
            self.reinspect_label.setText(self._format_reinspection_warning(previous))

        already_open = (
            self._active_session is not None
            and self._active_session.box_code == box_code
        )
        self.active_box_label.setVisible(already_open)
        if already_open and self._active_session is not None:
            self.active_box_label.setText(
                f"⚠   [ERR_SESSION_ALREADY_OPEN] Box {box_code} is already open in active "
                f"session {self._active_session.session_id}. Only one open session per box "
                "is allowed (D-021) — click 'Resume Inspection →' above."
            )

        self.info_card.setVisible(True)
        self.criteria_card.setVisible(True)
        self.btn_start.setEnabled(not already_open)

    def _populate_criteria_card(self, product: Product) -> None:
        healthy = product.detect_classes[0] if product.detect_classes else "—"
        self.criteria_summary_grid.set_items([
            ("Healthy Class",       healthy),
            ("Minimum Objects",     f"≥ {product.min_objects} objects (else Needs Review)"),
            ("Minimum Confidence",  f"≥ {product.min_confidence:.0%} mean confidence"),
        ])

        rows: list[list[str]] = []
        configured_classes: set[str] = set()
        for c in product.criteria:
            configured_classes.add(c.defect_class)
            if c.is_critical:
                rows.append([
                    c.defect_class,
                    "0.0% (Zero tolerance)",
                    "▲ Critical Defect",
                    "Propose FAIL immediately on ≥ 1 unit",
                ])
            else:
                rows.append([
                    c.defect_class,
                    f"{c.max_ratio:.1%}",
                    "Standard Threshold",
                    f"Propose FAIL when share exceeds {c.max_ratio:.1%}",
                ])

        for cls_name in product.detect_classes[1:]:
            if cls_name not in configured_classes:
                rows.append([
                    cls_name,
                    "—",
                    "Unconfigured",
                    "Counted only (no automatic Fail threshold)",
                ])

        if not rows:
            rows.append(["—", "—", "No defect classes", "Only Needs-Review gates apply"])

        self.criteria_table.set_rows(rows)
        row_height = max(1, len(rows)) * 42 + 44
        self.criteria_table.setFixedHeight(min(260, max(120, row_height)))
        self.rules_summary_label.setText(
            "Rule evaluation order:  " + "   ·   ".join(describe_rules(product))
        )

    def _order_progress_text(self, order_code: str) -> str:
        for summary in self._repo.order_summaries():
            if summary.order.order_code == order_code:
                return (
                    f"{summary.passed}/{summary.order.total_boxes} passed, "
                    f"{summary.pending} pending, {summary.failed} failed, "
                    f"{summary.remaining} remaining"
                )
        return "0 inspected"

    @staticmethod
    def _format_reinspection_warning(previous: list[InspectionRecord]) -> str:
        latest = sorted(previous, key=lambda r: r.session.started_at)[-1]
        if latest.review is not None:
            outcome = f"Completed — Reviewer: {latest.review.decision.value}"
        else:
            outcome = f"Pending Review — AI: {latest.assessment.recommendation.value}"
        return (
            f"▲  This box already has {len(previous)} prior session(s) "
            f"(latest: {latest.session_id}, {outcome}). Starting will open a new "
            "re-inspection session; earlier sessions are preserved as audit history (D-021)."
        )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_scan_return_pressed(self) -> None:
        raw = self.scan_field.text()
        normalized = raw.strip().upper()
        now = time.monotonic()
        if (
            normalized
            and normalized == self._last_hw_scan_code
            and (now - self._last_hw_scan_ts) < self._SCAN_DEBOUNCE_S
        ):
            self.suppressed_scan_bounces += 1
            return
        self._last_hw_scan_code = normalized
        self._last_hw_scan_ts = now
        self.load_code(raw)

    def _on_find_order_clicked(self) -> None:
        self.lookup_by_order_code(self.order_code_field.text())

    def _on_open_qr_dialog(self) -> None:
        initial = self._box_code.text if self._box_code is not None else ""
        dialog = QrLabelDialog(self._repo, initial_code=initial, parent=self)
        dialog.code_scanned.connect(self._on_simulated_qr_scan)
        dialog.exec()
        dialog.deleteLater()

    def _on_simulated_qr_scan(self, payload: str) -> None:
        self.scan_field.setText(payload)
        self.load_code(payload)

    def _fill_orders(self, select_order_code: Optional[str] = None) -> None:
        self.order_combo.blockSignals(True)
        self.order_combo.clear()
        target_index = 0
        for idx, order in enumerate(self._repo.orders.values()):
            self.order_combo.addItem(
                f"{order.order_code}  ·  {order.product.name} ({order.product.category})  ·  "
                f"{order.supplier}  ·  {order.total_boxes} boxes",
                userData=order,
            )
            if select_order_code and order.order_code == select_order_code:
                target_index = idx
        if self.order_combo.count() > 0:
            self.order_combo.setCurrentIndex(target_index)
        self.order_combo.blockSignals(False)
        self._on_order_changed()

    def _on_order_changed(self) -> None:
        order: Optional[Order] = self.order_combo.currentData()
        self.box_spin.setRange(1, order.total_boxes if order else 1)
        self.box_spin.setSuffix(f"  /  {order.total_boxes}" if order else "")

    def _on_lookup(self) -> None:
        selected: Optional[Order] = self.order_combo.currentData()
        if selected is not None:
            self.load_code(
                BoxCode(selected.order_code, self.box_spin.value(), selected.total_boxes).text
            )

    def _on_start(self) -> None:
        if self._starting_session or self._box_code is None or self._order is None:
            return
        if self._active_session is not None and self._active_session.box_code == self._box_code:
            return
        self._starting_session = True
        self.btn_start.setEnabled(False)
        box_code, order = self._box_code, self._order
        notes = self.notes_field.toPlainText().strip()
        try:
            self.session_requested.emit(box_code, order, notes)
        finally:
            # If navigation was cancelled (e.g., active session could not be released), re-enable
            if self._box_code is not None:
                self._starting_session = False
                self.btn_start.setEnabled(True)

    def _show_error(self, message: str, code: str = "ERR_INVALID_FORMAT") -> None:
        self.last_error_code = code
        self.error_label.setText(f"⚠   [{code}]  {message}")
        self.error_label.setVisible(True)

    def _hide_error(self) -> None:
        self.last_error_code = None
        self.error_label.setVisible(False)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        self.refresh_catalog_data()
        QTimer.singleShot(0, self.scan_field.setFocus)
