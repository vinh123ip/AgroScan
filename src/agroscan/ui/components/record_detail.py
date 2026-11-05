"""Read-only view of one inspection record, shared by result/review/history pages."""

from typing import Optional

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from agroscan.models.inspection_models import InspectionRecord
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.evidence_strip import EvidenceStrip
from agroscan.ui.components.page_layout import KeyValueGrid, SectionCard, make_hint
from agroscan.ui.components.status_badge import StatusBadge
from agroscan.ui.components.vlm_result_panel import VlmResultPanel
from agroscan.ui.formatting import fmt_datetime, fmt_percent


class RecordDetailWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)

        # Session
        session_card = SectionCard("Session")
        self.session_grid = KeyValueGrid(columns=3)
        session_card.body.addWidget(self.session_grid)
        layout.addWidget(session_card)

        # Recommendation
        rec_card = SectionCard("AI Recommendation")
        rec_row = QHBoxLayout()
        self.recommendation_badge = StatusBadge()
        rec_row.addWidget(self.recommendation_badge)
        self.simulated_label = QLabel("SIMULATED")
        self.simulated_label.setObjectName("MockBadge")
        rec_row.addWidget(self.simulated_label)
        rec_row.addStretch()
        rec_card.body.addLayout(rec_row)
        self.reasons_label = QLabel("")
        self.reasons_label.setObjectName("ValueLabel")
        self.reasons_label.setWordWrap(True)
        rec_card.body.addWidget(self.reasons_label)
        rec_card.body.addWidget(make_hint(
            "This is a system suggestion. The reviewer makes the final decision."
        ))
        layout.addWidget(rec_card)

        # Detection
        det_card = SectionCard("Detection on Evidence Image")
        self.detection_summary = QLabel("")
        self.detection_summary.setObjectName("ValueLabel")
        det_card.body.addWidget(self.detection_summary)
        self.detection_table = DataTable(["Class", "Count", "Ratio", "Limit", "Critical"])
        self.detection_table.setMinimumHeight(170)
        det_card.body.addWidget(self.detection_table)
        layout.addWidget(det_card)

        # Deep analysis
        self.deep_card = SectionCard("Deep Analysis (Qwen-VL)")
        self.vlm_panel = VlmResultPanel()
        self.deep_card.body.addWidget(self.vlm_panel)
        layout.addWidget(self.deep_card)

        # Evidence
        evidence_card = SectionCard("Evidence Images")
        self.evidence_strip = EvidenceStrip()
        evidence_card.body.addWidget(self.evidence_strip)
        layout.addWidget(evidence_card)

        # Review
        self.review_card = SectionCard("Reviewer Decision")
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

    def set_record(
        self, record: InspectionRecord, images: Optional[list[QImage]] = None
    ) -> None:
        session = record.session
        self.session_grid.set_items([
            ("Session",   session.session_id),
            ("Box",       session.box_code.text),
            ("Status",    session.status.value),
            ("Product",   session.product.name),
            ("Supplier",  session.order.supplier),
            ("Inspector", session.inspector),
            ("Station",   session.station),
            ("Started",   fmt_datetime(session.started_at)),
            ("Notes",     session.notes),
        ])

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
