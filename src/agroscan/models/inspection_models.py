"""Domain models for the AgroScan inspection workflow.

Defines all shared dataclasses and enumerations used across UI, services,
and (future) AI integration layers. No UI or PySide6 dependency here.

Structure (D-019, D-022): an ``Order`` groups many boxes; each box carries
its own QR code ``AGS:<order_code>-<box_no>/<total>`` and is inspected in
one or more ``InspectionSession`` (re-inspection creates a new session, D-021).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from agroscan.models.vlm_models import VlmAnalysis


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SessionStatus(Enum):
    """Vòng đời của một phiên kiểm tra hộp (D-020)."""

    IN_PROGRESS    = "In Progress"
    PENDING_REVIEW = "Pending Review"
    COMPLETED      = "Completed"


class AiRecommendation(Enum):
    """Đề xuất do hệ thống (YOLO + rule engine) đưa ra — chưa phải kết luận."""

    PASS         = "Pass"
    FAIL         = "Fail"
    NEEDS_REVIEW = "Needs Review"


class ReviewerDecision(Enum):
    """Quyết định cuối cùng của reviewer (bước 7)."""

    PASS       = "Pass"
    FAIL       = "Fail"
    RE_INSPECT = "Re-inspect"


class BoxZone(Enum):
    """Bề mặt / góc chụp của hộp để đánh giá độ phủ toàn hộp (3.4.5.1)."""

    TOP    = "top"
    LEFT   = "left"
    RIGHT  = "right"
    BOTTOM = "bottom"
    INNER  = "inner"


#: 4 bề mặt bắt buộc để đạt 100% độ phủ toàn bộ hộp (INNER là góc bổ sung).
REQUIRED_COVERAGE_ZONES: tuple[BoxZone, ...] = (
    BoxZone.TOP,
    BoxZone.LEFT,
    BoxZone.RIGHT,
    BoxZone.BOTTOM,
)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass
class DefectCriterion:
    """Ngưỡng cho một loại lỗi của sản phẩm (D-023). Cấu hình, không hardcode."""

    defect_class: str          # Ví dụ: "bruised", "rotten"
    max_ratio:    float        # 0.0 – 1.0; vượt ngưỡng → đề xuất Fail
    is_critical:  bool = False # Có là đề xuất Fail ngay
    operator: str = "gt"


@dataclass
class Product:
    """Loại sản phẩm, gắn với model YOLO chuyên hóa riêng (D-024)."""

    code:           str
    name:           str
    category:       str
    model_file:     str                       # Ví dụ: "banana_defect.onnx"
    detect_classes: list[str]                 # Lớp YOLO model trả về
    criteria:       list[DefectCriterion] = field(default_factory=list)
    min_objects:    int   = 5                 # Ít hơn → Needs Review
    min_confidence: float = 0.60              # Thấp hơn → Needs Review


@dataclass
class Order:
    """Đơn hàng — chỉ là nhóm hộp, không có kết quả đạt/không đạt riêng (D-022)."""

    order_code:        str
    product:           Product
    supplier:          str
    total_boxes:       int
    expected_quantity: Optional[int]
    created_at:        datetime = field(default_factory=datetime.now)
    lot_id: Optional[int] = None
    lot_code: Optional[str] = None
    lot_outcome: Optional[str] = None
    decision_version: Optional[int] = None
    sampling_recommendation: Optional[str] = None
    override_reason: Optional[str] = None
    signed_attempts: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Box code (D-019)
# ---------------------------------------------------------------------------


_BOX_CODE_PATTERN = re.compile(
    r"^AGS:(?P<order>[A-Z0-9][A-Z0-9_:-]*)-(?P<box>\d{1,4})/(?P<total>\d{1,4})$"
)


@dataclass(frozen=True)
class BoxCode:
    """Mã QR nội bộ của một hộp: ``AGS:<order_code>-<box_no>/<total>``."""

    order_code:  str
    box_number:  int
    total_boxes: int

    @classmethod
    def parse(cls, text: str) -> "BoxCode":
        """Phân tích chuỗi quét được thành BoxCode.

        Raises:
            ValueError: Nếu chuỗi sai định dạng hoặc số hộp không hợp lệ.
        """
        match = _BOX_CODE_PATTERN.match(text.strip().upper())
        if not match:
            raise ValueError(
                "Invalid box code format. Expected AGS:<ORDER>-<BOX>/<TOTAL>, "
                "e.g. AGS:DH00123-03/10."
            )
        box   = int(match.group("box"))
        total = int(match.group("total"))
        if total < 1 or not 1 <= box <= total:
            raise ValueError(f"Box number {box} is out of range 1–{total}.")
        return cls(match.group("order"), box, total)

    @property
    def text(self) -> str:
        """Chuỗi chuẩn hóa, dùng để in QR và hiển thị."""
        width = max(2, len(str(self.total_boxes)))
        return (
            f"AGS:{self.order_code}-"
            f"{self.box_number:0{width}d}/{self.total_boxes:0{width}d}"
        )

    def __str__(self) -> str:
        return self.text


# ---------------------------------------------------------------------------
# Inspection session
# ---------------------------------------------------------------------------


@dataclass
class InspectionSession:
    """Một lần kiểm tra của một hộp (bước 3 → 6)."""

    session_id: str
    box_code:   BoxCode
    order:      Order
    inspector:  str                 # username của inspector đang đăng nhập
    station:    str
    status:     SessionStatus = SessionStatus.IN_PROGRESS
    notes:      str = ""
    started_at: datetime = field(default_factory=datetime.now)

    @property
    def product(self) -> Product:
        return self.order.product


@dataclass(frozen=True)
class DetectedUnit:
    x: int
    y: int
    width: int
    height: int
    label: str
    confidence: float


@dataclass
class EvidenceImage:
    """Ảnh tĩnh làm bằng chứng gốc (D-026).

    ``sha256`` và ``relative_path`` để trống cho tới khi có tầng lưu trữ SMB.
    """

    captured_at:     datetime = field(default_factory=datetime.now)
    is_auto_capture: bool = False
    relative_path:   str = ""
    sha256:          str = ""
    width_px: int = 0
    height_px: int = 0
    source_kind: str = "camera"
    demo_image: bool = False
    model_file: str = ""
    units: list[DetectedUnit] = field(default_factory=list)
    zone: Optional[BoxZone] = None


@dataclass(frozen=True)
class BoxCoverageStatus:
    """Trạng thái độ phủ toàn bộ hộp (Whole-Box Coverage, 3.4.5.1)."""

    required_zones: tuple[BoxZone, ...]
    captured_zones: frozenset[BoxZone]
    total_images:   int

    @property
    def covered_required(self) -> int:
        return sum(1 for z in self.required_zones if z in self.captured_zones)

    @property
    def missing_zones(self) -> list[BoxZone]:
        return [z for z in self.required_zones if z not in self.captured_zones]

    @property
    def percentage(self) -> float:
        if not self.required_zones:
            return 100.0
        return round((self.covered_required / len(self.required_zones)) * 100.0, 1)

    @property
    def is_complete(self) -> bool:
        return len(self.missing_zones) == 0


def compute_box_coverage(
    evidence: list[EvidenceImage],
    required_zones: tuple[BoxZone, ...] = REQUIRED_COVERAGE_ZONES,
) -> BoxCoverageStatus:
    """Tính độ phủ bề mặt hộp từ danh sách ảnh bằng chứng đã chụp."""
    captured = frozenset(
        ev.zone if isinstance(ev.zone, BoxZone) else BoxZone(str(ev.zone).lower())
        for ev in evidence if ev.zone is not None
    )
    return BoxCoverageStatus(
        required_zones=required_zones,
        captured_zones=captured,
        total_images=len(evidence),
    )


@dataclass
class DetectionResult:
    """Kết quả YOLO tính trên ảnh tĩnh — nguồn số liệu chính thức (D-026).

    Trong giai đoạn UI shell, ``is_simulated`` luôn là ``True``.
    """

    total_objects:   int
    class_counts:    dict[str, int]   # Ví dụ: {"fresh": 21, "bruised": 3}
    mean_confidence: float            # 0.0 – 1.0
    is_simulated:    bool = True
    defect_classification_available: bool = True

    def ratio(self, defect_class: str) -> float:
        """Tỷ lệ của một lớp trên tổng số quả phát hiện được."""
        if self.total_objects == 0:
            return 0.0
        return self.class_counts.get(defect_class, 0) / self.total_objects


@dataclass
class QualityAssessmentResult:
    """Kết quả đánh giá của Python rule engine (D-023, bước 6)."""

    recommendation: AiRecommendation
    reasons:        list[str]
    defect_ratios:  dict[str, float]
    is_simulated:   bool = True


@dataclass
class ReviewRecord:
    """Xác nhận của reviewer (bước 7)."""

    decision:    ReviewerDecision
    reviewer:    str
    notes:       str = ""
    reviewed_at: datetime = field(default_factory=datetime.now)


@dataclass
class AttributedNote:
    """Ghi chú định danh gắn tác giả, vai trò và dấu thời gian (3.4.5.9)."""

    author:     str
    role:       str
    text:       str
    created_at: datetime = field(default_factory=datetime.now)
    note_id:    str = ""


@dataclass
class AuditEvent:
    """Một mốc sự kiện trong Audit Trail của phiên kiểm định (3.4.5.9)."""

    action:    str
    actor:     str
    role:      str
    timestamp: datetime = field(default_factory=datetime.now)
    details:   str = ""


@dataclass
class InspectionRecord:
    """Toàn bộ kết quả của một phiên, từ lúc gửi duyệt đến khi reviewer xác nhận."""

    session:          InspectionSession
    evidence:         list[EvidenceImage]
    detection:        DetectionResult
    assessment:       QualityAssessmentResult
    deep_analysis:    Optional[VlmAnalysis] = None   # Kết quả Qwen-VL schema 1.0 (nếu có)
    review:           Optional[ReviewRecord] = None
    attributed_notes: list[AttributedNote] = field(default_factory=list)
    audit_trail:      list[AuditEvent] = field(default_factory=list)
    version:          int = 1
    whole_box_confirmed: bool = False

    @property
    def session_id(self) -> str:
        return self.session.session_id

    @property
    def status(self) -> SessionStatus:
        return self.session.status

    @property
    def coverage(self) -> BoxCoverageStatus:
        return compute_box_coverage(self.evidence)


@dataclass
class OrderSummary:
    """Tổng hợp cấp đơn hàng từ kết quả từng hộp (D-022, 3.4.5.2)."""

    order:      Order
    passed:     int = 0
    failed:     int = 0
    pending:    int = 0   # Pending Review hoặc Re-inspect
    remaining:  int = 0   # Chưa kiểm tra
    reinspect:  int = 0   # Số hộp được yêu cầu kiểm tra lại (tách riêng cho Dashboard)

    required_boxes: Optional[int] = None

    @property
    def sample_size(self) -> int:
        return self.order.total_boxes if self.required_boxes is None else self.required_boxes

    @property
    def completion_rate(self) -> float:
        if self.sample_size <= 0:
            return 0.0
        return round(((self.passed + self.failed) / self.sample_size) * 100.0, 1)

    @property
    def text(self) -> str:
        """Ví dụ: "8/10 boxes passed, 1 pending, 1 failed"."""
        return (
            f"{self.passed}/{self.order.total_boxes} boxes passed, "
            f"{self.pending} pending, {self.failed} failed"
        )
