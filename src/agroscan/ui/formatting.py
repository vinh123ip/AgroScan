"""Display formatting shared by pages (Bilingual EN/VI aware, 3.4.5.2)."""

from datetime import datetime
from typing import Optional

from agroscan.models.inspection_models import BoxZone, InspectionRecord
from agroscan.services.i18n import get_language, tr, translate_enum_value


def fmt_datetime(value: Optional[datetime]) -> str:
    return value.strftime("%d %b %Y  %H:%M") if value else "—"


def fmt_percent(value: float) -> str:
    return f"{value:.0%}"


def fmt_zone(zone: BoxZone, short: bool = False) -> str:
    key = f"zone.short.{zone.value}" if short else f"zone.{zone.value}"
    return tr(key)


def fmt_status(status_value: str) -> str:
    return translate_enum_value("status", status_value)


def final_result_text(record: InspectionRecord) -> str:
    """Kết quả hiển thị theo ngôn ngữ hiện tại: quyết định reviewer nếu có, không thì đề xuất AI."""
    if record.review:
        return translate_enum_value("decision", record.review.decision.value)
    rec = translate_enum_value("rec", record.assessment.recommendation.value)
    prefix = "AI" if get_language() == "en" else "AI"
    return f"{prefix}: {rec}"


def defect_summary(record: InspectionRecord) -> str:
    counts = record.detection.class_counts
    return "  ·  ".join(f"{cls} {n}" for cls, n in counts.items())
