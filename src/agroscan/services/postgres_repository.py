"""PostgreSQL-backed repository replacing ``MockRepository`` (T1.2).

Implements the exact public interface and semantics of ``MockRepository`` so
all UI pages and workflows operate seamlessly against PostgreSQL without UI changes.
"""

from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import json
from typing import Iterator, Optional

from psycopg2.extensions import connection as PgConnection

from agroscan.models.inspection_models import (
    AiRecommendation,
    BoxCode,
    DefectCriterion,
    DetectionResult,
    EvidenceImage,
    InspectionRecord,
    InspectionSession,
    Order,
    OrderSummary,
    Product,
    QualityAssessmentResult,
    ReviewerDecision,
    ReviewRecord,
    SessionStatus,
)
from agroscan.models.user_models import Role, User
from agroscan.models.vlm_models import VlmAnalysis, VlmSchemaError, parse_vlm_response
from agroscan.services.app_settings import AppSettings, ConnectionSettings
from agroscan.services.catalog_validation import validate_product
from agroscan.services.database import (
    DbConfig,
    get_connection,
    resolve_db_config,
    test_connection,
)


def _to_local_naive(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert timezone-aware timestamps from PostgreSQL into local naive datetimes."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _parse_role(raw: str) -> Role:
    cleaned = raw.strip().upper()
    for role in Role:
        if role.name == cleaned or role.value.upper() == cleaned:
            return role
    raise ValueError(f"Unknown user role in database: {raw!r}")


def _parse_json_field(raw: object, default: object) -> object:
    if raw is None:
        return default
    if isinstance(raw, str):
        return json.loads(raw)
    return raw


class PostgresRepository:
    """PostgreSQL data-access layer matching ``MockRepository``'s interface."""

    def __init__(
        self,
        settings: Optional[AppSettings | ConnectionSettings | DbConfig] = None,
        db_config: Optional[DbConfig] = None,
    ) -> None:
        if db_config is not None:
            self._config = db_config
        elif isinstance(settings, DbConfig):
            self._config = settings
        else:
            self._config = resolve_db_config(settings)
        self._session_counter = 0

    @property
    def db_config(self) -> DbConfig:
        return self._config

    @contextmanager
    def _connection(self) -> Iterator[PgConnection]:
        conn = get_connection(self._config)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ping(self) -> tuple[bool, str]:
        """Check whether the PostgreSQL server and schema are reachable."""
        return test_connection(self._config)

    # ------------------------------------------------------------------
    # Properties matching MockRepository attributes
    # ------------------------------------------------------------------

    @property
    def products(self) -> list[Product]:
        with self._connection() as conn:
            return self._fetch_products(conn)

    @property
    def users(self) -> list[User]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT username, display_name, role, is_active
                    FROM users
                    ORDER BY username
                    """
                )
                return [
                    User(
                        username=row[0],
                        display_name=row[1],
                        role=_parse_role(row[2]),
                        is_active=bool(row[3]),
                    )
                    for row in cur.fetchall()
                ]

    @property
    def orders(self) -> dict[str, Order]:
        with self._connection() as conn:
            return self._fetch_orders(conn)

    @property
    def records(self) -> list[InspectionRecord]:
        with self._connection() as conn:
            return self._fetch_records(conn)

    @property
    def export_history(self) -> list[tuple[datetime, str, str, str]]:
        return []

    # ------------------------------------------------------------------
    # Internal loaders
    # ------------------------------------------------------------------

    def _fetch_products(self, conn: PgConnection) -> list[Product]:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT code, name, category, model_file, detect_classes, min_objects, min_confidence
                FROM products
                ORDER BY code
                """
            )
            product_rows = cur.fetchall()

            cur.execute(
                """
                SELECT product_code, defect_class, max_ratio, is_critical
                FROM product_criteria
                ORDER BY id
                """
            )
            criteria_by_code: dict[str, list[DefectCriterion]] = defaultdict(list)
            for prod_code, defect_cls, max_ratio, is_critical in cur.fetchall():
                criteria_by_code[prod_code].append(
                    DefectCriterion(
                        defect_class=defect_cls,
                        max_ratio=float(max_ratio),
                        is_critical=bool(is_critical),
                    )
                )

        products: list[Product] = []
        for code, name, category, model_file, detect_classes, min_objects, min_conf in product_rows:
            classes = list(_parse_json_field(detect_classes, []))
            products.append(
                Product(
                    code=code,
                    name=name,
                    category=category,
                    model_file=model_file,
                    detect_classes=[str(c) for c in classes],
                    criteria=criteria_by_code.get(code, []),
                    min_objects=int(min_objects),
                    min_confidence=float(min_conf),
                )
            )
        return products

    def _fetch_orders(self, conn: PgConnection) -> dict[str, Order]:
        products_by_code = {p.code: p for p in self._fetch_products(conn)}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT order_code, product_code, supplier, total_boxes, expected_quantity, created_at
                FROM orders
                ORDER BY created_at DESC, order_code
                """
            )
            orders: dict[str, Order] = {}
            for order_code, product_code, supplier, total_boxes, expected_qty, created_at in cur.fetchall():
                product = products_by_code.get(product_code)
                if product is None:
                    continue
                orders[order_code] = Order(
                    order_code=order_code,
                    product=product,
                    supplier=supplier,
                    total_boxes=int(total_boxes),
                    expected_quantity=int(expected_qty),
                    created_at=_to_local_naive(created_at) or datetime.now(),
                )
        return orders

    def _fetch_records(
        self, conn: PgConnection, box_code_filter: Optional[str] = None
    ) -> list[InspectionRecord]:
        orders_by_code = self._fetch_orders(conn)

        query = """
            SELECT
                s.session_id, s.box_code, s.order_code, s.box_number, s.total_boxes,
                s.inspector, s.station, s.status, s.notes, s.started_at,
                r.total_objects, r.class_counts, r.mean_confidence,
                r.recommendation, r.reasons, r.defect_ratios, r.deep_analysis,
                r.decision, r.reviewer, r.review_notes, r.reviewed_at
            FROM inspection_sessions s
            INNER JOIN inspection_results r ON r.session_id = s.session_id
        """
        params: tuple[object, ...] = ()
        if box_code_filter is not None:
            query += " WHERE s.box_code = %s"
            params = (box_code_filter,)
        query += " ORDER BY s.started_at DESC, s.session_id DESC"

        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            if not rows:
                return []

            session_ids = [row[0] for row in rows]
            cur.execute(
                """
                SELECT session_id, captured_at, is_auto_capture, relative_path, sha256
                FROM evidence_images
                WHERE session_id = ANY(%s)
                ORDER BY id
                """,
                (session_ids,),
            )
            evidence_by_session: dict[str, list[EvidenceImage]] = defaultdict(list)
            for sid, captured_at, is_auto, rel_path, sha256 in cur.fetchall():
                evidence_by_session[sid].append(
                    EvidenceImage(
                        captured_at=_to_local_naive(captured_at) or datetime.now(),
                        is_auto_capture=bool(is_auto),
                        relative_path=rel_path or "",
                        sha256=sha256 or "",
                    )
                )

        records: list[InspectionRecord] = []
        for row in rows:
            (
                session_id,
                _box_code_text,
                order_code,
                box_number,
                total_boxes,
                inspector,
                station,
                status_str,
                notes,
                started_at,
                total_objects,
                class_counts_raw,
                mean_conf,
                rec_str,
                reasons_raw,
                ratios_raw,
                deep_raw,
                decision_str,
                reviewer,
                review_notes,
                reviewed_at,
            ) = row

            order = orders_by_code.get(order_code)
            if order is None:
                continue

            box_code = BoxCode(order_code, int(box_number), int(total_boxes))
            session = InspectionSession(
                session_id=session_id,
                box_code=box_code,
                order=order,
                inspector=inspector,
                station=station,
                status=SessionStatus(status_str),
                notes=notes or "",
                started_at=_to_local_naive(started_at) or datetime.now(),
            )

            class_counts = {
                str(k): int(v)
                for k, v in dict(_parse_json_field(class_counts_raw, {})).items()
            }
            detection = DetectionResult(
                total_objects=int(total_objects),
                class_counts=class_counts,
                mean_confidence=float(mean_conf),
                is_simulated=False,
            )

            reasons = [str(item) for item in list(_parse_json_field(reasons_raw, []))]
            defect_ratios = {
                str(k): float(v)
                for k, v in dict(_parse_json_field(ratios_raw, {})).items()
            }
            assessment = QualityAssessmentResult(
                recommendation=AiRecommendation(rec_str),
                reasons=reasons,
                defect_ratios=defect_ratios,
                is_simulated=False,
            )

            deep_analysis: Optional[VlmAnalysis] = None
            if deep_raw is not None:
                parsed_deep = _parse_json_field(deep_raw, None)
                if isinstance(parsed_deep, dict):
                    try:
                        deep_analysis = parse_vlm_response(parsed_deep)
                    except VlmSchemaError:
                        deep_analysis = None

            review: Optional[ReviewRecord] = None
            if decision_str is not None:
                review = ReviewRecord(
                    decision=ReviewerDecision(decision_str),
                    reviewer=reviewer or "",
                    notes=review_notes or "",
                    reviewed_at=_to_local_naive(reviewed_at) or datetime.now(),
                )

            records.append(
                InspectionRecord(
                    session=session,
                    evidence=evidence_by_session.get(session_id, []),
                    detection=detection,
                    assessment=assessment,
                    deep_analysis=deep_analysis,
                    review=review,
                )
            )
        return records

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
        """Thêm mới (``original_code=None``) hoặc cập nhật sản phẩm theo mã gốc."""
        if original_code is not None and product.code != original_code:
            raise ValueError("Product code cannot be changed after creation.")

        current_products = self.products
        others = [p.code for p in current_products if p.code != original_code]
        errors = validate_product(product, others)
        if errors:
            raise ValueError("\n".join(errors))

        with self._connection() as conn:
            with conn.cursor() as cur:
                if original_code is None:
                    cur.execute(
                        """
                        INSERT INTO products (
                            code, name, category, model_file,
                            detect_classes, min_objects, min_confidence
                        )
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                        """,
                        (
                            product.code,
                            product.name,
                            product.category,
                            product.model_file,
                            json.dumps(product.detect_classes),
                            product.min_objects,
                            product.min_confidence,
                        ),
                    )
                else:
                    cur.execute("SELECT 1 FROM products WHERE code = %s", (original_code,))
                    if cur.fetchone() is None:
                        raise ValueError(f"Product {original_code} was not found.")
                    cur.execute(
                        """
                        UPDATE products
                        SET name = %s,
                            category = %s,
                            model_file = %s,
                            detect_classes = %s::jsonb,
                            min_objects = %s,
                            min_confidence = %s
                        WHERE code = %s
                        """,
                        (
                            product.name,
                            product.category,
                            product.model_file,
                            json.dumps(product.detect_classes),
                            product.min_objects,
                            product.min_confidence,
                            original_code,
                        ),
                    )
                    cur.execute(
                        "DELETE FROM product_criteria WHERE product_code = %s",
                        (original_code,),
                    )

                for criterion in product.criteria:
                    cur.execute(
                        """
                        INSERT INTO product_criteria (
                            product_code, defect_class, max_ratio, is_critical
                        )
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            product.code,
                            criterion.defect_class,
                            criterion.max_ratio,
                            criterion.is_critical,
                        ),
                    )

        saved = self.find_product(product.code)
        if saved is None:
            raise RuntimeError(f"Failed to reload saved product {product.code}.")
        return saved

    def delete_product(self, code: str) -> None:
        """Xóa sản phẩm chưa có đơn hàng nào tham chiếu."""
        product = self.find_product(code)
        if product is None:
            raise ValueError(f"Product {code} was not found.")
        orders = self.orders_for_product(code)
        if orders:
            raise ValueError(
                f"{product.name} is used by {len(orders)} order(s) "
                f"({', '.join(o.order_code for o in orders)}) and cannot be deleted."
            )
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM products WHERE code = %s", (code,))

    def resolve_box(self, text: str) -> tuple[BoxCode, Order]:
        """Xác thực mã hộp quét được với danh sách đơn hàng."""
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
        prefix = f"INS-{datetime.now():%Y%m%d}-"
        max_existing = 0
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_id FROM inspection_sessions WHERE session_id LIKE %s",
                    (f"{prefix}%",),
                )
                for (sid,) in cur.fetchall():
                    suffix = sid[len(prefix) :]
                    if suffix.isdigit():
                        max_existing = max(max_existing, int(suffix))
        self._session_counter = max(self._session_counter, max_existing) + 1
        session_id = f"{prefix}{self._session_counter:04d}"
        return InspectionSession(session_id, box_code, order, inspector, station)

    def records_for_box(self, box_code: BoxCode) -> list[InspectionRecord]:
        with self._connection() as conn:
            return self._fetch_records(conn, box_code_filter=box_code.text)

    def submit_for_review(self, record: InspectionRecord) -> None:
        """Lưu kết quả AI, phiên chuyển sang Pending Review (D-020)."""
        record.session.status = SessionStatus.PENDING_REVIEW
        session = record.session
        detection = record.detection
        assessment = record.assessment
        deep_json = (
            json.dumps(record.deep_analysis.to_dict())
            if record.deep_analysis is not None
            else None
        )

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO inspection_sessions (
                        session_id, box_code, order_code, box_number, total_boxes,
                        inspector, station, status, notes, started_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        notes = EXCLUDED.notes
                    """,
                    (
                        session.session_id,
                        session.box_code.text,
                        session.order.order_code,
                        session.box_code.box_number,
                        session.box_code.total_boxes,
                        session.inspector,
                        session.station,
                        session.status.value,
                        session.notes,
                        session.started_at,
                    ),
                )

                cur.execute(
                    "DELETE FROM evidence_images WHERE session_id = %s",
                    (session.session_id,),
                )
                for ev in record.evidence:
                    cur.execute(
                        """
                        INSERT INTO evidence_images (
                            session_id, captured_at, is_auto_capture, relative_path, sha256
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            session.session_id,
                            ev.captured_at,
                            ev.is_auto_capture,
                            ev.relative_path,
                            ev.sha256,
                        ),
                    )

                cur.execute(
                    """
                    INSERT INTO inspection_results (
                        session_id, total_objects, class_counts, mean_confidence,
                        recommendation, reasons, defect_ratios, deep_analysis
                    )
                    VALUES (%s, %s, %s::jsonb, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (session_id) DO UPDATE SET
                        total_objects = EXCLUDED.total_objects,
                        class_counts = EXCLUDED.class_counts,
                        mean_confidence = EXCLUDED.mean_confidence,
                        recommendation = EXCLUDED.recommendation,
                        reasons = EXCLUDED.reasons,
                        defect_ratios = EXCLUDED.defect_ratios,
                        deep_analysis = EXCLUDED.deep_analysis
                    """,
                    (
                        session.session_id,
                        detection.total_objects,
                        json.dumps(detection.class_counts),
                        detection.mean_confidence,
                        assessment.recommendation.value,
                        json.dumps(assessment.reasons),
                        json.dumps(assessment.defect_ratios),
                        deep_json,
                    ),
                )

    def apply_review(self, record: InspectionRecord, review: ReviewRecord) -> None:
        record.review = review
        record.session.status = SessionStatus.COMPLETED

        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE inspection_sessions
                    SET status = %s,
                        completed_at = %s
                    WHERE session_id = %s
                    """,
                    (
                        record.session.status.value,
                        review.reviewed_at,
                        record.session_id,
                    ),
                )
                cur.execute(
                    """
                    UPDATE inspection_results
                    SET decision = %s,
                        reviewer = %s,
                        review_notes = %s,
                        reviewed_at = %s
                    WHERE session_id = %s
                    """,
                    (
                        review.decision.value,
                        review.reviewer,
                        review.notes,
                        review.reviewed_at,
                        record.session_id,
                    ),
                )

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

