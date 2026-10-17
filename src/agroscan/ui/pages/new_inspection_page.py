"""New Inspection page — M2.1.

Allows the inspector to create a new inspection session and enter
batch information before proceeding to the image upload step (M2.2).
"""

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import CommodityType, InspectionSession


class NewInspectionPage(QWidget):
    """M2.1 — Tạo phiên kiểm định mới và nhập thông tin lô hàng.

    Signals:
        inspection_started(InspectionSession): Phát khi Inspector xác nhận bắt đầu.
        inspection_cancelled():               Phát khi Inspector huỷ, về Dashboard.
    """

    inspection_started   = Signal(InspectionSession)
    inspection_cancelled = Signal()

    _SESSION_ID_PREFIX: str = "INS"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NewInspectionPage")
        self._session_counter: int = 1

        self._init_ui()
        self._connect_signals()
        self._refresh_session_id()

    # ------------------------------------------------------------------
    # Private init helpers
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Khởi tạo layout tổng thể với scroll area."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("PageScrollArea")

        scroll_content = QWidget()
        scroll_content.setObjectName("ScrollContent")

        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(48, 40, 48, 48)
        content_layout.setSpacing(28)

        content_layout.addLayout(self._build_page_header())
        content_layout.addWidget(self._build_form_card())
        content_layout.addWidget(self._build_error_label())
        content_layout.addLayout(self._build_action_bar())
        content_layout.addStretch()

        scroll.setWidget(scroll_content)
        root.addWidget(scroll)

    def _build_page_header(self) -> QVBoxLayout:
        """Tạo section tiêu đề trang."""
        layout = QVBoxLayout()
        layout.setSpacing(8)

        title = QLabel("New Inspection")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Fill in the batch details below and press Start Inspection "
            "to proceed to the image upload step."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return layout

    def _build_form_card(self) -> QFrame:
        """Tạo card chứa toàn bộ form nhập liệu."""
        card = QFrame()
        card.setObjectName("FormCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 32, 36, 32)
        card_layout.setSpacing(20)

        # Section: Batch Information
        batch_section_title = QLabel("Batch Information")
        batch_section_title.setObjectName("FormSectionTitle")
        card_layout.addWidget(batch_section_title)

        card_layout.addLayout(self._build_form_fields())

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("FormDivider")
        card_layout.addWidget(divider)

        # Section: Notes
        notes_section_title = QLabel("Notes")
        notes_section_title.setObjectName("FormSectionTitle")
        card_layout.addWidget(notes_section_title)

        self.notes_field = QPlainTextEdit()
        self.notes_field.setObjectName("NotesField")
        self.notes_field.setPlaceholderText(
            "Optional — any additional remarks about this batch or inspection conditions..."
        )
        self.notes_field.setFixedHeight(104)
        card_layout.addWidget(self.notes_field)

        return card

    def _build_form_fields(self) -> QFormLayout:
        """Tạo QFormLayout chứa các trường nhập liệu chính."""
        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        # Session ID — read-only, auto-generated
        self.session_id_field = QLineEdit()
        self.session_id_field.setObjectName("ReadOnlyField")
        self.session_id_field.setReadOnly(True)
        self.session_id_field.setPlaceholderText("Auto-generated")
        form.addRow(self._make_form_label("Session ID"), self.session_id_field)

        # Batch Number — required
        self.batch_number_field = QLineEdit()
        self.batch_number_field.setObjectName("FormField")
        self.batch_number_field.setPlaceholderText("e.g.  BTN-2026-0042")
        form.addRow(
            self._make_form_label("Batch Number", required=True),
            self.batch_number_field,
        )

        # Commodity Type — required
        self.commodity_combo = QComboBox()
        self.commodity_combo.setObjectName("FormCombo")
        self.commodity_combo.addItem("— Select commodity type —", userData=None)
        for commodity in CommodityType:
            self.commodity_combo.addItem(commodity.value, userData=commodity)
        form.addRow(
            self._make_form_label("Commodity Type", required=True),
            self.commodity_combo,
        )

        # Origin Country — optional
        self.origin_country_field = QLineEdit()
        self.origin_country_field.setObjectName("FormField")
        self.origin_country_field.setPlaceholderText("e.g.  Vietnam")
        form.addRow(
            self._make_form_label("Origin Country"),
            self.origin_country_field,
        )

        # Inspector Name — optional
        self.inspector_name_field = QLineEdit()
        self.inspector_name_field.setObjectName("FormField")
        self.inspector_name_field.setPlaceholderText("e.g.  Nguyen Van A")
        form.addRow(
            self._make_form_label("Inspector Name"),
            self.inspector_name_field,
        )

        return form

    def _build_error_label(self) -> QLabel:
        """Tạo label hiển thị lỗi validation inline bên dưới form."""
        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        return self.error_label

    def _build_action_bar(self) -> QHBoxLayout:
        """Tạo thanh hành động với Cancel và Start Inspection."""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.setFixedHeight(44)
        self.btn_cancel.setMinimumWidth(120)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_start = QPushButton("Start Inspection  →")
        self.btn_start.setObjectName("PrimaryButton")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setMinimumWidth(184)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)

        layout.addWidget(self.btn_cancel)
        layout.addWidget(self.btn_start)
        return layout

    @staticmethod
    def _make_form_label(text: str, required: bool = False) -> QLabel:
        """Tạo label form; thêm dấu * đỏ nếu trường bắt buộc."""
        display = (
            f"{text}&nbsp;&nbsp;<span style='color:#F87171;font-size:15px;'>*</span>"
            if required
            else text
        )
        label = QLabel(display)
        label.setObjectName("FormLabel")
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    def _connect_signals(self) -> None:
        """Kết nối signal/slot nội bộ."""
        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.batch_number_field.textChanged.connect(self._clear_inline_error)
        self.commodity_combo.currentIndexChanged.connect(self._clear_inline_error)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset_form(self) -> None:
        """Xóa toàn bộ form về trạng thái ban đầu và sinh Session ID mới."""
        self._session_counter += 1
        self._refresh_session_id()
        self.batch_number_field.clear()
        self.commodity_combo.setCurrentIndex(0)
        self.origin_country_field.clear()
        self.inspector_name_field.clear()
        self.notes_field.clear()
        self._clear_inline_error()

    def get_form_data(self) -> InspectionSession:
        """Thu thập dữ liệu form, trả về InspectionSession.

        Chỉ gọi sau khi ``_validate_form()`` đã xác nhận hợp lệ.
        """
        commodity: CommodityType = self.commodity_combo.currentData()
        return InspectionSession(
            session_id=self.session_id_field.text(),
            batch_number=self.batch_number_field.text().strip(),
            commodity_type=commodity,
            origin_country=self.origin_country_field.text().strip(),
            inspector_name=self.inspector_name_field.text().strip(),
            notes=self.notes_field.toPlainText().strip(),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_session_id(self) -> str:
        """Tạo Session ID định dạng INS-YYYYMMDD-XXXX."""
        date_str = datetime.now().strftime("%Y%m%d")
        return f"{self._SESSION_ID_PREFIX}-{date_str}-{self._session_counter:04d}"

    def _refresh_session_id(self) -> None:
        """Cập nhật trường Session ID với giá trị mới nhất."""
        self.session_id_field.setText(self._generate_session_id())

    def _validate_form(self) -> tuple[bool, str]:
        """Kiểm tra tính hợp lệ của các trường bắt buộc.

        Returns:
            Tuple (is_valid, error_message). Nếu hợp lệ, error_message rỗng.
        """
        if not self.batch_number_field.text().strip():
            return False, "Batch Number is required."
        if self.commodity_combo.currentIndex() == 0:
            return False, "Please select a Commodity Type."
        return True, ""

    def _clear_inline_error(self) -> None:
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _show_inline_error(self, message: str) -> None:
        self.error_label.setText(f"⚠   {message}")
        self.error_label.setVisible(True)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_start_clicked(self) -> None:
        """Validate → tạo InspectionSession → emit inspection_started."""
        is_valid, error_msg = self._validate_form()
        if not is_valid:
            self._show_inline_error(error_msg)
            return
        session = self.get_form_data()
        self.inspection_started.emit(session)

    def _on_cancel_clicked(self) -> None:
        """Emit inspection_cancelled để MainWindow về Dashboard."""
        self._clear_inline_error()
        self.inspection_cancelled.emit()
