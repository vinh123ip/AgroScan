"""Box Intake page — step 3: scan a box QR code and open an inspection session.

A USB 2D scanner behaves like a keyboard: it types the code and sends Enter,
so the scan field only needs to react to ``returnPressed`` (D-019).
"""

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

from agroscan.models.inspection_models import BoxCode, InspectionSession, Order
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.page_layout import (
    KeyValueGrid,
    PageHeader,
    ScrollPage,
    SectionCard,
    make_hint,
)


class BoxIntakePage(ScrollPage):

    session_requested = Signal(object, object, str)   # BoxCode, Order, notes
    resume_requested  = Signal()

    def __init__(self, repo: MockRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__("BoxIntakePage", parent)
        self._repo = repo
        self._box_code: Optional[BoxCode] = None
        self._order: Optional[Order] = None
        self._init_ui()
        self._connect_signals()
        self.reset_form()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.body.addWidget(PageHeader(
            "Box Intake",
            "Scan the QR label on the box to open an inspection session. "
            "One box code = one box = one session.",
        ))

        # Banner phiên đang mở (bước 12: phiên chưa xong vẫn được quản lý)
        self.resume_banner = QFrame()
        self.resume_banner.setObjectName("InfoBanner")
        banner_layout = QHBoxLayout(self.resume_banner)
        banner_layout.setContentsMargins(20, 14, 20, 14)
        self.resume_label = QLabel("")
        self.resume_label.setObjectName("InfoBannerText")
        self.btn_resume = QPushButton("Resume Inspection  →")
        self.btn_resume.setObjectName("PrimaryButton")
        self.btn_resume.setFixedHeight(38)
        banner_layout.addWidget(self.resume_label, 1)
        banner_layout.addWidget(self.btn_resume)
        self.resume_banner.setVisible(False)
        self.body.addWidget(self.resume_banner)

        # Scan
        scan_card = SectionCard("Scan Box Code")
        self.scan_field = QLineEdit()
        self.scan_field.setObjectName("ScanField")
        self.scan_field.setPlaceholderText("Scan QR code or type  AGS:DH00123-03/10  then press Enter")
        scan_card.body.addWidget(self.scan_field)
        scan_card.body.addWidget(make_hint(
            "The barcode scanner types the code into this field automatically. "
            "Keep the cursor here while scanning."
        ))
        self.body.addWidget(scan_card)

        # Manual lookup
        lookup_card = SectionCard("Or Find by Order")
        lookup_row = QHBoxLayout()
        lookup_row.setSpacing(12)
        self.order_combo = QComboBox()
        self.order_combo.setObjectName("FormCombo")
        self.box_spin = QSpinBox()
        self.box_spin.setObjectName("FormSpin")
        self.box_spin.setPrefix("Box  ")
        self.box_spin.setMinimumWidth(140)
        self.btn_lookup = QPushButton("Load Box")
        self.btn_lookup.setObjectName("SecondaryButton")
        self.btn_lookup.setFixedHeight(42)
        lookup_row.addWidget(self.order_combo, 1)
        lookup_row.addWidget(self.box_spin)
        lookup_row.addWidget(self.btn_lookup)
        lookup_card.body.addLayout(lookup_row)
        self.body.addWidget(lookup_card)

        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.body.addWidget(self.error_label)

        # Box info
        self.info_card = SectionCard("Box Information")
        self.info_grid = KeyValueGrid(columns=3)
        self.info_card.body.addWidget(self.info_grid)
        self.reinspect_label = QLabel("")
        self.reinspect_label.setObjectName("WarningNote")
        self.reinspect_label.setWordWrap(True)
        self.info_card.body.addWidget(self.reinspect_label)
        self.notes_field = QPlainTextEdit()
        self.notes_field.setObjectName("NotesField")
        self.notes_field.setPlaceholderText("Optional notes about this box…")
        self.notes_field.setFixedHeight(80)
        self.info_card.body.addWidget(self.notes_field)
        self.body.addWidget(self.info_card)

        actions = QHBoxLayout()
        actions.addStretch()
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("SecondaryButton")
        self.btn_start = QPushButton("Start Inspection  →")
        self.btn_start.setObjectName("PrimaryButton")
        for btn, width in ((self.btn_clear, 120), (self.btn_start, 200)):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(width)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(btn)
        self.body.addLayout(actions)
        self.body.addStretch()

    def _connect_signals(self) -> None:
        self.scan_field.returnPressed.connect(lambda: self.load_code(self.scan_field.text()))
        self.scan_field.textEdited.connect(self._hide_error)
        self.order_combo.currentIndexChanged.connect(self._on_order_changed)
        self.btn_lookup.clicked.connect(self._on_lookup)
        self.btn_clear.clicked.connect(self.reset_form)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_resume.clicked.connect(self.resume_requested)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset_form(self) -> None:
        self._box_code, self._order = None, None
        self.scan_field.clear()
        self.notes_field.clear()
        self._hide_error()
        self.info_card.setVisible(False)
        self.btn_start.setEnabled(False)
        self._fill_orders()
        QTimer.singleShot(0, self.scan_field.setFocus)

    def set_active_session(self, session: Optional[InspectionSession]) -> None:
        """Hiện banner nếu còn phiên đang kiểm tra dở."""
        self.resume_banner.setVisible(session is not None)
        if session:
            self.resume_label.setText(
                f"Session {session.session_id} for box {session.box_code} is still in progress."
            )

    def load_code(self, text: str) -> bool:
        """Xác thực mã hộp và hiển thị thông tin. Trả về True nếu hợp lệ."""
        try:
            box_code, order = self._repo.resolve_box(text)
        except ValueError as exc:
            self._show_error(str(exc))
            self.info_card.setVisible(False)
            self.btn_start.setEnabled(False)
            return False

        self._box_code, self._order = box_code, order
        self.scan_field.setText(box_code.text)
        self._hide_error()

        previous = self._repo.records_for_box(box_code)
        self.info_grid.set_items([
            ("Order",             order.order_code),
            ("Box",               f"{box_code.box_number} of {order.total_boxes}"),
            ("Product",           order.product.name),
            ("Supplier",          order.supplier),
            ("Expected Quantity", f"{order.expected_quantity} units / order"),
            ("YOLO Model",        order.product.model_file),
        ])
        self.reinspect_label.setVisible(bool(previous))
        if previous:
            self.reinspect_label.setText(
                f"▲  This box already has {len(previous)} session(s). Starting will create a "
                "new re-inspection session; earlier sessions are kept as history."
            )
        self.info_card.setVisible(True)
        self.btn_start.setEnabled(True)
        self.btn_start.setFocus()
        return True

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _fill_orders(self) -> None:
        self.order_combo.blockSignals(True)
        self.order_combo.clear()
        for order in self._repo.orders.values():
            self.order_combo.addItem(
                f"{order.order_code}  ·  {order.product.name}  ·  {order.supplier}", userData=order
            )
        self.order_combo.blockSignals(False)
        self._on_order_changed()

    def _on_order_changed(self) -> None:
        order: Optional[Order] = self.order_combo.currentData()
        self.box_spin.setRange(1, order.total_boxes if order else 1)
        self.box_spin.setSuffix(f"  /  {order.total_boxes}" if order else "")

    def _on_lookup(self) -> None:
        order: Optional[Order] = self.order_combo.currentData()
        if order:
            self.load_code(BoxCode(order.order_code, self.box_spin.value(), order.total_boxes).text)

    def _on_start(self) -> None:
        if self._box_code and self._order:
            self.session_requested.emit(
                self._box_code, self._order, self.notes_field.toPlainText().strip()
            )

    def _show_error(self, message: str) -> None:
        self.error_label.setText(f"⚠   {message}")
        self.error_label.setVisible(True)

    def _hide_error(self) -> None:
        self.error_label.setVisible(False)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        QTimer.singleShot(0, self.scan_field.setFocus)
