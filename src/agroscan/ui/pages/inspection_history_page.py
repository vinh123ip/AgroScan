"""Versioned History Explorer, Audit Detail & Attributed Notes Page (3.4.4.2, 3.4.5.9)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
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
from agroscan.models.user_models import User
from agroscan.services.app_settings import AppSettings
from agroscan.services.i18n import language_manager, tr
from agroscan.services.mock_repository import MockRepository
try:
    from agroscan.services.pdf_report_service import (
        DEFAULT_EXPORTS_DIR,
        export_inspection_record_pdf,
    )
except ImportError:
    DEFAULT_EXPORTS_DIR = Path.cwd() / "exports"
    export_inspection_record_pdf = None  # type: ignore[assignment]
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, SectionCard
from agroscan.ui.components.record_detail import RecordDetailWidget
from agroscan.ui.formatting import final_result_text, fmt_datetime, fmt_status


class InspectionHistoryPage(QWidget):
    """Searchable master-detail explorer with Versioned History, Date/Outcome filters,
    Audit Trail timeline, and interactive Attributed Notes.
    """

    certificate_exported = Signal(str)  # exported PDF path

    def __init__(
        self,
        repo: MockRepository,
        settings: Optional[AppSettings] = None,
        current_user: Optional[User] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("InspectionHistoryPage")
        self._repo = repo
        self._settings = settings or AppSettings()
        self._current_user = current_user
        self._records: list[InspectionRecord] = []
        self._init_ui()
        language_manager().language_changed.connect(self.retranslate_ui)
        self.refresh()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 32, 40, 28)
        root.setSpacing(16)

        self.header = PageHeader(tr("history.title"), tr("history.subtitle"), is_mock=False)
        root.addWidget(self.header)

        # Search & Advanced Filter Card (3.4.5.9)
        self.filter_card = SectionCard(tr("history.filter_card"))

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.search_field = QLineEdit()
        self.search_field.setObjectName("FormField")
        self.search_field.setPlaceholderText(tr("history.search_placeholder"))
        row1.addWidget(self.search_field, 2)

        self.product_combo = QComboBox()
        self.product_combo.setObjectName("FormCombo")
        self.product_combo.setMinimumWidth(150)
        row1.addWidget(self.product_combo)

        self.status_combo = QComboBox()
        self.status_combo.setObjectName("FormCombo")
        self.status_combo.setMinimumWidth(145)
        self.status_combo.addItem(tr("history.all_statuses"), userData=None)
        for st in SessionStatus:
            self.status_combo.addItem(fmt_status(st.value), userData=st)
        row1.addWidget(self.status_combo)

        self.outcome_combo = QComboBox()
        self.outcome_combo.setObjectName("FormCombo")
        self.outcome_combo.setMinimumWidth(145)
        self.outcome_combo.addItem(tr("history.all_outcomes"), userData=None)
        for outcome_val in ("Pass", "Fail", "Re-inspect", "Needs Review"):
            self.outcome_combo.addItem(outcome_val, userData=outcome_val)
        row1.addWidget(self.outcome_combo)
        self.filter_card.body.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.setObjectName("FormCombo")
        self.view_mode_combo.setMinimumWidth(155)
        self.view_mode_combo.addItem(tr("history.view.all"), userData="all")
        self.view_mode_combo.addItem(tr("history.view.grouped"), userData="grouped")
        row2.addWidget(self.view_mode_combo)

        self.date_filter_check = QCheckBox(tr("history.date_filter"))
        self.date_filter_check.setChecked(False)
        row2.addWidget(self.date_filter_check)

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setObjectName("FormField")
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setDate(QDate.currentDate().addDays(-14))
        self.start_date_edit.setEnabled(False)
        row2.addWidget(self.start_date_edit)

        self.end_date_edit = QDateEdit()
        self.end_date_edit.setObjectName("FormField")
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setEnabled(False)
        row2.addWidget(self.end_date_edit)

        row2.addStretch()

        self.btn_clear = QPushButton(tr("history.reset"))
        self.btn_clear.setObjectName("SecondaryButton")
        self.btn_clear.setFixedHeight(38)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        row2.addWidget(self.btn_clear)

        self.btn_export_cert = QPushButton(tr("history.export_cert"))
        self.btn_export_cert.setObjectName("PrimaryButton")
        self.btn_export_cert.setFixedHeight(38)
        self.btn_export_cert.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_cert.setVisible(export_inspection_record_pdf is not None)
        row2.addWidget(self.btn_export_cert)
        self.filter_card.body.addLayout(row2)

        self.notice_label = QLabel("")
        self.notice_label.setObjectName("HintLabel")
        self.filter_card.body.addWidget(self.notice_label)
        root.addWidget(self.filter_card)

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
        self.history_table = DataTable(self._table_headers())
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

        self.empty_label = QLabel(tr("history.empty"))
        self.empty_label.setObjectName("PageSubtitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detail_layout.addWidget(self.empty_label)

        self.detail_widget = RecordDetailWidget()
        detail_layout.addWidget(self.detail_widget)
        detail_layout.addStretch()

        detail_scroll.setWidget(detail_content)
        splitter.addWidget(detail_scroll)
        splitter.setSizes([590, 730])
        root.addWidget(splitter, 1)

        self.search_field.textChanged.connect(lambda _: self._apply_filters())
        self.product_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        self.status_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        self.outcome_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        self.view_mode_combo.currentIndexChanged.connect(lambda _: self._apply_filters())
        self.date_filter_check.toggled.connect(self._on_date_filter_toggled)
        self.start_date_edit.dateChanged.connect(lambda _: self._apply_filters())
        self.end_date_edit.dateChanged.connect(lambda _: self._apply_filters())
        self.btn_clear.clicked.connect(self._on_reset_filters)
        self.history_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_export_cert.clicked.connect(self._on_export_certificate_clicked)
        self.detail_widget.version_selected.connect(self._on_version_selected)
        self.detail_widget.note_added.connect(self._on_note_added)

    @staticmethod
    def _table_headers() -> list[str]:
        return [
            tr("history.col.ver"),
            tr("history.col.session"),
            tr("history.col.box"),
            tr("history.col.product"),
            tr("history.col.status"),
            tr("history.col.outcome"),
            tr("history.col.started"),
        ]

    def retranslate_ui(self, _lang: str = "") -> None:
        labels = self.header.findChildren(QLabel)
        if len(labels) >= 2:
            labels[0].setText(tr("history.title"))
            labels[1].setText(tr("history.subtitle"))
        title_lbl = self.filter_card.findChild(QLabel, "FormSectionTitle")
        if title_lbl is not None:
            title_lbl.setText(tr("history.filter_card").upper())
        self.search_field.setPlaceholderText(tr("history.search_placeholder"))
        self.date_filter_check.setText(tr("history.date_filter"))
        self.btn_clear.setText(tr("history.reset"))
        self.btn_export_cert.setText(tr("history.export_cert"))
        self.empty_label.setText(tr("history.empty"))
        self.view_mode_combo.setItemText(0, tr("history.view.all"))
        self.view_mode_combo.setItemText(1, tr("history.view.grouped"))
        self.status_combo.setItemText(0, tr("history.all_statuses"))
        self.outcome_combo.setItemText(0, tr("history.all_outcomes"))
        self.history_table.setHorizontalHeaderLabels(self._table_headers())
        self.refresh()

    def _on_date_filter_toggled(self, enabled: bool) -> None:
        self.start_date_edit.setEnabled(enabled)
        self.end_date_edit.setEnabled(enabled)
        self._apply_filters()

    def _populate_products(self) -> None:
        current = self.product_combo.currentData()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        self.product_combo.addItem(tr("history.all_products"), userData=None)
        for p in self._repo.products:
            self.product_combo.addItem(f"{p.name} ({p.code})", userData=p.code)
        idx = self.product_combo.findData(current)
        self.product_combo.setCurrentIndex(max(0, idx))
        self.product_combo.blockSignals(False)

    def refresh(self) -> None:
        self._populate_products()
        self._apply_filters()

    def _on_reset_filters(self) -> None:
        for widget in (
            self.search_field,
            self.product_combo,
            self.status_combo,
            self.outcome_combo,
            self.view_mode_combo,
            self.date_filter_check,
        ):
            widget.blockSignals(True)
        self.search_field.clear()
        self.product_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.outcome_combo.setCurrentIndex(0)
        self.view_mode_combo.setCurrentIndex(0)
        self.date_filter_check.setChecked(False)
        self.start_date_edit.setEnabled(False)
        self.end_date_edit.setEnabled(False)
        for widget in (
            self.search_field,
            self.product_combo,
            self.status_combo,
            self.outcome_combo,
            self.view_mode_combo,
            self.date_filter_check,
        ):
            widget.blockSignals(False)
        self._apply_filters()

    def _apply_filters(self) -> None:
        query = self.search_field.text().strip()
        prod_code = self.product_combo.currentData()
        status = self.status_combo.currentData()
        outcome = self.outcome_combo.currentData()
        start_d: Optional[date] = None
        end_d: Optional[date] = None
        if self.date_filter_check.isChecked():
            qs = self.start_date_edit.date()
            qe = self.end_date_edit.date()
            start_d = date(qs.year(), qs.month(), qs.day())
            end_d = date(qe.year(), qe.month(), qe.day())
            if end_d < start_d:
                start_d, end_d = end_d, start_d

        filtered = self._repo.filter_records(
            text=query,
            product_code=prod_code,
            status=status,
            start=start_d,
            end=end_d,
            outcome=outcome,
        )

        # Compute version numbers across matching box codes
        versions_by_box: dict[str, list[InspectionRecord]] = {}
        for rec in filtered:
            key = rec.session.box_code.text
            if key not in versions_by_box:
                versions_by_box[key] = self._repo.box_versions(rec.session.box_code)

        if self.view_mode_combo.currentData() == "grouped":
            latest_by_box: dict[str, InspectionRecord] = {}
            for rec in filtered:
                key = rec.session.box_code.text
                if key not in latest_by_box or rec.version > latest_by_box[key].version:
                    latest_by_box[key] = rec
            self._records = list(latest_by_box.values())
        else:
            self._records = filtered

        unique_boxes = len({r.session.box_code.text for r in self._records})
        self.count_label.setText(tr("history.count_found", n=len(self._records), boxes=unique_boxes))
        self.history_table.set_rows(
            [
                [
                    f"v{r.version}/{len(versions_by_box.get(r.session.box_code.text, [r]))}",
                    r.session_id,
                    r.session.box_code.text,
                    r.session.product.name,
                    fmt_status(r.status.value),
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
            versions = self._repo.box_versions(record.session.box_code)
            self.detail_widget.set_record(record, versions=versions)

    def _on_version_selected(self, target: InspectionRecord) -> None:
        for row, rec in enumerate(self._records):
            if rec.session_id == target.session_id:
                self.history_table.selectRow(row)
                return
        versions = self._repo.box_versions(target.session.box_code)
        self.detail_widget.set_record(target, versions=versions)

    def _on_note_added(self, session_id: str, text: str) -> None:
        author = self._current_user.username if self._current_user else "operator"
        role = self._current_user.role.value if self._current_user else "User"
        try:
            self._repo.add_attributed_note(session_id, author, role, text)
            self.notice_label.setText(f"✔  Attributed note saved by {author} ({role}).")
            # Refresh current detail view
            current = self.selected_record()
            if current is not None:
                updated_versions = self._repo.box_versions(current.session.box_code)
                updated_rec = next(
                    (r for r in updated_versions if r.session_id == session_id),
                    current,
                )
                self.detail_widget.set_record(updated_rec, versions=updated_versions)
        except ValueError as exc:
            self.notice_label.setText(f"⚠  {exc}")

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
