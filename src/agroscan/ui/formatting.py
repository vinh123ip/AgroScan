"""Display formatting shared by pages (English UI, D-013)."""

from datetime import datetime
from typing import Optional

from agroscan.models.inspection_models import InspectionRecord


def fmt_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d %b %Y  %H:%M") if value else "—"


def fmt_percent(value: float) -> str:
    return f"{value:.0%}"


def final_result_text(record: InspectionRecord) -> str:
    """Kết quả hiển thị: quyết định reviewer nếu có, không thì đề xuất AI."""
    if record.review:
        return record.review.decision.value
    return f"AI: {record.assessment.recommendation.value}"


def defect_summary(record: InspectionRecord) -> str:
    counts = record.detection.class_counts
    return "  ·  ".join(f"{cls} {n}" for cls, n in counts.items())
