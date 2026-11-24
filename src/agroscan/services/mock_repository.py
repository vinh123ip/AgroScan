"""In-memory data store for the UI-shell phase.

Holds the mock catalog, orders, users and inspection history so every page
can render realistic data and the full workflow (intake → live inspection →
review → reports) works end to end without a database. All data is lost when
the application closes. Replace with the PostgreSQL data-access layer later.
"""

import copy
import random
from collections import defaultdict
from dataclasses import fields
from datetime import date, datetime, timedelta
from typing import Optional

from agroscan.models.inspection_models import (
    AiRecommendation,
    AttributedNote,
    AuditEvent,
    BoxCode,
    BoxZone,
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
from agroscan.services.catalog_validation import validate_product
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

    def categories(self) -> list[str]:
        """Danh mục hàng hóa (Goods Category) đang dùng, sắp xếp A–Z."""
        return sorted({p.category for p in self.products if p.category})

    def orders_for_product(self, code: str) -> list[Order]:
        return [o for o in self.orders.values() if o.product.code == code]

    def save_product(self, product: Product, original_code: Optional[str] = None) -> Product:
        """Thêm mới (``original_code=None``) hoặc cập nhật sản phẩm theo mã gốc.

        Cập nhật tại chỗ để các đơn hàng đang tham chiếu dùng ngay tiêu chí mới
        cho phiên kiểm tra kế tiếp. Mã sản phẩm không đổi được sau khi tạo.

        Raises:
            ValueError: Cấu hình không hợp lệ (thông điệp gồm mọi lỗi, mỗi lỗi một dòng).
        """
        if original_code is not None and product.code != original_code:
            raise ValueError("Product code cannot be changed after creation.")
        others = [p.code for p in self.products if p.code != original_code]
        errors = validate_product(product, others)
        if errors:
            raise ValueError("\n".join(errors))

        stored = copy.deepcopy(product)
        if original_code is None:
            self.products.append(stored)
            return stored
        target = self.find_product(original_code)
        if target is None:
            raise ValueError(f"Product {original_code} was not found.")
        for f in fields(Product):
            setattr(target, f.name, getattr(stored, f.name))
        return target

    def delete_product(self, code: str) -> None:
        """Xóa sản phẩm chưa có đơn hàng nào tham chiếu.

        Raises:
            ValueError: Không tìm thấy, hoặc còn đơn hàng dùng sản phẩm này.
        """
        product = self.find_product(code)
        if product is None:
            raise ValueError(f"Product {code} was not found.")
        orders = self.orders_for_product(code)
        if orders:
            raise ValueError(
                f"{product.name} is used by {len(orders)} order(s) "
                f"({', '.join(o.order_code for o in orders)}) and cannot be deleted."
            )
        self.products.remove(product)

    def save_order(self, order: Order) -> Order:
        """Insert or update an Order in the repository (T3.4)."""
        code = order.order_code.strip().upper()
        if not code:
            raise ValueError("Order code cannot be empty.")
        if order.total_boxes < 1:
            raise ValueError("Total boxes must be >= 1.")
        if order.expected_quantity < 1:
            raise ValueError("Expected quantity must be >= 1.")
        stored = Order(
            order_code=code,
            product=order.product,
            supplier=order.supplier.strip() or "Unknown Supplier",
            total_boxes=int(order.total_boxes),
            expected_quantity=int(order.expected_quantity),
            created_at=order.created_at,
        )
        self.orders[code] = stored
        return stored

    def import_orders(self, rows: list[dict[str, object]]) -> tuple[int, list[str]]:
        """Validate and import a batch of order dicts from CSV/Excel (T3.4)."""
        imported = 0
        errors: list[str] = []
        for idx, row in enumerate(rows, start=1):
            order_code = str(row.get("order_code") or "").strip().upper()
            product_code = str(row.get("product_code") or "").strip().upper()
            supplier = str(row.get("supplier") or "").strip()
            if not order_code or not product_code or not supplier:
                errors.append(f"Row {idx}: Missing order_code, product_code, or supplier.")
                continue
            product = self.find_product(product_code)
            if product is None:
                errors.append(f"Row {idx} ({order_code}): Product '{product_code}' does not exist.")
                continue
            try:
                total_boxes = int(str(row.get("total_boxes") or "0").strip())
                expected_qty = int(str(row.get("expected_quantity") or "0").strip())
                if total_boxes < 1 or expected_qty < 1:
                    raise ValueError("Boxes and quantity must be positive integers.")
            except ValueError as exc:
                errors.append(f"Row {idx} ({order_code}): {exc}")
                continue

            self.save_order(
                Order(
                    order_code=order_code,
                    product=product,
                    supplier=supplier,
                    total_boxes=total_boxes,
                    expected_quantity=expected_qty,
                )
            )
            imported += 1
        return imported, errors

    def save_user(
        self,
        username: str,
        display_name: str,
        role: Role,
        is_active: bool = True,
        password: Optional[str] = None,
    ) -> User:
        """Create or update a user account in the repository (T3.5)."""
        name = username.strip().lower()
        if not name:
            raise ValueError("Username cannot be empty.")
        if not display_name.strip():
            raise ValueError("Display name cannot be empty.")
        existing = next((u for u in self.users if u.username == name), None)
        if existing is None:
            new_user = User(name, display_name.strip(), role, is_active=is_active)
            self.users.append(new_user)
            return copy.deepcopy(new_user)
        existing.display_name = display_name.strip()
        existing.role = role
        existing.is_active = is_active
        return copy.deepcopy(existing)

    def record_export(self, fmt: str, file_path: str, filter_summary: str = "All") -> None:
        """Append an entry to export_history (T3.2)."""
        self.export_history.insert(0, (datetime.now(), fmt, file_path, filter_summary))

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
        return sorted(
            (r for r in self.records if r.session.box_code == box_code),
            key=lambda r: r.session.started_at,
        )

    def box_versions(self, box_code: BoxCode) -> list[InspectionRecord]:
        """Return chronological versioned inspection records (v1, v2, ...) for ``box_code``."""
        versions = self.records_for_box(box_code)
        for idx, rec in enumerate(versions, start=1):
            rec.version = idx
        return versions

    def _ensure_record_metadata(self, record: InspectionRecord) -> None:
        session = record.session
        if not record.audit_trail:
            record.audit_trail.append(
                AuditEvent(
                    action="Session Created",
                    actor=session.inspector,
                    role="Inspector",
                    timestamp=session.started_at,
                    details=f"Box {session.box_code.text} at {session.station}",
                )
            )
            if record.evidence:
                zones = ", ".join(sorted({ev.zone.value for ev in record.evidence}))
                record.audit_trail.append(
                    AuditEvent(
                        action="Evidence Captured",
                        actor=session.inspector,
                        role="Inspector",
                        timestamp=record.evidence[-1].captured_at,
                        details=f"{len(record.evidence)} image(s) [{zones}] · coverage {record.coverage.percentage:.0f}%",
                    )
                )
            if record.deep_analysis is not None:
                record.audit_trail.append(
                    AuditEvent(
                        action="Deep Analysis (Qwen-VL)",
                        actor=session.inspector,
                        role="Inspector",
                        timestamp=record.deep_analysis.analyzed_at,
                        details=f"Model {record.deep_analysis.model} ({record.deep_analysis.status.value})",
                    )
                )
            record.audit_trail.append(
                AuditEvent(
                    action="Submitted for Review",
                    actor=session.inspector,
                    role="Inspector",
                    timestamp=record.evidence[-1].captured_at if record.evidence else session.started_at,
                    details=f"AI recommendation: {record.assessment.recommendation.value}",
                )
            )
        if session.notes.strip() and not any(
            n.text == session.notes.strip() and n.author == session.inspector
            for n in record.attributed_notes
        ):
            record.attributed_notes.append(
                AttributedNote(
                    author=session.inspector,
                    role="Inspector",
                    text=session.notes.strip(),
                    created_at=session.started_at,
                    note_id=f"note-{session.session_id}-init",
                )
            )

    def submit_for_review(self, record: InspectionRecord) -> None:
        """Lưu kết quả AI, phiên chuyển sang Pending Review (D-020)."""
        record.session.status = SessionStatus.PENDING_REVIEW
        prior = self.records_for_box(record.session.box_code)
        if record not in prior:
            record.version = len(prior) + 1
            self._ensure_record_metadata(record)
            self.records.append(record)
        else:
            self._ensure_record_metadata(record)

    def apply_review(self, record: InspectionRecord, review: ReviewRecord) -> None:
        record.review = review
        record.session.status = SessionStatus.COMPLETED
        record.audit_trail.append(
            AuditEvent(
                action=f"Reviewer Decision: {review.decision.value}",
                actor=review.reviewer,
                role="Reviewer",
                timestamp=review.reviewed_at,
                details=review.notes or f"Marked as {review.decision.value}",
            )
        )
        if review.notes.strip():
            record.attributed_notes.append(
                AttributedNote(
                    author=review.reviewer,
                    role="Reviewer",
                    text=review.notes.strip(),
                    created_at=review.reviewed_at,
                    note_id=f"note-{record.session_id}-rev-{len(record.attributed_notes) + 1}",
                )
            )

    def add_attributed_note(
        self,
        session_id: str,
        author: str,
        role: str,
        text: str,
        created_at: Optional[datetime] = None,
    ) -> AttributedNote:
        """Append an attributed note to an existing inspection record (3.4.5.9)."""
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Note text cannot be empty.")
        record = next((r for r in self.records if r.session_id == session_id), None)
        if record is None:
            raise ValueError(f"Session '{session_id}' was not found.")
        ts = created_at or datetime.now()
        note = AttributedNote(
            author=author.strip() or "unknown",
            role=role.strip() or "User",
            text=cleaned,
            created_at=ts,
            note_id=f"note-{session_id}-{len(record.attributed_notes) + 1}",
        )
        record.attributed_notes.append(note)
        record.audit_trail.append(
            AuditEvent(
                action="Note Added",
                actor=note.author,
                role=note.role,
                timestamp=ts,
                details=cleaned[:120],
            )
        )
        return note

    def record_audit_event(
        self,
        session_id: str,
        action: str,
        actor: str,
        role: str,
        details: str = "",
        timestamp: Optional[datetime] = None,
    ) -> AuditEvent:
        """Append a chronological audit event to an existing session (3.4.5.9)."""
        record = next((r for r in self.records if r.session_id == session_id), None)
        if record is None:
            raise ValueError(f"Session '{session_id}' was not found.")
        event = AuditEvent(
            action=action,
            actor=actor,
            role=role,
            timestamp=timestamp or datetime.now(),
            details=details,
        )
        record.audit_trail.append(event)
        return event

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
                elif record.review is None:
                    summary.pending += 1
                elif record.review.decision == ReviewerDecision.RE_INSPECT:
                    summary.pending += 1
                    summary.reinspect += 1
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
        outcome: Optional[str] = None,
    ) -> list[InspectionRecord]:
        needle = text.strip().upper()
        outcome_filter = outcome.strip().lower() if outcome else None
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
            if outcome_filter:
                actual = (
                    record.review.decision.value.lower()
                    if record.review is not None
                    else record.assessment.recommendation.value.lower()
                )
                if actual != outcome_filter:
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
        deep_analysis = (
            mock_ai.simulate_deep_analysis(session, detection, rng=self._rng)
            if assessment.recommendation != AiRecommendation.PASS or not review
            else None
        )
        record = InspectionRecord(
            session,
            [EvidenceImage(started + timedelta(minutes=2))],
            detection,
            assessment,
            deep_analysis=deep_analysis,
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
