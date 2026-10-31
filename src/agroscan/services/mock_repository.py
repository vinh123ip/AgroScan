"""In-memory data store for the UI-shell phase.

Holds the mock catalog, orders, users and inspection history so every page
can render realistic data and the full workflow (intake → live inspection →
review → reports) works end to end without a database. All data is lost when
the application closes. Replace with the PostgreSQL data-access layer later.
"""

import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from agroscan.models.inspection_models import (
    AiRecommendation,
    BoxCode,
    DefectCriterion,
    EvidenceImage,
    InspectionRecord,
    InspectionSession,
    Order,
    OrderSummary,
    Product,
    ReviewerDecision,
    ReviewRecord,
    SessionStatus,
)
from agroscan.models.user_models import Role, User
from agroscan.services import mock_ai
from agroscan.services.mock_auth import MockAuthService


def _default_products() -> list[Product]:
    classes = ["fresh", "bruised", "rotten"]
    return [
        Product(
            "BANANA", "Banana", "Fruit", "banana_defect.onnx", classes,
            [DefectCriterion("bruised", 0.10), DefectCriterion("rotten", 0.0, is_critical=True)],
        ),
        Product(
            "APPLE", "Apple", "Fruit", "apple_defect.onnx", classes,
            [DefectCriterion("bruised", 0.08), DefectCriterion("rotten", 0.0, is_critical=True)],
        ),
        Product(
            "MANGO", "Mango", "Fruit", "mango_defect.onnx", classes,
            [DefectCriterion("bruised", 0.12), DefectCriterion("rotten", 0.0, is_critical=True)],
        ),
    ]


