"""QR Box Label Preview and USB Scanner Test Dialog (D-019).

Renders genuine ISO/IEC 18004 QR symbols (with a 4-module white quiet zone so
cameras scan reliably regardless of light/dark UI theme) and provides one-click
test presets for both valid box labels and real-world scan error scenarios.
"""

from typing import Optional

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import BoxCode, Order
from agroscan.services.mock_repository import MockRepository
from agroscan.services.qr_encoder import encode_qr_matrix
from agroscan.ui.components.page_layout import SectionCard, make_hint


class QrCodeWidget(QWidget):
    """Crisp pixel-aligned QR symbol widget with a standard 4-module quiet zone."""

    QUIET_ZONE = 4

    def __init__(self, payload: str = "", size_px: int = 220, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("QrCodeWidget")
        self.setFixedSize(size_px, size_px)
        self._payload = ""
        self._matrix: list[list[bool]] = []
        if payload:
            self.set_payload(payload)

    @property
    def payload(self) -> str:
        return self._payload

    @property
    def matrix(self) -> list[list[bool]]:
        return self._matrix

    def set_payload(self, payload: str) -> None:
        self._payload = payload.strip()
        if not self._payload:
            self._matrix = []
        else:
            try:
                self._matrix = encode_qr_matrix(self._payload)
            except ValueError:
                self._matrix = []
        self.update()

    def to_image(self, scale: int = 8) -> QImage:
        """Render the QR matrix + quiet zone to a crisp monochrome ``QImage``."""
        if not self._matrix:
            img = QImage(64, 64, QImage.Format.Format_RGB32)
            img.fill(QColor("#FFFFFF"))
            return img
        n = len(self._matrix)
        total = (n + 2 * self.QUIET_ZONE) * max(1, scale)
        img = QImage(total, total, QImage.Format.Format_RGB32)
        img.fill(QColor("#FFFFFF"))
        painter = QPainter(img)
        dark = QColor("#0F172A")
        for r, row in enumerate(self._matrix):
            for c, is_dark in enumerate(row):
                if is_dark:
                    painter.fillRect(
                        (c + self.QUIET_ZONE) * scale,
                        (r + self.QUIET_ZONE) * scale,
                        scale,
                        scale,
                        dark,
                    )
        painter.end()
        return img

    def paintEvent(self, _event) -> None:  # noqa: N802 — Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        if not self._matrix:
            painter.end()
            return

        total_modules = len(self._matrix) + 2 * self.QUIET_ZONE
        side = min(self.width(), self.height())
        cell = max(1, side // total_modules)
        drawn = cell * total_modules
        ox = (self.width() - drawn) // 2
        oy = (self.height() - drawn) // 2

        dark = QColor("#0F172A")
        for r, row in enumerate(self._matrix):
            for c, is_dark in enumerate(row):
                if is_dark:
                    x = ox + (c + self.QUIET_ZONE) * cell
                    y = oy + (r + self.QUIET_ZONE) * cell
                    painter.fillRect(QRect(x, y, cell, cell), dark)
        painter.end()


class QrLabelDialog(QDialog):
    """Generate internal ``AGS:`` box QR labels or trigger scanner test cases."""

    code_scanned = Signal(str)

    def __init__(
        self,
        repo: MockRepository,
        initial_code: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AppDialog")
        self.setWindowTitle("AgroScan — Box QR Labels & Scanner Simulator")
        self.setMinimumSize(820, 520)
        self._repo = repo
        self._current_payload = ""

        self._init_ui()
        self._connect_signals()
        self._populate_orders()
        self._populate_presets()
        if initial_code.strip():
            self.set_payload(initial_code.strip())
        else:
            self._sync_from_order_selection()

    def _init_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(24)

        # Left column: order label generator + test scenario presets
        left = QVBoxLayout()
        left.setSpacing(16)

        builder = SectionCard("Generate Internal Box Label (D-019)")
        form = QFormLayout()
        form.setSpacing(12)
        self.order_combo = QComboBox()
        self.order_combo.setObjectName("FormCombo")
        self.box_spin = QSpinBox()
        self.box_spin.setObjectName("FormSpin")
        self.box_spin.setPrefix("Box  ")

        lbl_order = QLabel("Order")
        lbl_order.setObjectName("FormLabel")
        lbl_box = QLabel("Box Number")
        lbl_box.setObjectName("FormLabel")
        form.addRow(lbl_order, self.order_combo)
        form.addRow(lbl_box, self.box_spin)
        builder.body.addLayout(form)
        builder.body.addWidget(make_hint(
            "Internal labels encode AGS:<ORDER>-<BOX>/<TOTAL> so each physical box "
            "maps to a unique inspection session."
        ))
        left.addWidget(builder)

        presets = SectionCard("Scanner Test Scenarios (Valid & Edge Cases)")
        self.preset_combo = QComboBox()
        self.preset_combo.setObjectName("FormCombo")
        self.btn_apply_preset = QPushButton("Load Scenario into Preview")
        self.btn_apply_preset.setObjectName("SecondaryButton")
        self.btn_apply_preset.setFixedHeight(38)
        self.btn_apply_preset.setCursor(Qt.CursorShape.PointingHandCursor)
        presets.body.addWidget(self.preset_combo)
        presets.body.addWidget(self.btn_apply_preset)
        presets.body.addWidget(make_hint(
            "Includes uninspected boxes, re-inspection boxes, accidental retail EAN-13 "
            "barcodes, unknown orders, and lot-size mismatches."
        ))
        left.addWidget(presets)
        left.addStretch()
        root.addLayout(left, 1)

        # Right column: visual QR label card + actions
        right = QVBoxLayout()
        right.setSpacing(16)

        label_card = SectionCard("Box QR Label Preview")
        frame = QFrame()
        frame.setObjectName("QrPreviewFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 20, 20, 18)
        frame_layout.setSpacing(10)

        self.qr_widget = QrCodeWidget(size_px=220)
        frame_layout.addWidget(self.qr_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.payload_label = QLabel("")
        self.payload_label.setObjectName("QrPayloadLabel")
        self.payload_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.payload_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        frame_layout.addWidget(self.payload_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("HintLabel")
        self.meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.meta_label.setWordWrap(True)
        frame_layout.addWidget(self.meta_label)

        label_card.body.addWidget(frame)
        self.copied_label = QLabel("")
        self.copied_label.setObjectName("HintLabel")
        self.copied_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_card.body.addWidget(self.copied_label)
        right.addWidget(label_card, 1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_copy = QPushButton("Copy Code")
        self.btn_copy.setObjectName("SecondaryButton")
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("SecondaryButton")
        self.btn_simulate = QPushButton("Simulate USB Scan  →")
        self.btn_simulate.setObjectName("PrimaryButton")
        for btn in (self.btn_copy, self.btn_close, self.btn_simulate):
            btn.setFixedHeight(42)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(btn)
        right.addLayout(actions)
        root.addLayout(right, 1)

    def _connect_signals(self) -> None:
        self.order_combo.currentIndexChanged.connect(self._on_order_changed)
        self.box_spin.valueChanged.connect(lambda _: self._sync_from_order_selection())
        self.btn_apply_preset.clicked.connect(self._on_apply_preset)
        self.btn_copy.clicked.connect(self._on_copy)
        self.btn_close.clicked.connect(self.reject)
        self.btn_simulate.clicked.connect(self._on_simulate_scan)

    def _populate_orders(self) -> None:
        self.order_combo.blockSignals(True)
        self.order_combo.clear()
        for order in self._repo.orders.values():
            self.order_combo.addItem(
                f"{order.order_code}  ·  {order.product.name} ({order.product.category})",
                userData=order,
            )
        self.order_combo.blockSignals(False)
        self._on_order_changed()

    def _populate_presets(self) -> None:
        presets = [
            ("Valid — Uninspected Box (DH00124 Box 1/8)", "AGS:DH00124-01/08"),
            ("Valid — Re-inspection Box (DH00121 Box 1/10)", "AGS:DH00121-01/10"),
            ("Valid — Pending Review Box (DH00123 Box 5/10)", "AGS:DH00123-05/10"),
            ("Error — Retail EAN-13 Barcode (Not an AGS Label)", "8934567890123"),
            ("Error — Unknown Order Code", "AGS:DH99999-01/10"),
            ("Error — Lot Size Mismatch (12 vs 10 Boxes)", "AGS:DH00123-03/12"),
            ("Error — Box Number Out of Range (15 of 10)", "AGS:DH00123-15/10"),
        ]
        self.preset_combo.clear()
        for title, code in presets:
            self.preset_combo.addItem(f"{title}  [{code}]", userData=code)

    def _on_order_changed(self) -> None:
        order: Optional[Order] = self.order_combo.currentData()
        self.box_spin.blockSignals(True)
        self.box_spin.setRange(1, order.total_boxes if order else 1)
        self.box_spin.setSuffix(f"  /  {order.total_boxes}" if order else "")
        self.box_spin.setValue(1)
        self.box_spin.blockSignals(False)
        self._sync_from_order_selection()

    def _sync_from_order_selection(self) -> None:
        order: Optional[Order] = self.order_combo.currentData()
        if order is None:
            return
        code = BoxCode(order.order_code, self.box_spin.value(), order.total_boxes).text
        self.set_payload(code)

    def _on_apply_preset(self) -> None:
        code = self.preset_combo.currentData()
        if isinstance(code, str):
            self.set_payload(code)

    def set_payload(self, payload: str) -> None:
        """Render ``payload`` on the QR preview card and describe its order metadata."""
        self._current_payload = payload.strip()
        self.copied_label.setText("")
        self.qr_widget.set_payload(self._current_payload)
        self.payload_label.setText(self._current_payload)
        try:
            box_code, order = self._repo.resolve_box(self._current_payload)
            self.meta_label.setText(
                f"{order.product.name} ({order.product.category})  ·  {order.supplier}\n"
                f"Box {box_code.box_number} of {order.total_boxes}  ·  "
                f"Lot: {order.total_boxes} boxes ({order.expected_quantity} units)"
            )
        except ValueError as exc:
            self.meta_label.setText(f"Test negative case: {exc}")

    @property
    def current_payload(self) -> str:
        return self._current_payload

    def _on_copy(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._current_payload)
            self.copied_label.setText(f"✔  Copied '{self._current_payload}' to clipboard.")

    def _on_simulate_scan(self) -> None:
        if self._current_payload:
            self.code_scanned.emit(self._current_payload)
            self.accept()
