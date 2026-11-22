"""Reports & Analytics Page — KPI summaries, order aggregation, and PDF/Excel export (T3.2, D-022)."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from agroscan.models.inspection_models import (
    InspectionRecord,
    OrderSummary,
    ReviewerDecision,
)
from agroscan.services.mock_repository import MockRepository
from agroscan.services.pdf_report_service import (
    DEFAULT_EXPORTS_DIR,
    export_report_excel,
    export_summary_report_pdf,
)
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard
from agroscan.ui.components.stat_card_widget import StatCardWidget
from agroscan.ui.formatting import fmt_datetime


class ReportsPage(ScrollPage):
    """Order-level KPI reports, daily outcome statistics, and PDF/Excel export."""

    report_exported = Signal(str, str)  # (format, file_path)

    def __init__(self, repo: MockRepository, parent: Optional[QWidget] = None) -> None:
        super().__init__("ReportsPage", parent)
        self._repo = repo
        self._filtered_records: list[InspectionRecord] = []
        self._filtered_summaries: list[OrderSummary] = []
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        self.body.addWidget(
            PageHeader(
                "Reports & Analytics",
                "Order-level quality summaries, daily inspection outcomes, and PDF/Excel exports.",
                is_mock=False,
            )
        )

        # Filter & Export Toolbar
        filter_card = SectionCard("Filter & Export Controls")
        bar = QHBoxLayout()
        bar.setSpacing(12)

        prod_lbl = QLabel("Product:")
        prod_lbl.setObjectName("FormLabel")
        self.product_combo = QComboBox()
        self.product_combo.setObjectName("FormCombo")
        self.product_combo.setMinimumWidth(180)
        bar.addWidget(prod_lbl)
        bar.addWidget(self.product_combo)

        from_lbl = QLabel("From:")
        from_lbl.setObjectName("FormLabel")
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setObjectName("FormField")
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setDate(QDate.currentDate().addDays(-14))
        bar.addWidget(from_lbl)
        bar.addWidget(self.start_date_edit)

        to_lbl = QLabel("To:")
        to_lbl.setObjectName("FormLabel")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setObjectName("FormField")
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate())
        bar.addWidget(to_lbl)
        bar.addWidget(self.end_date_edit)

        self.btn_refresh = QPushButton("Apply Filter")
        self.btn_refresh.setObjectName("SecondaryButton")
        self.btn_export_pdf = QPushButton("📄  Export PDF")
        self.btn_export_pdf.setObjectName("PrimaryButton")
        self.btn_export_excel = QPushButton("📊  Export Excel (.xlsx)")
        self.btn_export_excel.setObjectName("SecondaryButton")

        for btn in (self.btn_refresh, self.btn_export_pdf, self.btn_export_excel):
            btn.setFixedHeight(40)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        bar.addWidget(self.btn_refresh)
        bar.addStretch()
        bar.addWidget(self.btn_export_excel)
        bar.addWidget(self.btn_export_pdf)
        filter_card.body.addLayout(bar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("HintLabel")
        filter_card.body.addWidget(self.status_label)
        self.body.addWidget(filter_card)

        # KPI Cards
        self._kpi_grid = QGridLayout()
        self._kpi_grid.setSpacing(20)
        self.body.addLayout(self._kpi_grid)

        # Order-Level Summaries (D-022)
        order_card = SectionCard("Order-Level Quality Summary (D-022)")
        self.order_table = DataTable(
            [
                "Order Code",
                "Product",
                "Supplier",
                "Total Boxes",
                "Passed",
                "Failed",
                "Pending",
                "Remaining",
                "Summary",
            ]
        )
        self.order_table.setMinimumHeight(220)
        order_card.body.addWidget(self.order_table)
        self.body.addWidget(order_card)

        # Daily Outcomes
        daily_card = SectionCard("Daily Inspection Outcomes")
        self.daily_table = DataTable(["Date", "Passed", "Failed", "Pending", "Total Sessions"])
        self.daily_table.setMinimumHeight(200)
        daily_card.body.addWidget(self.daily_table)
        self.body.addWidget(daily_card)

        # Export History
        history_card = SectionCard("Export History")
        self.export_table = DataTable(["Exported At", "Format", "File Path", "Filter Applied"])
        self.export_table.setMinimumHeight(160)
        history_card.body.addWidget(self.export_table)
        self.body.addWidget(history_card)
        self.body.addStretch()

        self.product_combo.currentIndexChanged.connect(lambda _: self.refresh())
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_export_pdf.clicked.connect(self._on_export_pdf_clicked)
        self.btn_export_excel.clicked.connect(self._on_export_excel_clicked)

    def _populate_products(self) -> None:
        current = self.product_combo.currentData()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem("All Products", userData=None)
        for prod in self._repo.products:
            self.product_combo.addItem(f"{prod.name} ({prod.code})", userData=prod.code)
        idx = self.product_combo.findData(current)
        self.product_combo.setCurrentIndex(max(0, idx))
        self.product_combo.blockSignals(False)

    def _current_date_range(self) -> tuple[date, date]:
        q_start = self.start_date_edit.date()
        q_end = self.end_date_edit.date()
        start = date(q_start.year(), q_start.month(), q_start.day())
        end = date(q_end.year(), q_end.month(), q_end.day())
        if end < start:
            start, end = end, start
        return start, end

    def _filter_description(self) -> str:
        prod_code = self.product_combo.currentData()
        start, end = self._current_date_range()
        prod_text = prod_code if prod_code else "All Products"
        return f"{prod_text} ({start.isoformat()} to {end.isoformat()})"

    def refresh(self) -> None:
        self._populate_products()
        prod_code: Optional[str] = self.product_combo.currentData()
        start, end = self._current_date_range()

        self._filtered_records = self._repo.filter_records(
            product_code=prod_code,
            start=start,
            end=end,
        )
        self._filtered_summaries = self._repo.order_summaries(product_code=prod_code)

        # KPI Cards
        total_orders = len(self._filtered_summaries)
        total_sessions = len(self._filtered_records)
        reviewed = [r for r in self._filtered_records if r.review is not None]
        passed_count = sum(1 for r in reviewed if r.review.decision == ReviewerDecision.PASS)
        failed_count = sum(1 for r in reviewed if r.review.decision == ReviewerDecision.FAIL)
        decided_total = passed_count + failed_count
        pass_rate_str = f"{(passed_count / decided_total * 100):.1f}%" if decided_total > 0 else "—"

        kpis = [
            ("ORDERS TRACKED", str(total_orders), "Active orders in scope"),
            ("INSPECTION SESSIONS", str(total_sessions), f"{len(reviewed)} reviewed"),
            ("PASS RATE", pass_rate_str, f"{passed_count} boxes passed"),
            ("FAILED BOXES", str(failed_count), "Confirmed by reviewer"),
        ]
        while self._kpi_grid.count():
            w = self._kpi_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for col, (title, val, sub) in enumerate(kpis):
            self._kpi_grid.addWidget(StatCardWidget(title, val, sub), 0, col)

        # Order summary table
        self.order_table.set_rows(
            [
                [
                    s.order.order_code,
                    s.order.product.name,
                    s.order.supplier,
                    str(s.order.total_boxes),
                    str(s.passed),
                    str(s.failed),
                    str(s.pending),
                    str(s.remaining),
                    s.text,
                ]
                for s in self._filtered_summaries
            ],
            self._filtered_summaries,
        )

        # Daily outcomes table (show non-empty days or recent 7 days)
        daily = self._repo.daily_outcomes(
            start=max(start, end - timedelta(days=14)),
            end=end,
            product_code=prod_code,
        )
        daily_rows = []
        for day, passed, failed, pending in reversed(daily):
            total = passed + failed + pending
            if total > 0 or len(daily_rows) < 5:
                daily_rows.append(
                    [day.isoformat(), str(passed), str(failed), str(pending), str(total)]
                )
        self.daily_table.set_rows(daily_rows)

        # Export history
        history = getattr(self._repo, "export_history", [])
        self.export_table.set_rows(
            [
                [fmt_datetime(ts), fmt, path, flt]
                for ts, fmt, path, flt in history
            ]
        )

    def export_pdf_to(self, output_path: Optional[Union[Path, str]] = None) -> Path:
        """Programmatic PDF export (also called by UI button)."""
        filter_desc = self._filter_description()
        out = export_summary_report_pdf(
            records=self._filtered_records,
            summaries=self._filtered_summaries,
            output_path=output_path,
            filter_description=filter_desc,
        )
        if hasattr(self._repo, "record_export"):
            self._repo.record_export("PDF", str(out), filter_desc)
        self.status_label.setText(f"✔  Exported PDF report to {out}")
        self.refresh()
        self.report_exported.emit("PDF", str(out))
        return out

    def export_excel_to(self, output_path: Optional[Union[Path, str]] = None) -> Path:
        """Programmatic Excel export (also called by UI button)."""
        filter_desc = self._filter_description()
        out = export_report_excel(
            records=self._filtered_records,
            summaries=self._filtered_summaries,
            output_path=output_path,
        )
        if hasattr(self._repo, "record_export"):
            self._repo.record_export("Excel (.xlsx)", str(out), filter_desc)
        self.status_label.setText(f"✔  Exported Excel report to {out}")
        self.refresh()
        self.report_exported.emit("EXCEL", str(out))
        return out

    def _on_export_pdf_clicked(self) -> None:
        DEFAULT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        default_file = str(DEFAULT_EXPORTS_DIR / "AgroScan_Inspection_Report.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Inspection Report", default_file, "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            self.export_pdf_to(path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF Export Failed", f"Could not export PDF:\n{exc}")

    def _on_export_excel_clicked(self) -> None:
        DEFAULT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        default_file = str(DEFAULT_EXPORTS_DIR / "AgroScan_Inspection_Report.xlsx")
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Excel Inspection Report", default_file, "Excel Workbook (*.xlsx)"
        )
        if not path:
            return
        try:
            self.export_excel_to(path)
        except Exception as exc:
            QMessageBox.critical(self, "Excel Export Failed", f"Could not export Excel:\n{exc}")

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)

