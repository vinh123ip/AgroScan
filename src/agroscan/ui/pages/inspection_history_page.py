"""Inspection History Page — search, filter, view session details & export PDF certificate (T3.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import InspectionRecord, SessionStatus
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_repository import MockRepository
from agroscan.services.pdf_report_service import (
    DEFAULT_EXPORTS_DIR,
    export_inspection_record_pdf,
)
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, SectionCard
from agroscan.ui.components.record_detail import RecordDetailWidget
from agroscan.ui.formatting import final_result_text, fmt_datetime


class InspectionHistoryPage(QWidget):
    """Searchable master-detail view of all historical inspection sessions."""

    certificate_exported = Signal(str)  # exported PDF path

    def __init__(
        self,
        repo: MockRepository,
        settings: Optional[AppSettings] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InspectionHistoryPage")
        self._repo = repo
        self._settings = settings or AppSettings()
        self._records: list[InspectionRecord] = []
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 28)
        root.setSpacing(18)

        root.addWidget(
            PageHeader(
                "Inspection History",
                "Search past inspection sessions by box code, product, or status and export PDF certificates.",
                is_mock=False,
            )
        )

        # Search & filter bar
        filter_card = SectionCard("Search & Filter")
        bar = QHBoxLayout()
        bar.setSpacing(12)

        self.search_field = QLineEdit()
        self.search_field.setObjectName("FormField")
        self.search_field.setPlaceholderText("Search by Box Code (e.g. AGS:DH00123-01/10) or Session ID…")
        bar.addWidget(self.search_field, 2)

        self.product_combo = QComboBox()
        self.product_combo.setObjectName("FormCombo")
        self.product_combo.setMinimumWidth(160)
        bar.addWidget(self.product_combo)

        self.status_combo = QComboBox()
        self.status_combo.setObjectName("FormCombo")
        self.status_combo.setMinimumWidth(160)
        self.status_combo.addItem("All Statuses", userData=None)
        for st in SessionStatus:
            self.status_combo.addItem(st.value, userData=st)
        bar.addWidget(self.status_combo)

        self.btn_clear = QPushButton("Reset")
        self.btn_clear.setObjectName("SecondaryButton")
        self.btn_clear.setFixedHeight(40)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(self.btn_clear)

        self.btn_export_cert = QPushButton("📄  Export Certificate PDF")
        self.btn_export_cert.setObjectName("PrimaryButton")
        self.btn_export_cert.setFixedHeight(40)
        self.btn_export_cert.setCursor(Qt.CursorShape.PointingHandCursor)
        bar.addWidget(self.btn_export_cert)

        filter_card.body.addLayout(bar)
        self.notice_label = QLabel("")
        self.notice_label.setObjectName("HintLabel")
        filter_card.body.addWidget(self.notice_label)
        root.addWidget(filter_card)

        # Master-detail splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("HistorySplitter")
        splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.count_label = QLabel("0 SESSIONS")
        self.count_label.setObjectName("FormSectionTitle")
        left_layout.addWidget(self.count_label)
        self.history_table = DataTable(
            ["Session ID", "Box Code", "Product", "Status", "Outcome", "Started"]
        )
        left_layout.addWidget(self.history_table)
        splitter.addWidget(left_panel)

        detail_scroll = QScrollArea()
        detail_scroll.setObjectName("PageScrollArea")
        detail_scroll.setWidgetResizable(True)
        detail_content = QWidget()
        detail_content.setObjectName("ScrollContent")
        detail_layout = QVBoxLayout(detail_content)
        detail_layout.setContentsMargins(4, 0, 12, 0)
        detail_layout.setSpacing(18)

        self.empty_label = QLabel("Select an inspection session from the table to view full details.")
        self.empty_label.setObjectName("PageSubtitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.empty_label)

        self.detail_widget = RecordDetailWidget()
        detail_layout.addWidget(self.detail_widget)
        detail_layout.addStretch()

        detail_scroll.setWidget(detail_content)
        splitter.addWidget(detail_scroll)
        splitter.setSizes([580, 740])
        root.addWidget(splitter, 1)

        self.search_field.textChanged.connect(lambda _: self._apply_filters())
        self.product_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        self.status_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        self.btn_clear.clicked.connect(self._on_reset_filters)
        self.history_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_export_cert.clicked.connect(self._on_export_certificate_clicked)

    def _populate_products(self) -> None:
        current = self.product_combo.currentData()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem("All Products", userData=None)
        for p in self._repo.products:
            self.product_combo.addItem(f"{p.name} ({p.code})", userData=p.code)
        idx = self.product_combo.findData(current)
        self.product_combo.setCurrentIndex(max(0, idx))
        self.product_combo.blockSignals(False)

    def refresh(self) -> None:
        self._populate_products()
        self._apply_filters()

    def _on_reset_filters(self) -> None:
        self.search_field.blockSignals(True)
        self.product_combo.blockSignals(True)
        self.status_combo.blockSignals(True)
        self.search_field.clear()
        self.product_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.search_field.blockSignals(False)
        self.product_combo.blockSignals(False)
        self.status_combo.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        query = self.search_field.text().strip()
        prod_code = self.product_combo.currentData()
        status = self.status_combo.currentData()

        self._records = self._repo.filter_records(
            text=query,
            product_code=prod_code,
            status=status,
        )
        self.count_label.setText(f"{len(self._records)} SESSIONS FOUND")
        self.history_table.set_rows(
            [
                [
                    r.session_id,
                    r.session.box_code.text,
                    r.session.product.name,
                    r.status.value,
                    final_result_text(r),
                    fmt_datetime(r.session.started_at),
                ]
                for r in self._records
            ],
            self._records,
        )
        if self._records:
            self.history_table.selectRow(0)
        self._on_selection_changed()

    def selected_record(self) -> Optional[InspectionRecord]:
        return self.history_table.selected_payload()

    def _on_selection_changed(self) -> None:
        record = self.selected_record()
        has_rec = record is not None
        self.empty_label.setVisible(not has_rec)
        self.detail_widget.setVisible(has_rec)
        self.btn_export_cert.setEnabled(has_rec)
        if record is not None:
            self.detail_widget.set_record(record)

    def export_selected_certificate(
        self, output_path: Optional[Union[Path, str]] = None
    ) -> Optional[Path]:
        """Export a PDF Inspection Certificate for the currently selected record."""
        record = self.selected_record()
        if record is None:
            return None
        out = export_inspection_record_pdf(
            record=record,
            output_path=output_path,
            settings=self._settings,
        )
        if hasattr(self._repo, "record_export"):
            self._repo.record_export("Certificate PDF", str(out), record.session_id)
        self.notice_label.setText(f"✔  Exported certificate for {record.session_id} to {out}")
        self.certificate_exported.emit(str(out))
        return out

    def _on_export_certificate_clicked(self) -> None:
        record = self.selected_record()
        if record is None:
            return
        DEFAULT_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        default_file = str(DEFAULT_EXPORTS_DIR / f"Certificate_{record.session_id}.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Inspection Certificate PDF",
            default_file,
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        try:
            self.export_selected_certificate(path)
        except Exception as exc:
            QMessageBox.critical(self, "Certificate Export Failed", f"Could not generate PDF:\n{exc}")

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)

