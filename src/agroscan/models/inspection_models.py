"""Domain models for the AgroScan inspection workflow.

Defines all shared dataclasses and enumerations used across UI, services,
and (future) AI integration layers. No UI or PySide6 dependency here.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CommodityType(Enum):
    """Phân loại hàng hóa được kiểm định."""

    AGRICULTURAL = "Agricultural Goods"
    AQUATIC      = "Aquatic Goods"


class InspectionDecision(Enum):
    """Quyết định cuối cùng của Inspector sau khi xem xét kết quả AI."""

    APPROVED         = "APPROVED"
    CONDITIONAL_PASS = "CONDITIONAL PASS"
    REJECTED         = "REJECTED"
    PENDING          = "PENDING"   # Trạng thái mặc định, chưa xác nhận


# ---------------------------------------------------------------------------
# Core dataclasses
# ---------------------------------------------------------------------------


@dataclass
class InspectionSession:
    """Thông tin phiên kiểm định được tạo ở M2.1 (New Inspection).

    Được truyền xuyên suốt toàn bộ workflow M2.1 → M2.5.
    """

    session_id:     str
    batch_number:   str
    commodity_type: CommodityType
    origin_country: str
    inspector_name: str
    notes:          str
    created_at:     datetime = field(default_factory=datetime.now)


@dataclass
class DetectionResult:
    """Kết quả phát hiện và đếm vật thể từ M2.3 (Detection Demo).

    Trong giai đoạn demo, ``is_simulated`` luôn là ``True``.
    """

    total_objects:    int
    object_counts:    dict[str, int]   # Ví dụ: {"Banana": 24, "Damaged": 3}
    confidence_score: float            # Khoảng 0.0 – 1.0
    is_simulated:     bool = True


@dataclass
class QualityAssessmentResult:
    """Kết quả đánh giá chất lượng từ M2.4 (Quality Assessment Demo).

    Các tỷ lệ grade phải cộng lại bằng 1.0.
    Trong giai đoạn demo, ``is_simulated`` luôn là ``True``.
    """

    grade_a_ratio:      float   # Tốt     — 0.0 – 1.0
    grade_b_ratio:      float   # Đạt     — 0.0 – 1.0
    grade_c_ratio:      float   # Lỗi nhỏ — 0.0 – 1.0
    unclassified_ratio: float   # Chưa xếp loại
    overall_score:      float   # Tổng hợp 0 – 100
    recommendation:     str     # "PASS" | "FLAG FOR REVIEW" | "REJECT"
    is_simulated:       bool = True


@dataclass
class InspectionRecord:
    """Bản ghi hoàn chỉnh của một phiên kiểm định sau khi Inspector xác nhận.

    Được tạo ở M2.5 (Human Review) và lưu vào lịch sử ở M2.6.
    """

    session:          InspectionSession
    image_paths:      list[str]
    detection_result: DetectionResult
    quality_result:   QualityAssessmentResult
    decision:         InspectionDecision
    inspector_notes:  str
    finalized_at:     datetime = field(default_factory=datetime.now)

    @property
    def session_id(self) -> str:
        """Tiện truy cập Session ID trực tiếp từ record."""
        return self.session.session_id

    @property
    def batch_number(self) -> str:
        """Tiện truy cập Batch Number trực tiếp từ record."""
        return self.session.batch_number
