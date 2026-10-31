"""Dashboard page — overview of inspection activities."""

from datetime import date
from typing import Optional

from PySide6.QtWidgets import QGridLayout, QWidget

from agroscan.models.inspection_models import ReviewerDecision
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard
from agroscan.ui.components.stat_card_widget import StatCardWidget
from agroscan.ui.formatting import final_result_text, fmt_datetime


class DashboardPage(ScrollPage):
    """Trang tổng quan: 4 thẻ số liệu hôm nay và bảng hoạt động gần đây.

    Dữ liệu lấy từ ``MockRepository``; sẽ chuyển sang PostgreSQL ở giai đoạn sau.
    """

    _RECENT_LIMIT = 8

    def __init__(self, repo: MockRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__("DashboardPage", parent)
        self._repo = repo
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        self.body.addWidget(PageHeader("Dashboard", "Overview of goods inspection activities"))

        self._cards_grid = QGridLayout()
        self._cards_grid.setSpacing(24)
        self.body.addLayout(self._cards_grid)

        recent = SectionCard("Recent Activity")
        self.recent_table = DataTable(
            ["Session", "Box", "Product", "Status", "Result", "Started"]
        )
        self.recent_table.setMinimumHeight(360)
        recent.body.addWidget(self.recent_table)
        self.body.addWidget(recent)
        self.body.addStretch()

    def refresh(self) -> None:
        """Tính lại số liệu từ repository."""
        today = date.today()
        todays = [r for r in self._repo.records if r.session.started_at.date() == today]
        reviewed = [r for r in self._repo.records if r.review]
        stats = [
            ("BOXES INSPECTED TODAY", str(len(todays)), f"{len(self._repo.records)} in total"),
            ("PENDING REVIEW", str(len(self._repo.pending_records())), "Awaiting reviewer"),
            ("PASSED", str(sum(r.review.decision == ReviewerDecision.PASS for r in reviewed)),
             "Confirmed by reviewer"),
            ("FAILED", str(sum(r.review.decision == ReviewerDecision.FAIL for r in reviewed)),
             "Confirmed by reviewer"),
        ]
        while self._cards_grid.count():
            widget = self._cards_grid.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        for col, (title, value, note) in enumerate(stats):
            self._cards_grid.addWidget(StatCardWidget(title, value, note), 0, col)

        recent = self._repo.all_records()[: self._RECENT_LIMIT]
        self.recent_table.set_rows([
            [
                r.session_id,
                r.session.box_code.text,
                r.session.product.name,
                r.status.value,
                final_result_text(r),
                fmt_datetime(r.session.started_at),
            ]
            for r in recent
        ], recent)

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        self.refresh()
        super().showEvent(event)