class MockRepository:
    """Kho dữ liệu trong RAM, mô phỏng tầng truy cập dữ liệu."""

    def __init__(self, seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self._session_counter = 0

        self.products: list[Product] = _default_products()
        self.users: list[User] = MockAuthService.default_users() + [
            User("inspector2", "Night Shift Inspector", Role.INSPECTOR, is_active=False),
        ]
        self.orders: dict[str, Order] = {}
        self.records: list[InspectionRecord] = []
        self.export_history: list[tuple[datetime, str, str, str]] = []

        self._seed_orders()
        self._seed_history()

    # ------------------------------------------------------------------
    # Catalog & orders
    # ------------------------------------------------------------------

    def find_product(self, code: str) -> Optional[Product]:
        return next((p for p in self.products if p.code == code), None)

    def resolve_box(self, text: str) -> tuple[BoxCode, Order]:
        """Xác thực mã hộp quét được với danh sách đơn hàng.

        Raises:
            ValueError: Sai định dạng, không có đơn, hoặc tổng số hộp không khớp.
        """
        box_code = BoxCode.parse(text)
        order = self.orders.get(box_code.order_code)
        if order is None:
            raise ValueError(f"Order {box_code.order_code} was not found.")
        if order.total_boxes != box_code.total_boxes:
            raise ValueError(
                f"Box code says {box_code.total_boxes} boxes but order "
                f"{order.order_code} has {order.total_boxes}."
            )
        return box_code, order

    # ------------------------------------------------------------------
    # Sessions & records
    # ------------------------------------------------------------------

    def create_session(
        self, box_code: BoxCode, order: Order, inspector: str, station: str
    ) -> InspectionSession:
        self._session_counter += 1
        session_id = f"INS-{datetime.now():%Y%m%d}-{self._session_counter:04d}"
        return InspectionSession(session_id, box_code, order, inspector, station)

    def records_for_box(self, box_code: BoxCode) -> list[InspectionRecord]:
        return [r for r in self.records if r.session.box_code == box_code]

    def submit_for_review(self, record: InspectionRecord) -> None:
        """Lưu kết quả AI, phiên chuyển sang Pending Review (D-020)."""
        record.session.status = SessionStatus.PENDING_REVIEW
        self.records.append(record)

    def apply_review(self, record: InspectionRecord, review: ReviewRecord) -> None:
        record.review = review
        record.session.status = SessionStatus.COMPLETED

    def pending_records(self) -> list[InspectionRecord]:
        pending = [r for r in self.records if r.status == SessionStatus.PENDING_REVIEW]
        return sorted(pending, key=lambda r: r.session.started_at)

    def all_records(self) -> list[InspectionRecord]:
        return sorted(self.records, key=lambda r: r.session.started_at, reverse=True)

    # ------------------------------------------------------------------
    # Aggregates (D-022)
    # ------------------------------------------------------------------

    def order_summaries(self, product_code: Optional[str] = None) -> list[OrderSummary]:
        latest: dict[BoxCode, InspectionRecord] = {}
        for record in sorted(self.records, key=lambda r: r.session.started_at):
            latest[record.session.box_code] = record

        summaries: list[OrderSummary] = []
        for order in self.orders.values():
            if product_code and order.product.code != product_code:
                continue
            summary = OrderSummary(order)
            for box_no in range(1, order.total_boxes + 1):
                record = latest.get(BoxCode(order.order_code, box_no, order.total_boxes))
                if record is None:
                    summary.remaining += 1
                elif record.review is None or record.review.decision == ReviewerDecision.RE_INSPECT:
                    summary.pending += 1
                elif record.review.decision == ReviewerDecision.PASS:
                    summary.passed += 1
                else:
                    summary.failed += 1
            summaries.append(summary)
        return summaries

    def daily_outcomes(
        self, start: date, end: date, product_code: Optional[str] = None
    ) -> list[tuple[date, int, int, int]]:
        """(ngày, passed, failed, pending) theo ngày bắt đầu phiên."""
        buckets: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0])
        for record in self.filter_records(start=start, end=end, product_code=product_code):
            bucket = buckets[record.session.started_at.date()]
            if record.review is None or record.review.decision == ReviewerDecision.RE_INSPECT:
                bucket[2] += 1
            elif record.review.decision == ReviewerDecision.PASS:
                bucket[0] += 1
            else:
                bucket[1] += 1
        days = (end - start).days + 1
        return [
            (day, *buckets[day])
            for day in (start + timedelta(n) for n in range(max(days, 0)))
        ]

    def filter_records(
        self,
        text: str = "",
        product_code: Optional[str] = None,
        status: Optional[SessionStatus] = None,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> list[InspectionRecord]:
        needle = text.strip().upper()
        result = []
        for record in self.all_records():
            session = record.session
            day = session.started_at.date()
            if needle and needle not in session.box_code.text and needle not in session.session_id:
                continue
            if product_code and session.product.code != product_code:
                continue
            if status and session.status != status:
                continue
            if start and day < start:
                continue
            if end and day > end:
                continue
            result.append(record)
        return result

    # ------------------------------------------------------------------
    # Seed data
    # ------------------------------------------------------------------

    def _seed_orders(self) -> None:
        now = datetime.now()
        banana, apple, mango = self.products
        for code, product, supplier, boxes, qty, days_ago in [
            ("DH00121", banana, "Green Valley Farm",    10, 240, 6),
            ("DH00122", apple,  "Da Lat Orchard Co.",    6, 150, 4),
            ("DH00123", banana, "Mekong Fresh Supply",  10, 250, 1),
            ("DH00124", mango,  "Cam Ranh Mango Coop",   8, 180, 0),
        ]:
            self.orders[code] = Order(code, product, supplier, boxes, qty, now - timedelta(days=days_ago))

    def _seed_history(self) -> None:
        """Sinh lịch sử kiểm tra demo nhất quán với kết quả rule engine giả lập."""
        plan = [("DH00121", 10, 6), ("DH00122", 6, 4), ("DH00123", 6, 1)]
        for order_code, inspected, days_ago in plan:
            order = self.orders[order_code]
            for box_no in range(1, inspected + 1):
                started = (datetime.now() - timedelta(days=days_ago)).replace(
                    hour=8 + box_no // 2, minute=self._rng.randint(0, 59)
                )
                is_pending = order_code == "DH00123" and box_no > 3
                self._seed_record(order, box_no, started, review=not is_pending)

    def _seed_record(self, order: Order, box_no: int, started: datetime, review: bool) -> None:
        box_code = BoxCode(order.order_code, box_no, order.total_boxes)
        session = self.create_session(box_code, order, "inspector", "STATION-01")
        session.session_id = f"INS-{started:%Y%m%d}-{self._session_counter:04d}"
        session.started_at = started

        detection = mock_ai.simulate_detection(order.product, self._rng)
        assessment = mock_ai.assess_quality(order.product, detection)
        record = InspectionRecord(
            session, [EvidenceImage(started + timedelta(minutes=2))], detection, assessment
        )
        self.submit_for_review(record)
        if review:
            decision = {
                AiRecommendation.PASS: ReviewerDecision.PASS,
                AiRecommendation.FAIL: ReviewerDecision.FAIL,
            }.get(assessment.recommendation) or self._rng.choice(
                [ReviewerDecision.PASS, ReviewerDecision.RE_INSPECT]
            )
            self.apply_review(
                record, ReviewRecord(decision, "reviewer", reviewed_at=started + timedelta(minutes=30))
            )
