"""Review Queue page — step 7: reviewer confirms Pending Review sessions (D-020, D-027)."""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import (
    InspectionRecord,
    ReviewerDecision,
    ReviewRecord,
)
from agroscan.models.user_models import User
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, SectionCard
from agroscan.ui.components.record_detail import RecordDetailWidget
from agroscan.ui.formatting import fmt_datetime


class ReviewQueuePage(QWidget):

    review_submitted = Signal(object)   # InspectionRecord

    def __init__(
        self, repo: MockRepository, user: User, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ReviewQueuePage")
        self._repo = repo
        self._user = user
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 28)
        root.setSpacing(20)
        root.addWidget(PageHeader(
            "Review Queue",
            "Sessions waiting for a reviewer decision. Oldest first.",
        ))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("ReviewSplitter")
        splitter.setChildrenCollapsible(False)

        # Queue list
        list_panel = QWidget()
        list_layout = QVBoxLayout(list_panel)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self.count_label = QLabel("")
        self.count_label.setObjectName("FormSectionTitle")
        list_layout.addWidget(self.count_label)
        self.queue_table = DataTable(["Box", "Product", "AI", "Inspector", "Started"])
        list_layout.addWidget(self.queue_table)
        splitter.addWidget(list_panel)

        # Detail + decision
        detail_scroll = QScrollArea()
        detail_scroll.setObjectName("PageScrollArea")
        detail_scroll.setWidgetResizable(True)
        detail_content = QWidget()
        detail_content.setObjectName("ScrollContent")
        detail_layout = QVBoxLayout(detail_content)
        detail_layout.setContentsMargins(4, 0, 12, 0)
        detail_layout.setSpacing(18)

        self.empty_label = QLabel("Select a session from the queue to review it.")
        self.empty_label.setObjectName("PageSubtitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.empty_label)

        self.detail = RecordDetailWidget()
        detail_layout.addWidget(self.detail)

        self.decision_card = SectionCard("Your Decision")
        self.notes_field = QPlainTextEdit()
        self.notes_field.setObjectName("NotesField")
        self.notes_field.setPlaceholderText("Optional notes about your decision…")
        self.notes_field.setFixedHeight(90)
        self.decision_card.body.addWidget(self.notes_field)
        buttons = QHBoxLayout()
        self._decision_buttons: dict[ReviewerDecision, QPushButton] = {}
        for decision, name in (
            (ReviewerDecision.PASS,       "PassButton"),
            (ReviewerDecision.FAIL,       "DangerButton"),
            (ReviewerDecision.RE_INSPECT, "SecondaryButton"),
        ):
            btn = QPushButton(decision.value)
            btn.setObjectName(name)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, d=decision: self._on_decide(d))
            buttons.addWidget(btn)
            self._decision_buttons[decision] = btn
        self.decision_card.body.addLayout(buttons)
        detail_layout.addWidget(self.decision_card)
        detail_layout.addStretch()

        detail_scroll.setWidget(detail_content)
        splitter.addWidget(detail_scroll)
        splitter.setSizes([520, 800])
        root.addWidget(splitter, 1)

        self.queue_table.itemSelectionChanged.connect(self._on_selection_changed)

    def refresh(self) -> None:
        pending = self._repo.pending_records()
        self.count_label.setText(f"{len(pending)} PENDING")
        self.queue_table.set_rows([
            [
                r.session.box_code.text,
                r.session.product.name,
                r.assessment.recommendation.value,
                r.session.inspector,
                fmt_datetime(r.session.started_at),
            ]
            for r in pending
        ], pending)
        if pending:
            self.queue_table.selectRow(0)
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        record: Optional[InspectionRecord] = self.queue_table.selected_payload()
        has_record = record is not None
        self.empty_label.setVisible(not has_record)
        self.detail.setVisible(has_record)
        self.decision_card.setVisible(has_record)
        self.notes_field.clear()
        if record:
            self.detail.set_record(record)

    def _on_decide(self, decision: ReviewerDecision) -> None:
        record: Optional[InspectionRecord] = self.queue_table.selected_payload()
        if record is None:
            return
        notes = self.notes_field.toPlainText().strip()
        self._repo.apply_review(record, ReviewRecord(decision, self._user.username, notes))
        self.review_submitted.emit(record)
        self.refresh()

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        self.refresh()
        super().showEvent(event)
