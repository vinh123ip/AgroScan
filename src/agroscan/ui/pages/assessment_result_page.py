"""Assessment Result page — step 6: show the system recommendation for one box.

The inspector does not decide here. Submitting moves the session to
Pending Review so the station can continue with the next box (D-020).
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from agroscan.models.inspection_models import InspectionRecord
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard
from agroscan.ui.components.record_detail import RecordDetailWidget


class AssessmentResultPage(ScrollPage):

    submit_requested = Signal(object)   # InspectionRecord
    back_requested   = Signal()
    next_box_scanned = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("AssessmentResultPage", parent)
        self._record: Optional[InspectionRecord] = None
        self._init_ui()

    def _init_ui(self) -> None:
        self.body.addWidget(PageHeader(
            "Assessment Result",
            "Python rule engine result for this box. Submit to send it to the review queue.",
        ))
        self.detail = RecordDetailWidget()
        self.body.addWidget(self.detail)

        next_card = SectionCard("Next Box")
        self.next_scan_field = QLineEdit()
        self.next_scan_field.setObjectName("FormField")
        self.next_scan_field.setPlaceholderText(
            "Scan next box — this box is submitted for review automatically"
        )
        next_card.body.addWidget(self.next_scan_field)
        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        next_card.body.addWidget(self.error_label)
        self.body.addWidget(next_card)

        actions = QHBoxLayout()
        self.btn_back = QPushButton("←  Back to Live Inspection")
        self.btn_back.setObjectName("SecondaryButton")
        self.btn_submit = QPushButton("Submit for Review  →")
        self.btn_submit.setObjectName("PrimaryButton")
        actions.addWidget(self.btn_back)
        actions.addStretch()
        actions.addWidget(self.btn_submit)
        for btn in (self.btn_back, self.btn_submit):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(220)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.body.addLayout(actions)
        self.body.addStretch()

        self.btn_back.clicked.connect(self.back_requested)
        self.btn_submit.clicked.connect(self._on_submit)
        self.next_scan_field.returnPressed.connect(self._on_next_scanned)
        self.next_scan_field.textEdited.connect(lambda: self.error_label.setVisible(False))

    def show_record(self, record: InspectionRecord, images: Optional[list[QImage]] = None) -> None:
        self._record = record
        self.detail.set_record(record, images)
        self.next_scan_field.clear()
        self.error_label.setVisible(False)

    def show_error(self, message: str) -> None:
        self.error_label.setText(f"⚠   {message}")
        self.error_label.setVisible(True)

    def _on_submit(self) -> None:
        if self._record is not None:
            self.submit_requested.emit(self._record)

    def _on_next_scanned(self) -> None:
        text = self.next_scan_field.text().strip()
        if text:
            self.next_scan_field.clear()
            self.next_box_scanned.emit(text)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        QTimer.singleShot(0, self.next_scan_field.setFocus)
