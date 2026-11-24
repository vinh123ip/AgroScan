"""Bilingual Order Progress & Review Status Dashboard (3.4.5.2)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from agroscan.models.inspection_models import ReviewerDecision
from agroscan.services.i18n import language_manager, tr
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard
from agroscan.ui.components.stat_card_widget import StatCardWidget
from agroscan.ui.formatting import final_result_text, fmt_datetime, fmt_status


class DashboardPage(ScrollPage):
    """Bilingual (EN/VI) operational dashboard: KPIs, Review Status breakdown,
    Order Progress table (via ``repo.order_summaries()``), and Recent Activity.
    """

    _RECENT_LIMIT = 8

    def __init__(self, repo: MockRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__("DashboardPage", parent)
        self._repo = repo
        self._init_ui()
        language_manager().language_changed.connect(self.retranslate_ui)
        self.refresh()

    def _init_ui(self) -> None:
        self.header = PageHeader(tr("dashboard.title"), tr("dashboard.subtitle"), is_mock=False)
        self.body.addWidget(self.header)

        self._cards_grid = QGridLayout()
        self._cards_grid.setSpacing(24)
        self.body.addLayout(self._cards_grid)

        # Review Status Breakdown (3.4.5.2)
        self.review_status_card = SectionCard(tr("dashboard.review_status_section"))
        pills_row = QHBoxLayout()
        pills_row.setSpacing(12)
        self.pill_pending = QLabel("")
        self.pill_pending.setObjectName("ReviewPill")
        self.pill_pending.setProperty("kind", "pending")
        self.pill_reinspect = QLabel("")
        self.pill_reinspect.setObjectName("ReviewPill")
        self.pill_reinspect.setProperty("kind", "reinspect")
        self.pill_passed = QLabel("")
        self.pill_passed.setObjectName("ReviewPill")
        self.pill_passed.setProperty("kind", "passed")
        self.pill_failed = QLabel("")
        self.pill_failed.setObjectName("ReviewPill")
        self.pill_failed.setProperty("kind", "failed")
        for pill in (self.pill_pending, self.pill_reinspect, self.pill_passed, self.pill_failed):
            pills_row.addWidget(pill)
        pills_row.addStretch()
        self.review_status_card.body.addLayout(pills_row)
        self.body.addWidget(self.review_status_card)

        # Order Progress Table (3.4.5.2)
        self.order_card = SectionCard(tr("dashboard.order_progress_section"))
        self.order_progress_table = DataTable(self._order_headers())
        self.order_progress_table.setMinimumHeight(230)
        self.order_card.body.addWidget(self.order_progress_table)
        self.body.addWidget(self.order_card)

        # Recent Activity Table
        self.recent_card = SectionCard(tr("dashboard.recent_section"))
        self.recent_table = DataTable(self._recent_headers())
        self.recent_table.setMinimumHeight(300)
        self.recent_card.body.addWidget(self.recent_table)
        self.body.addWidget(self.recent_card)
        self.body.addStretch()

    @staticmethod
    def _order_headers() -> list[str]:
        return [
            tr("dashboard.col.order"),
            tr("dashboard.col.product"),
            tr("dashboard.col.supplier"),
            tr("dashboard.col.progress"),
            tr("dashboard.col.passed"),
            tr("dashboard.col.failed"),
            tr("dashboard.col.pending"),
            tr("dashboard.col.reinspect"),
            tr("dashboard.col.remaining"),
            tr("dashboard.col.completion"),
        ]

    @staticmethod
    def _recent_headers() -> list[str]:
        return [
            tr("dashboard.col.session"),
            tr("dashboard.col.box"),
            tr("dashboard.col.product"),
            tr("dashboard.col.status"),
            tr("dashboard.col.result"),
            tr("dashboard.col.started"),
        ]

    def retranslate_ui(self, _lang: str = "") -> None:
        # Update PageHeader title & subtitle labels
        labels = self.header.findChildren(QLabel)
        if len(labels) >= 2:
            labels[0].setText(tr("dashboard.title"))
            labels[1].setText(tr("dashboard.subtitle"))
        for card, key in (
            (self.review_status_card, "dashboard.review_status_section"),
            (self.order_card, "dashboard.order_progress_section"),
            (self.recent_card, "dashboard.recent_section"),
        ):
            title_lbl = card.findChild(QLabel, "FormSectionTitle")
            if title_lbl is not None:
                title_lbl.setText(tr(key).upper())
        self.order_progress_table.setHorizontalHeaderLabels(self._order_headers())
        self.recent_table.setHorizontalHeaderLabels(self._recent_headers())
        self.refresh()

    def refresh(self) -> None:
        """Recompute KPIs, Review Status breakdown, Order Progress, and Recent Activity."""
        all_recs = self._repo.records
        today = date.today()
        todays = [r for r in all_recs if r.session.started_at.date() == today]
        reviewed = [r for r in all_recs if r.review is not None]
        pending_first = len(self._repo.pending_records())
        passed_total = sum(1 for r in reviewed if r.review.decision == ReviewerDecision.PASS)
        failed_total = sum(1 for r in reviewed if r.review.decision == ReviewerDecision.FAIL)
        reinspect_total = sum(1 for r in reviewed if r.review.decision == ReviewerDecision.RE_INSPECT)

        stats = [
            (
                tr("dashboard.kpi.today"),
                str(len(todays)),
                tr("dashboard.kpi.today_note", total=len(all_recs)),
            ),
            (
                tr("dashboard.kpi.pending"),
                str(pending_first),
                tr("dashboard.kpi.pending_note", reinspect=reinspect_total),
            ),
            (
                tr("dashboard.kpi.passed"),
                str(passed_total),
                tr("dashboard.kpi.confirmed"),
            ),
            (
                tr("dashboard.kpi.failed"),
                str(failed_total),
                tr("dashboard.kpi.confirmed"),
            ),
        ]
        while self._cards_grid.count():
            widget = self._cards_grid.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        for col, (title, value, note) in enumerate(stats):
            self._cards_grid.addWidget(StatCardWidget(title, value, note), 0, col)

        # Review status breakdown pills
        self.pill_pending.setText(tr("dashboard.review_status.pending", n=pending_first))
        self.pill_reinspect.setText(tr("dashboard.review_status.reinspect", n=reinspect_total))
        self.pill_passed.setText(tr("dashboard.review_status.passed", n=passed_total))
        self.pill_failed.setText(tr("dashboard.review_status.failed", n=failed_total))

        # Order progress table
        summaries = self._repo.order_summaries()
        self.order_progress_table.set_rows(
            [
                [
                    s.order.order_code,
                    s.order.product.name,
                    s.order.supplier,
                    f"{s.passed}/{s.order.total_boxes}",
                    str(s.passed),
                    str(s.failed),
                    str(max(0, s.pending - s.reinspect)),
                    str(s.reinspect),
                    str(s.remaining),
                    f"{s.completion_rate:.0f}%",
                ]
                for s in summaries
            ],
            summaries,
        )

        # Recent activity table
        recent = self._repo.all_records()[: self._RECENT_LIMIT]
        self.recent_table.set_rows(
            [
                [
                    r.session_id,
                    r.session.box_code.text,
                    r.session.product.name,
                    fmt_status(r.status.value),
                    final_result_text(r),
                    fmt_datetime(r.session.started_at),
                ]
                for r in recent
            ],
            recent,
        )

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        self.refresh()
        super().showEvent(event)
