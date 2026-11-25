"""Read-only + interactive detail view of one inspection record (3.4.4.2, 3.4.5.9).

Shared by AssessmentResultPage, ReviewQueuePage, and InspectionHistoryPage.
Includes:
  - Session metadata & version badge
  - Box Version History table (v1, v2, ...) with version-to-version diff banner
  - AI Recommendation, Detection Table, Qwen-VL Panel, Evidence Strip, Reviewer Decision
  - Audit Detail (chronological event timeline)
  - Attributed Notes (multi-entry author/role/timestamp list + inline add note)
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import InspectionRecord
from agroscan.models.user_models import Role
from agroscan.services.i18n import language_manager, tr
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.evidence_strip import EvidenceStrip
from agroscan.ui.components.page_layout import KeyValueGrid, SectionCard, make_hint
from agroscan.ui.components.status_badge import StatusBadge
from agroscan.ui.components.vlm_result_panel import VlmResultPanel
from agroscan.ui.formatting import defect_summary, final_result_text, fmt_datetime, fmt_percent, fmt_status



class RecordDetailWidget(QWidget):
    """Comprehensive inspection detail view with Versioned History, Audit Trail & Attributed Notes."""

    version_selected = Signal(object)      # InspectionRecord when user clicks another version
    note_added       = Signal(str, str)    # (session_id, note_text)

    def __init__(self, parent: Optional[QWidget] = None, *, role: Optional[Role] = None) -> None:
        super().__init__(parent)
        self._record: Optional[InspectionRecord] = None
        self._versions: list[InspectionRecord] = []
        self._images: Optional[list[QImage]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # 1. Session
        self.session_card = SectionCard(tr("detail.session"))
        self.session_grid = KeyValueGrid(columns=3)
        self.session_card.body.addWidget(self.session_grid)
        layout.addWidget(self.session_card)

        # 2. Box Version History (3.4.4.2)
        self.versions_card = SectionCard(tr("detail.versions"))
        self.version_diff_label = QLabel("")
        self.version_diff_label.setObjectName("VersionDiffBanner")
        self.version_diff_label.setWordWrap(True)
        self.version_diff_label.setVisible(False)
        self.versions_card.body.addWidget(self.version_diff_label)
        self.version_table = DataTable(["Ver", "Session ID", "Started", "AI Rec.", "Outcome", "Defects"])
        self.version_table.setMinimumHeight(130)
        self.version_table.cellClicked.connect(self._on_version_clicked)
        self.versions_card.body.addWidget(self.version_table)
        self.versions_card.setVisible(False)
        layout.addWidget(self.versions_card)

        # 3. Recommendation
        self.rec_card = SectionCard(tr("detail.ai_rec"))
        rec_row = QHBoxLayout()
        self.recommendation_badge = StatusBadge()
        rec_row.addWidget(self.recommendation_badge)
        self.simulated_label = QLabel("SIMULATED")
        self.simulated_label.setObjectName("MockBadge")
        rec_row.addWidget(self.simulated_label)
        rec_row.addStretch()
        self.rec_card.body.addLayout(rec_row)
        self.reasons_label = QLabel("")
        self.reasons_label.setObjectName("ValueLabel")
        self.reasons_label.setWordWrap(True)
        self.rec_card.body.addWidget(self.reasons_label)
        self.rec_card.body.addWidget(make_hint(
            "This is a system suggestion. The reviewer makes the final decision."
        ))
        layout.addWidget(self.rec_card)

        # 4. Detection
        self.det_card = SectionCard(tr("detail.detection"))
        self.detection_summary = QLabel("")
        self.detection_summary.setObjectName("ValueLabel")
        self.det_card.body.addWidget(self.detection_summary)
        self.detection_table = DataTable(["Class", "Count", "Ratio", "Limit", "Critical"])
        self.detection_table.setMinimumHeight(160)
        self.det_card.body.addWidget(self.detection_table)
        layout.addWidget(self.det_card)

        # 5. Deep analysis
        self.deep_card = SectionCard(tr("detail.deep_analysis"))
        self.vlm_panel = VlmResultPanel()
        self.deep_card.body.addWidget(self.vlm_panel)
        layout.addWidget(self.deep_card)

        # 6. Evidence
        self.evidence_card = SectionCard(tr("detail.evidence"))
        self.evidence_strip = EvidenceStrip()
        self.evidence_card.body.addWidget(self.evidence_strip)
        layout.addWidget(self.evidence_card)

        # 7. Review
        self.review_card = SectionCard(tr("detail.review"))
        review_row = QHBoxLayout()
        self.review_badge = StatusBadge()
        review_row.addWidget(self.review_badge)
        review_row.addStretch()
        self.review_card.body.addLayout(review_row)
        self.review_label = QLabel("")
        self.review_label.setObjectName("ValueLabel")
        self.review_label.setWordWrap(True)
        self.review_card.body.addWidget(self.review_label)
        layout.addWidget(self.review_card)

        # 8. Audit Detail / Chronological Timeline (3.4.5.9)
        self.audit_card = SectionCard(tr("detail.audit"))
        self.audit_filter = QLineEdit()
        self.audit_filter.setPlaceholderText(tr("detail.audit_filter"))
        self.audit_filter.textChanged.connect(self._filter_audit)
        self.audit_card.body.addWidget(self.audit_filter)
        self.audit_table = DataTable(["Timestamp", "Action", "Actor", "Role", "Details"])
        self.audit_table.setMinimumHeight(160)
        self.audit_card.body.addWidget(self.audit_table)
        layout.addWidget(self.audit_card)

        # 9. Attributed Notes (3.4.5.9)
        self.notes_card = SectionCard(tr("detail.notes"))
        self._notes_container = QVBoxLayout()
        self._notes_container.setSpacing(8)
        self.notes_card.body.addLayout(self._notes_container)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.note_input = QLineEdit()
        self.note_input.setObjectName("FormField")
        self.note_input.setPlaceholderText(tr("detail.notes_placeholder"))
        self.btn_add_note = QPushButton(tr("detail.notes_add"))
        self.btn_add_note.setObjectName("SecondaryButton")
        self.btn_add_note.setFixedHeight(38)
        self.btn_add_note.setCursor(Qt.CursorShape.PointingHandCursor)
        add_row.addWidget(self.note_input, 1)
        add_row.addWidget(self.btn_add_note)
        self.notes_card.body.addLayout(add_row)
        layout.addWidget(self.notes_card)
        self.audit_card.setVisible(role in (Role.ADMIN, Role.REVIEWER))
        self.notes_card.setVisible(role in (Role.ADMIN, Role.REVIEWER))
        self.note_input.setVisible(role is Role.REVIEWER)
        self.btn_add_note.setVisible(role is Role.REVIEWER)

        self.btn_add_note.clicked.connect(self._on_add_note)
        self.note_input.returnPressed.connect(self._on_add_note)
        language_manager().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self, _lang: str = "") -> None:
        mapping = (
            (self.session_card, "detail.session"),
            (self.versions_card, "detail.versions"),
            (self.rec_card, "detail.ai_rec"),
            (self.det_card, "detail.detection"),
            (self.deep_card, "detail.deep_analysis"),
            (self.evidence_card, "detail.evidence"),
            (self.review_card, "detail.review"),
            (self.audit_card, "detail.audit"),
            (self.notes_card, "detail.notes"),
        )
        for card, key in mapping:
            lbl = card.findChild(QLabel, "FormSectionTitle")
            if lbl is not None:
                lbl.setText(tr(key).upper())
        self.audit_filter.setPlaceholderText(tr("detail.audit_filter"))
        self.note_input.setPlaceholderText(tr("detail.notes_placeholder"))
        self.btn_add_note.setText(tr("detail.notes_add"))
        if self._record is not None:
            self.set_record(self._record, self._images, self._versions)

    def set_record(
        self,
        record: InspectionRecord,
        images: Optional[list[QImage]] = None,
        versions: Optional[list[InspectionRecord]] = None,
    ) -> None:
        self._record = record
        self._images = images
        self._versions = list(versions) if versions is not None else [record]

        session = record.session
        cov = record.coverage
        ver_text = f"v{record.version} of {len(self._versions)}" if self._versions else f"v{record.version}"
        self.session_grid.set_items([
            ("Session",   session.session_id),
            ("Box",       f"{session.box_code.text}  ({ver_text})"),
            ("Status",    fmt_status(session.status.value)),
            ("Product",   session.product.name),
            ("Supplier",  session.order.supplier),
            ("Inspector", session.inspector),
            ("Station",   session.station),
            ("Started",   fmt_datetime(session.started_at)),
            ("Whole-box confirmation", "Recorded" if record.whole_box_confirmed else "Not recorded"),
            ("Tagged views", f"{cov.covered_required}/{len(cov.required_zones)}"),
            ("Lot", session.order.lot_code or session.order.order_code),
            ("Signed lot decision", f"v{session.order.decision_version} · {session.order.lot_outcome}"
             if session.order.lot_outcome else "None recorded"),
            ("Attempt in signed manifest", "Yes" if record.session_id in session.order.signed_attempts else "No"),
            ("Sampling recommendation", session.order.sampling_recommendation or "—"),
            ("Override reason", session.order.override_reason or "—"),
        ])

        # Box Version History & Diff (3.4.4.2)
        show_versions = len(self._versions) > 1
        self.versions_card.setVisible(show_versions)
        if show_versions:
            ordered = sorted(self._versions, key=lambda r: (r.version, r.session.started_at), reverse=True)
            self.version_table.set_rows(
                [
                    [
                        f"v{r.version}" + (" ★" if r.session_id == record.session_id else ""),
                        r.session_id,
                        fmt_datetime(r.session.started_at),
                        r.assessment.recommendation.value,
                        final_result_text(r),
                        defect_summary(r),
                    ]
                    for r in ordered
                ],
                ordered,
            )
            prev = next((r for r in self._versions if r.version == record.version - 1), None)
            if prev is not None:
                obj_delta = record.detection.total_objects - prev.detection.total_objects
                sign = "+" if obj_delta >= 0 else ""
                diff_str = (
                    f"Objects {prev.detection.total_objects}→{record.detection.total_objects} ({sign}{obj_delta}), "
                    f"Outcome {final_result_text(prev)}→{final_result_text(record)}"
                )
                self.version_diff_label.setText(
                    tr("detail.versions_diff", prev=f"v{prev.version}", curr=f"v{record.version}", diff=diff_str)
                )
                self.version_diff_label.setVisible(True)
            else:
                self.version_diff_label.setVisible(False)

        assessment = record.assessment
        self.recommendation_badge.set_value(assessment.recommendation)
        self.simulated_label.setVisible(assessment.is_simulated)
        self.reasons_label.setText("\n".join(f"•  {r}" for r in assessment.reasons))

        detection = record.detection
        self.detection_summary.setText(
            f"{detection.total_objects} objects  ·  mean confidence "
            f"{fmt_percent(detection.mean_confidence)}"
        )
        criteria = {c.defect_class: c for c in session.product.criteria}
        rows = []
        for cls, count in detection.class_counts.items():
            criterion = criteria.get(cls)
            rows.append([
                cls.capitalize(),
                str(count),
                fmt_percent(detection.ratio(cls)),
                fmt_percent(criterion.max_ratio) if criterion else "—",
                "Yes" if criterion and criterion.is_critical else "—",
            ])
        self.detection_table.set_rows(rows)

        self.deep_card.setVisible(record.deep_analysis is not None)
        if record.deep_analysis is not None:
            self.vlm_panel.set_analysis(record.deep_analysis, {
                "box_code": session.box_code.text,
                "supplier": session.order.supplier,
            })
        self.evidence_strip.set_evidence(record.evidence, images)

        self.review_card.setVisible(record.review is not None)
        if record.review:
            self.review_badge.set_value(record.review.decision)
            notes = f"\nNotes: {record.review.notes}" if record.review.notes else ""
            self.review_label.setText(
                f"By {record.review.reviewer} on {fmt_datetime(record.review.reviewed_at)}{notes}"
            )

        # Audit Trail Timeline (3.4.5.9)
        audit_events = sorted(record.audit_trail, key=lambda e: e.timestamp)
        self.audit_table.set_rows(
            [
                [
                    fmt_datetime(ev.timestamp),
                    ev.action,
                    ev.actor,
                    ev.role,
                    ev.details,
                ]
                for ev in audit_events
            ]
        )

        # Attributed Notes (3.4.5.9)
        self._filter_audit(self.audit_filter.text())
        self._render_notes(record)

    def _filter_audit(self, text: str) -> None:
        terms = text.casefold().split()
        for row in range(self.audit_table.rowCount()):
            event = " ".join(self.audit_table.item(row, col).text()
                             for col in range(self.audit_table.columnCount())).casefold()
            self.audit_table.setRowHidden(row, not all(term in event for term in terms))

    def _render_notes(self, record: InspectionRecord) -> None:
        while self._notes_container.count():
            item = self._notes_container.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        notes = list(record.attributed_notes)
        if not notes:
            empty = QLabel(tr("detail.notes_empty"))
            empty.setObjectName("HintLabel")
            self._notes_container.addWidget(empty)
            return

        for note in notes:
            card = QFrame()
            card.setObjectName("NoteItemCard")
            v = QVBoxLayout(card)
            v.setContentsMargins(12, 8, 12, 8)
            v.setSpacing(4)
            meta = QLabel(f"[{note.role.upper()}]  {note.author}   ·   {fmt_datetime(note.created_at)}")
            meta.setObjectName("NoteAuthorMeta")
            body = QLabel(note.text)
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setObjectName("NoteBodyText")
            body.setWordWrap(True)
            v.addWidget(meta)
            v.addWidget(body)
            self._notes_container.addWidget(card)

    def _on_version_clicked(self, row: int, _col: int) -> None:
        selected = self.version_table.payload_at(row)
        if isinstance(selected, InspectionRecord) and self._record is not None:
            if selected.session_id != self._record.session_id:
                self.version_selected.emit(selected)

    def _on_add_note(self) -> None:
        if self._record is None:
            return
        text = self.note_input.text().strip()
        if not text:
            return
        self.note_input.clear()
        self.note_added.emit(self._record.session_id, text)
