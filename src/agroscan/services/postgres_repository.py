"""Data access for AgroScan Database Design v1.2."""

from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Union
from uuid import UUID, uuid4

import psycopg2
from psycopg2.extras import Json

from agroscan.models.inspection_models import (
    AiRecommendation, AttributedNote, AuditEvent, BoxCode, BoxZone, DefectCriterion, DetectionResult, EvidenceImage,
    InspectionRecord, InspectionSession, Order, OrderSummary, Product,
    QualityAssessmentResult, ReviewerDecision, ReviewRecord, SessionStatus,
)
from agroscan.models.user_models import Role, User
from agroscan.models.vlm_models import VlmSchemaError, parse_vlm_response
from agroscan.services.catalog_validation import validate_product
from agroscan.services.database import DbConfig, get_connection, resolve_db_config
from agroscan.services.evidence_service import verify_evidence_integrity
from agroscan.services.order_import import (
    ImportFileError,
    ImportIssue,
    LotRow,
    as_parsed_rows,
    check_headers,
    order_codes,
    parse_order_file,
    validate_rows,
)
from agroscan.services.passwords import hash_password


_STATUS = {
    "draft": SessionStatus.IN_PROGRESS,
    "submitted": SessionStatus.PENDING_REVIEW,
    "reviewed": SessionStatus.COMPLETED,
    "reinspect": SessionStatus.COMPLETED,
}
_RECOMMENDATION = {
    "conforming": AiRecommendation.PASS,
    "nonconforming": AiRecommendation.FAIL,
}
_ROLE = {"admin": Role.ADMIN, "inspector": Role.INSPECTOR, "manager": Role.MANAGER}
_TABLES = """
    'users', 'products', 'inspection_profiles', 'quality_rules', 'sampling_rules',
    'orders', 'lots', 'boxes', 'sample_selections', 'inspections', 'inspection_batches',
    'inspection_images', 'observed_products', 'lot_decisions', 'audit_logs'
"""
_BOXES = """
    SELECT b.*, row_number() OVER (PARTITION BY lot_id ORDER BY box_code, id) AS box_number
    FROM agroscan.boxes b
"""


class _ImportRejected(Exception):
    """Abort the import transaction with one reportable issue."""

    def __init__(self, issue: ImportIssue) -> None:
        super().__init__(str(issue))
        self.issue = issue


def _local(value: datetime) -> datetime:
    return value.astimezone().replace(tzinfo=None)


def _user(login: str, role: str, can_review: bool, active: bool,
          display_name: Optional[str] = None) -> User:
    return User(login, display_name or login, Role.REVIEWER if can_review else _ROLE[role], active)


class PostgresRepository:
    """Read and update the agroscan namespace from the workstation."""

    def __init__(self, settings=None, db_config: Optional[DbConfig] = None) -> None:
        self._config = db_config or (
            settings if isinstance(settings, DbConfig) else resolve_db_config(settings)
        )

    @property
    def db_config(self) -> DbConfig:
        return self._config

    @contextmanager
    def _connection(self):
        try:
            conn = get_connection(self._config)
            try:
                with conn:
                    yield conn
            finally:
                conn.close()
        except psycopg2.Error as exc:
            raise ValueError(exc.diag.message_primary or str(exc)) from exc

    def ping(self) -> tuple[bool, str]:
        try:
            with self._connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT has_schema_privilege(to_regnamespace('agroscan'), 'USAGE')")
                if not cur.fetchone()[0]:
                    return False, (
                        f"Schema agroscan is missing or {self._config.user} lacks USAGE "
                        f"in {self._config.dbname}. See scripts/db_v1_2/README.md."
                    )
                cur.execute(f"""
                    SELECT count(*) FROM information_schema.tables
                    WHERE table_schema = 'agroscan' AND table_type = 'BASE TABLE'
                      AND table_name IN ({_TABLES})
                      AND has_table_privilege(format('%I.%I', table_schema, table_name), 'SELECT')
                """)
                if cur.fetchone()[0] != 15:
                    return False, "AgroScan v1.2 requires read access to all 15 agroscan tables."
                cur.execute("SELECT id FROM agroscan.current_selections LIMIT 0")
                cur.execute("SELECT lot_id FROM agroscan.latest_lot_decisions LIMIT 0")
                cur.execute("SELECT inspection_id FROM agroscan.box_rule_counts LIMIT 0")
            return True, f"Connected to {self._config.dbname} (agroscan v1.2)."
        except ValueError as exc:
            return False, str(exc)

    def account(self, login: str):
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT u.login, u.role, u.can_review, u.active, a.details->>'display_name',
                       u.password_hash
                FROM agroscan.users u
                LEFT JOIN LATERAL (
                    SELECT details FROM agroscan.audit_logs
                    WHERE target_type = 'user' AND target_key = u.id::text
                      AND action = 'workstation_account_saved'
                    ORDER BY id DESC LIMIT 1
                ) a ON true
                WHERE u.login = %s
            """, (login,))
            row = cur.fetchone()
        return (_user(*row[:-1]), row[-1]) if row else None

    @property
    def users(self) -> list[User]:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT u.login, u.role, u.can_review, u.active, a.details->>'display_name'
                FROM agroscan.users u
                LEFT JOIN LATERAL (
                    SELECT details FROM agroscan.audit_logs
                    WHERE target_type = 'user' AND target_key = u.id::text
                      AND action = 'workstation_account_saved'
                    ORDER BY id DESC LIMIT 1
                ) a ON true
                ORDER BY u.login
            """)
            return [_user(*row) for row in cur.fetchall()]

    def save_user(self, username, display_name, role, is_active=True, password=None, *, create_only=False) -> User:
        name, label = username.strip().lower(), display_name.strip()
        if not name or not label:
            raise ValueError("Enter a username and display name.")
        digest = hash_password(password) if password else None
        db_role = "inspector" if role is Role.REVIEWER else role.name.lower()
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT id, password_hash FROM agroscan.users WHERE login = %s FOR UPDATE
            """, (name,))
            existing = cur.fetchone()
            if create_only and existing:
                raise ValueError(f"Account {name} already exists.")
            if existing and existing[0] < 0:
                raise ValueError("Fixture accounts identify historical actors and cannot be edited here.")
            if existing is None and digest is None:
                raise ValueError("A new account requires a password.")
            cur.execute("""
                INSERT INTO agroscan.users (login, role, can_review, active, password_hash)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (login) DO UPDATE
                SET role = EXCLUDED.role, can_review = EXCLUDED.can_review,
                    active = EXCLUDED.active, password_hash = EXCLUDED.password_hash
                WHERE users.id > 0 AND NOT %s
                RETURNING id
            """, (name, db_role, role is Role.REVIEWER, is_active, digest or existing[1], create_only))
            saved = cur.fetchone()
            if not saved:
                raise ValueError(f"Account {name} already exists or is reserved.")
            cur.execute("""
                INSERT INTO agroscan.audit_logs (action, target_type, target_key, details)
                VALUES ('workstation_account_saved', 'user', %s, %s)
            """, (str(saved[0]), Json({"display_name": label})))
        return User(name, label, role, is_active)

    @staticmethod
    def _product(code, name, category, settings, rules) -> Product:
        config = (settings or {}).get("workstation_detector", {})
        criteria = [
            DefectCriterion(rule[0], float(rule[2] or 0), rule[1] == "exclusion", rule[3] or "gt")
            for rule in rules
        ]
        return Product(
            code.upper(), name, category, config.get("model_file", ""),
            config.get("detect_classes", []), criteria, config.get("min_objects", 5),
            config.get("min_confidence", 0.60),
        )

    def _fetch_products(self, conn):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.code, p.name, p.category, f.applicability,
                       coalesce(r.rules, '[]'::jsonb)
                FROM agroscan.products p
                LEFT JOIN LATERAL (
                    SELECT id, applicability FROM agroscan.inspection_profiles
                    WHERE product_id = p.id AND retired_at IS NULL
                    ORDER BY version DESC LIMIT 1
                ) f ON true
                LEFT JOIN LATERAL (
                    SELECT jsonb_agg(jsonb_build_array(code, rule_type, limit_ratio, operator)
                                     ORDER BY id) AS rules
                    FROM agroscan.quality_rules WHERE profile_id = f.id
                ) r ON true
                ORDER BY p.code
            """)
            return [self._product(*row) for row in cur.fetchall()]

    @property
    def products(self) -> list[Product]:
        with self._connection() as conn:
            return self._fetch_products(conn)

    def find_product(self, code: str) -> Optional[Product]:
        return next((p for p in self.products if p.code == code.strip().upper()), None)

    def categories(self) -> list[str]:
        return sorted({p.category for p in self.products})

    def orders_for_product(self, code: str) -> list[Order]:
        return [order for order in self.orders.values() if order.product.code == code]

    def save_product(self, product: Product, original_code: Optional[str] = None) -> Product:
        original = (original_code or product.code).upper()
        errors = validate_product(product, [p.code for p in self.products if p.code != original])
        if errors:
            raise ValueError("\n".join(errors))
        detector = {key: getattr(product, key) for key in (
            "model_file", "detect_classes", "min_objects", "min_confidence"
        )}
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, code FROM agroscan.products WHERE upper(code)=%s FOR UPDATE", (original,))
            row = cur.fetchone()
            if row:
                product_id = row[0]
                code = row[1] if original == product.code else product.code
                cur.execute("""
                    UPDATE agroscan.products SET code=%s, name=%s, category=%s WHERE id=%s
                """, (code, product.name, product.category, product_id))
            else:
                cur.execute("""
                    INSERT INTO agroscan.products (code, name, category) VALUES (%s,%s,%s) RETURNING id
                """, (product.code, product.name, product.category))
                product_id = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO agroscan.inspection_profiles
                    (product_id, version, reference, applicability)
                SELECT %s, coalesce(max(version),0)+1, 'Workstation draft', %s
                FROM agroscan.inspection_profiles WHERE product_id=%s
                RETURNING id
            """, (product_id, Json({"workstation_detector": detector}), product_id))
            profile_id = cur.fetchone()[0]
            cur.executemany("""
                INSERT INTO agroscan.quality_rules
                    (profile_id, code, rule_type, operator, limit_ratio, source_clause)
                VALUES (%s,%s,%s,%s,%s,'Workstation draft')
            """, [
                (profile_id, c.defect_class, "exclusion" if c.is_critical else "ratio",
                 None if c.is_critical else c.operator, None if c.is_critical else c.max_ratio)
                for c in product.criteria
            ])
        return product

    def delete_product(self, code: str) -> None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT id FROM agroscan.products WHERE upper(code)=%s FOR UPDATE", (code.upper(),))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Product {code} was not found.")
            product_id = row[0]
            cur.execute("""
                SELECT 1 FROM agroscan.inspection_profiles f
                WHERE f.product_id=%s AND (f.approved OR EXISTS (
                    SELECT FROM agroscan.lots WHERE profile_id=f.id
                ))
            """, (product_id,))
            if cur.fetchone():
                raise ValueError("This product has an approved or assigned profile.")
            cur.execute("""
                DELETE FROM agroscan.quality_rules WHERE profile_id IN (
                    SELECT id FROM agroscan.inspection_profiles WHERE product_id=%s
                )
            """, (product_id,))
            cur.execute("DELETE FROM agroscan.inspection_profiles WHERE product_id=%s", (product_id,))
            cur.execute("DELETE FROM agroscan.products WHERE id=%s", (product_id,))

    def _fetch_orders(self, conn, order_code: Optional[str] = None) -> dict[str, Order]:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.id, o.order_code, l.lot_code, count(*) OVER (PARTITION BY o.id),
                       o.supplier, l.declared_boxes, o.imported_at, p.code, p.name, p.category,
                       f.applicability, coalesce(r.rules, '[]'::jsonb),
                       (a.details->>'expected_quantity')::int, d.outcome, d.version,
                       convert_from(d.manifest_bytes,'UTF8')::jsonb
                FROM agroscan.lots l JOIN agroscan.orders o ON o.id=l.order_id
                JOIN agroscan.inspection_profiles f ON f.id=l.profile_id
                JOIN agroscan.products p ON p.id=f.product_id
                LEFT JOIN agroscan.latest_lot_decisions d ON d.lot_id=l.id
                LEFT JOIN LATERAL (
                    SELECT jsonb_agg(jsonb_build_array(code, rule_type, limit_ratio, operator)
                                     ORDER BY id) AS rules
                    FROM agroscan.quality_rules WHERE profile_id=f.id
                ) r ON true
                LEFT JOIN LATERAL (
                    SELECT details FROM agroscan.audit_logs
                    WHERE target_type='order' AND target_key=o.id::text AND action='order_imported'
                      AND details->'lot_id'=to_jsonb(l.id)
                    ORDER BY id DESC LIMIT 1
                ) a ON true
                WHERE %(code)s::text IS NULL OR upper(o.order_code) = %(code)s
                ORDER BY o.order_code, l.lot_code
            """, {"code": order_code.strip().upper() if order_code else None})
            orders = {}
            for lot_id, order_code, lot_code, count, supplier, boxes, imported, code, name, category, config, rules, quantity, outcome, decision_version, manifest in cur.fetchall():
                key = order_code if count == 1 else f"{order_code}:{lot_code}"
                orders[key.upper()] = Order(
                    key, self._product(code, name, category, config, rules),
                    supplier or "", boxes, quantity, _local(imported),
                    lot_id=lot_id, lot_code=lot_code, lot_outcome=outcome,
                    decision_version=decision_version, sampling_recommendation=(manifest or {}).get("recommendation"),
                    override_reason=(manifest or {}).get("override_reason"),
                    signed_attempts=tuple(f"INS-{slot['attempt_id']}" for slot in (manifest or {}).get("slots", [])),
                )
            return orders

    @property
    def orders(self) -> dict[str, Order]:
        with self._connection() as conn:
            return self._fetch_orders(conn)

    def list_orders(self) -> list[Order]:
        """Return every imported order lot, sorted by order code and batch."""
        return list(self.orders.values())

    def get_order(self, order_code: str, *, lot_code: Optional[str] = None) -> list[Order]:
        """Return lots matching ``order_code`` (or ``ORDER:BATCH``); empty when not found."""
        code = (order_code or "").strip().upper()
        if not code:
            return []
        target_lot = (lot_code or "").strip().upper() or None
        if target_lot is None and ":" in code:
            code, target_lot = code.split(":", 1)
        with self._connection() as conn:
            lots = list(self._fetch_orders(conn, code).values())
        if target_lot is not None:
            return [o for o in lots if (o.lot_code or "").upper() == target_lot]
        return lots

    def import_order_file(self, file_path: Union[Path, str], *, actor: str = "") -> tuple[int, list[ImportIssue]]:
        """Parse, validate and atomically import a CSV or Excel order file."""
        path = Path(file_path)
        try:
            parsed = parse_order_file(path)
        except ImportFileError as exc:
            return 0, [ImportIssue(None, None, "", str(exc))]
        header_issues = check_headers(parsed.headers)
        if header_issues:
            return 0, header_issues
        return self.import_orders(parsed.rows, actor=actor, source_file=path.name)

    @staticmethod
    def _importable_products(cur) -> dict[str, tuple[int, str]]:
        """Product code -> (latest approved, active profile id, category)."""
        cur.execute("""
            SELECT DISTINCT ON (p.id) upper(p.code), f.id, p.category
            FROM agroscan.products p JOIN agroscan.inspection_profiles f ON f.product_id=p.id
            WHERE f.approved AND f.retired_at IS NULL
            ORDER BY p.id, f.version DESC
        """)
        return {code: (profile_id, category) for code, profile_id, category in cur.fetchall()}

    def _validate_orders(self, cur, rows):
        parsed = as_parsed_rows(rows)
        products = self._importable_products(cur)
        cur.execute(
            "SELECT upper(order_code) FROM agroscan.orders WHERE upper(order_code) = ANY(%s)",
            (sorted(order_codes(parsed)),),
        )
        existing = [row[0] for row in cur.fetchall()]
        lots, issues = validate_rows(parsed, {c: v[1] for c, v in products.items()}, existing)
        return lots, issues, products

    def validate_orders(self, rows) -> tuple[list[LotRow], list[ImportIssue]]:
        """Dry-run the import checks against the database without writing."""
        try:
            with self._connection() as conn, conn.cursor() as cur:
                return self._validate_orders(cur, rows)[:2]
        except ValueError as exc:
            return [], [ImportIssue(None, None, "", f"Database error: {exc}")]

    def import_orders(self, rows, *, actor="", source_file="") -> tuple[int, list[ImportIssue]]:
        """Validate all rows, then store every order and lot in one transaction.

        All-or-nothing: any validation or database issue stores nothing and
        returns ``(0, issues)``. Rows sharing an Order Code become one order
        with one lot per Batch. Returns ``(lots_imported, [])`` on success.
        """
        if not source_file.strip():
            return 0, [ImportIssue(None, None, "", "A source file name is required.")]
        try:
            with self._connection() as conn, conn.cursor() as cur:
                cur.execute("SELECT id FROM agroscan.users WHERE login=%s AND role='admin' AND active", (actor,))
                user = cur.fetchone()
                if not user:
                    return 0, [ImportIssue(None, None, "", "An active administrator is required to import orders.")]
                lots, issues, products = self._validate_orders(cur, rows)
                if issues:
                    return 0, issues
                order_ids: dict[str, int] = {}
                for lot in lots:
                    if lot.order_code not in order_ids:
                        cur.execute("""
                            INSERT INTO agroscan.orders (order_code,supplier,source_file)
                            VALUES (%s,%s,%s) ON CONFLICT (order_code) DO NOTHING RETURNING id
                        """, (lot.order_code, lot.supplier, source_file))
                        saved = cur.fetchone()
                        if not saved:
                            raise _ImportRejected(ImportIssue(
                                lot.row_number, "Order Code", lot.order_code,
                                "Order Code already exists in the database.",
                            ))
                        order_ids[lot.order_code] = saved[0]
                    cur.execute("""
                        INSERT INTO agroscan.lots (order_id,profile_id,lot_code,declared_boxes)
                        VALUES (%s,%s,%s,%s) RETURNING id
                    """, (order_ids[lot.order_code], products[lot.product_code][0], lot.batch, lot.lot_size))
                    lot_id = cur.fetchone()[0]
                    cur.execute("""
                        INSERT INTO agroscan.boxes (lot_id,box_code)
                        SELECT %s, 'BOX-' || lpad(n::text,4,'0') FROM generate_series(1,%s) n
                    """, (lot_id, lot.lot_size))
                    cur.execute("""
                        INSERT INTO agroscan.audit_logs (actor_id,action,target_type,target_key,details)
                        VALUES (%s,'order_imported','order',%s,%s)
                    """, (user[0], str(order_ids[lot.order_code]), Json({
                        "lot_id": lot_id, "declared_boxes": lot.lot_size,
                        "expected_quantity": lot.expected_quantity,
                    })))
                return len(lots), []
        except _ImportRejected as exc:
            return 0, [exc.issue]
        except (ValueError, psycopg2.Error) as exc:
            message = getattr(getattr(exc, "diag", None), "message_primary", None) or str(exc)
            return 0, [ImportIssue(None, None, "", f"Database error, nothing was imported: {message}")]

    def resolve_box(self, text: str) -> tuple[BoxCode, Order]:
        with self._connection() as conn, conn.cursor() as cur:
            orders = self._fetch_orders(conn)
            try:
                token = str(UUID(text.strip()))
            except ValueError:
                code = BoxCode.parse(text)
                order = orders.get(code.order_code)
                if order is None:
                    raise ValueError(f"Order {code.order_code} was not found.")
                if code.total_boxes != order.total_boxes:
                    raise ValueError(f"Box code says {code.total_boxes} boxes but order has {order.total_boxes}.")
                cur.execute(f"""
                    WITH boxes AS ({_BOXES})
                    SELECT 1 FROM boxes WHERE lot_id=%s AND box_number=%s
                """, (order.lot_id, code.box_number))
                if not cur.fetchone():
                    raise ValueError("Box was not found in the lot register.")
                return code, order
            cur.execute(f"""
                WITH boxes AS ({_BOXES})
                SELECT lot_id,box_number FROM boxes WHERE scan_token=%s AND lot_id=ANY(%s)
            """, (token, [order.lot_id for order in orders.values()]))
            row = cur.fetchone()
            if not row:
                raise ValueError("Box scan token was not found.")
            order = next(o for o in orders.values() if o.lot_id == row[0])
            return BoxCode(order.order_code.upper(), row[1], order.total_boxes), order

    @property
    def records(self) -> list[InspectionRecord]:
        with self._connection() as conn, conn.cursor() as cur:
            orders = {order.lot_id: order for order in self._fetch_orders(conn).values()}
            cur.execute(f"""
                WITH boxes AS ({_BOXES})
                SELECT i.id,b.lot_id,b.box_number,creator.login,i.station_code,i.state,
                       coalesce((i.checkpoint->>'started_at')::timestamptz,
                                ev.first_image,i.submitted_at,s.selected_at),
                       i.machine_box_result,reviewer.login,i.review_note,i.reviewed_at,i.box_result,
                       ev.images,coalesce(stats.num_objects,0), coalesce(stats.ratios,'{{}}'::jsonb),
                       i.checkpoint->>'notes', submitted.details->'workstation_vlm_analysis',
                       submitted.details->'workstation_vlm_simulated', ev.demo, i.attempt_no,
                       i.coverage->>'confirmed', submitted.details->'view_zones'
                FROM agroscan.inspections i
                JOIN agroscan.sample_selections s ON s.id=i.selection_id
                JOIN boxes b ON b.id=s.box_id
                JOIN agroscan.users creator ON creator.id=i.inspector_id
                LEFT JOIN agroscan.users reviewer ON reviewer.id=i.reviewer_id
                LEFT JOIN LATERAL (
                    SELECT min(im.received_at) AS first_image,
                           bool_or(im.usage_context='demo') AS demo,
                           array_agg(im.id ORDER BY g.batch_no, im.is_count_image DESC, im.id) AS images
                    FROM agroscan.inspection_batches g
                    JOIN agroscan.inspection_images im ON im.batch_id=g.id
                    WHERE g.inspection_id=i.id
                ) ev ON true
                LEFT JOIN LATERAL (
                    SELECT max(denominator) AS num_objects,
                           jsonb_object_agg(code,machine_affected::numeric/nullif(denominator,0)) AS ratios
                    FROM agroscan.box_rule_counts WHERE inspection_id=i.id
                ) stats ON true
                LEFT JOIN agroscan.audit_logs submitted
                    ON submitted.target_type='inspection' AND submitted.target_key=i.id::text
                       AND submitted.action='inspection_submitted'
                WHERE b.lot_id=ANY(%s)
                ORDER BY 7 DESC,i.attempt_no DESC,i.id DESC
            """, (list(orders),))
            rows = cur.fetchall()
            cur.execute("""
                SELECT id, coalesce(captured_at,received_at), object_key, sha256,
                       width_px, height_px, source_kind, usage_context
                FROM agroscan.inspection_images WHERE id=ANY(%s)
            """, ([image for row in rows for image in (row[12] or [])],))
            images = {
                image_id: EvidenceImage(_local(ts), False, key, digest, width, height,
                                        source, context == "demo")
                for image_id, ts, key, digest, width, height, source, context in cur.fetchall()
            }
            cur.execute("""
                SELECT a.target_key,a.id,a.occurred_at,a.action,u.login,u.role,u.can_review,
                       a.details->>'text'
                FROM agroscan.audit_logs a LEFT JOIN agroscan.users u ON u.id=a.actor_id
                WHERE a.target_type='inspection' AND a.target_key=ANY(%s)
                ORDER BY a.occurred_at,a.id
            """, ([str(row[0]) for row in rows],))
            events, notes_by_id = defaultdict(list), defaultdict(list)
            for key, event_id, ts, action, actor, role, can_review, message in cur.fetchall():
                label = "Reviewer" if can_review else (role or "system").title()
                if action == "review_note_added":
                    label = "Reviewer"
                    notes_by_id[key].append(AttributedNote(actor, label, message, _local(ts), str(event_id)))
                events[key].append(AuditEvent(action, actor or "System", label, _local(ts), message or ""))
        records = []
        known_zones = {zone.value: zone for zone in BoxZone}
        for row in rows:
            (identifier, lot_id, number, inspector, station, state, started, result,
             reviewer, notes, reviewed, verdict, image_ids, observed, ratios,
             inspection_notes, vlm_payload, vlm_simulated, demo, attempt, confirmed, zones) = row
            order = orders[lot_id]
            session = InspectionSession(
                f"INS-{identifier}", BoxCode(order.order_code.upper(), number, order.total_boxes),
                order, inspector, station, _STATUS[state],
                notes=inspection_notes or "", started_at=_local(started),
            )
            result = result or {}
            evaluation = QualityAssessmentResult(
                _RECOMMENDATION.get(result.get("outcome"), AiRecommendation.NEEDS_REVIEW),
                [], {key: float(ratio) for key, ratio in ratios.items() if ratio is not None},
                bool(demo),
            )
            decision = None
            if reviewed:
                outcome = {"conforming": ReviewerDecision.PASS, "nonconforming": ReviewerDecision.FAIL}
                decision = ReviewRecord(outcome.get(verdict, ReviewerDecision.RE_INSPECT),
                                        reviewer, notes or "", _local(reviewed))
            detection = DetectionResult(
                result.get("denominator", observed), result.get("class_counts", {}),
                float(result.get("mean_confidence", 0.0)), is_simulated=bool(demo),
            )
            try:
                vlm = parse_vlm_response(vlm_payload) if vlm_payload else None
            except VlmSchemaError:
                vlm = None
            if vlm:
                vlm.is_simulated = bool(vlm_simulated)
            evidence = [images[x] for x in image_ids or []]
            for image in evidence:
                tag = (zones or {}).get(image.relative_path)
                if tag in known_zones:
                    image.zone = known_zones[tag]
            records.append(InspectionRecord(
                session, evidence, detection, evaluation,
                deep_analysis=vlm, review=decision, version=attempt,
                whole_box_confirmed=confirmed == "true", audit_trail=events[str(identifier)],
                attributed_notes=notes_by_id[str(identifier)],
            ))
        return records

    def records_for_box(self, box_code: BoxCode) -> list[InspectionRecord]:
        return [record for record in self.records if record.session.box_code == box_code]

    def box_versions(self, box_code: BoxCode) -> list[InspectionRecord]:
        return sorted(self.records_for_box(box_code), key=lambda record: record.session.started_at)

    def add_attributed_note(self, session_id: str, author: str, role: str, text: str) -> AttributedNote:
        message = text.strip()
        if not message:
            raise ValueError("Enter a review note.")
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agroscan.audit_logs (actor_id,action,target_type,target_key,details)
                SELECT u.id,'review_note_added','inspection',i.id::text,
                       jsonb_build_object('text',%s::text,'attempt_no',i.attempt_no)
                FROM agroscan.inspections i CROSS JOIN agroscan.users u
                WHERE i.id::text=%s AND u.login=%s AND u.active AND u.can_review
                RETURNING id, occurred_at
            """, (message, session_id.removeprefix("INS-"), author))
            row = cur.fetchone()
            if row is None:
                raise ValueError("An active Reviewer and an existing inspection are required.")
            return AttributedNote(author, Role.REVIEWER.value, message, _local(row[1]), str(row[0]))

    def _active_attempt(self, cur, order, box_code, inspector):
        cur.execute(f"""
            WITH boxes AS ({_BOXES})
            SELECT s.id, u.id, i.id, i.attempt_no, i.state,
                   (p.applicability->>'scope'='demo' OR sr.verification->>'scope'='demo') IS TRUE,
                   p.applicability
            FROM boxes b JOIN agroscan.lots l ON l.id=b.lot_id
            JOIN agroscan.current_selections s ON s.box_id=b.id
            JOIN agroscan.inspection_profiles p ON p.id=l.profile_id
            JOIN agroscan.sampling_rules sr ON sr.id=l.sampling_rule_id
            JOIN agroscan.users u ON u.login=%s AND u.active AND u.role='inspector'
            LEFT JOIN LATERAL (
                SELECT id,attempt_no,state FROM agroscan.inspections WHERE selection_id=s.id
                ORDER BY attempt_no DESC LIMIT 1
            ) i ON true
            WHERE l.id=%s AND b.box_number=%s AND l.declared_boxes=%s
        """, (inspector, order.lot_id, box_code.box_number, box_code.total_boxes))
        row = cur.fetchone()
        if row is None:
            raise ValueError("An active inspector and a box in the current sampling plan are required.")
        return row

    def create_session(self, box_code, order, inspector, station) -> InspectionSession:
        with self._connection() as conn, conn.cursor() as cur:
            _, _, _, _, state, demo, config = self._active_attempt(cur, order, box_code, inspector)
            if state and state != "reinspect":
                raise ValueError("The active sample already has an open or resolved inspection.")
            if not demo and not config.get("workstation_detector", {}).get("model_file"):
                raise ValueError("The assigned profile needs a configured detector.")
        return InspectionSession(f"RUN-{uuid4().hex}", box_code, order, inspector, station)

    def _insert_batch_evidence(self, cur, inspection_id, items, scope, model, product, operation):
        cur.execute("""
            INSERT INTO agroscan.inspection_batches (inspection_id,batch_no)
            VALUES (%s,1) RETURNING id
        """, (inspection_id,))
        batch = cur.fetchone()[0]
        for index, image in enumerate(items):
            count_image = index == len(items) - 1
            cur.execute("""
                INSERT INTO agroscan.inspection_images
                    (batch_id,is_count_image,object_key,sha256,width_px,height_px,captured_at,
                     source_kind,usage_context)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """, (batch, count_image, image.relative_path, image.sha256, image.width_px,
                  image.height_px, image.captured_at.astimezone(), image.source_kind, scope))
            image_id = cur.fetchone()[0]
        count = items[-1]
        trusted = count.model_file == model and bool(model)
        classes = Counter(unit.label for unit in count.units)
        confidence = sum(unit.confidence for unit in count.units) / len(count.units)
        cur.execute("""
            INSERT INTO agroscan.audit_logs (action,target_type,target_key,details)
            VALUES ('inference_result','image',%s,%s)
        """, (str(image_id), Json({
            "inspection_id": inspection_id, "execution_id": f"{operation}-detector",
            "image_sha256": count.sha256, "stage": "detector", "model_version": count.model_file,
            "prompt_version": None, "predicted_label": None, "route": "workstation_onnx",
            "explanation_en": "Object detector executed on the count image.",
            "confidence": confidence, "ocr": {"readability": "not_applicable"},
            "schema_version": "1", "validation": "valid", "error": None,
        })))
        observations = []
        for index, unit in enumerate(count.units, 1):
            findings = []
            for rule in product.criteria:
                if trusted and unit.confidence >= product.min_confidence and unit.label == rule.defect_class:
                    assessment = "present"
                else:
                    assessment = "uncertain"
                findings.append({
                    "code": rule.defect_class, "assessment": assessment,
                    "detail": f"Detector class: {unit.label}, confidence: {unit.confidence:.3f}.",
                })
            warning = "red" if any(f["assessment"] == "present" for f in findings) else "yellow"
            if not product.criteria:
                warning = "green"
            observations.append((
                batch, image_id, index, unit.x, unit.y, unit.width, unit.height, Json(findings), warning,
            ))
        cur.executemany("""
            INSERT INTO agroscan.observed_products
                (batch_id,count_image_id,unit_no,x,y,width,height,ai_findings,warning)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, observations)
        return batch, classes, confidence

    @staticmethod
    def _machine_result(cur, inspection_id, classes, confidence, denominator, too_few):
        cur.execute("""
            SELECT code,rule_type,operator,limit_ratio,machine_affected,
                   CASE WHEN rule_type='exclusion' THEN machine_affected>0
                        WHEN operator='gt' THEN machine_affected>limit_ratio*denominator
                        ELSE machine_affected>=limit_ratio*denominator END
            FROM agroscan.box_rule_counts WHERE inspection_id=%s ORDER BY code
        """, (inspection_id,))
        comparisons, exclusions = [], []
        violated = False
        for code, rule_type, operator, limit, affected, exceeds in cur.fetchall():
            violated |= bool(exceeds)
            if rule_type == "exclusion":
                exclusions.append({"code": code, "present": bool(exceeds)})
            else:
                comparisons.append({
                    "code": code, "affected": affected, "operator": operator,
                    "limit_ratio": float(limit), "ratio": affected / denominator,
                })
        return {
            "class_counts": classes, "denominator": denominator, "mean_confidence": confidence,
            "comparisons": comparisons, "exclusions": exclusions,
            "outcome": "nonconforming" if violated and not too_few else "needs_review",
        }

    def submit_for_review(self, record: InspectionRecord, *, coverage_confirmed=False) -> None:
        items, session = record.evidence, record.session
        if session.status == SessionStatus.PENDING_REVIEW:
            return
        if not coverage_confirmed or not items or not items[-1].units:
            raise ValueError("Confirm whole-box coverage and capture a count image with detected objects.")
        if any(image.width_px <= 0 or image.height_px <= 0 or not verify_evidence_integrity(image)
               for image in items):
            raise ValueError("Every original image must be saved and match its recorded SHA-256.")
        with self._connection() as conn, conn.cursor() as cur:
            # Lock the lot before re-reading the current selection and latest attempt.
            cur.execute("SELECT id FROM agroscan.lots WHERE id=%s FOR UPDATE", (session.order.lot_id,))
            selection, actor, previous, attempt_no, state, demo, config = self._active_attempt(
                cur, session.order, session.box_code, session.inspector,
            )
            cur.execute("""
                SELECT id, machine_box_result FROM agroscan.inspections
                WHERE selection_id=%s AND checkpoint->>'operation_id'=%s AND state='submitted'
            """, (selection, session.session_id))
            saved = cur.fetchone()
            if saved:
                inspection_id, result = saved
            else:
                if state and state != "reinspect":
                    raise ValueError("The current sample already has an open or resolved inspection.")
                expected_model = config.get("workstation_detector", {}).get("model_file")
                if not demo and (any(image.demo_image for image in items) or not expected_model
                                 or items[-1].model_file != expected_model):
                    raise ValueError("Operational inspections require original evidence and the assigned detector.")
                detector = items[-1].model_file
                if not detector:
                    raise ValueError("A real detector execution is required on the count image.")
                checkpoint = {
                    "phase": "submitted", "operation_id": session.session_id,
                    "started_at": session.started_at.astimezone().isoformat(), "notes": session.notes,
                    "last_successful_stage": "rule_evaluation",
                }
                cur.execute("""
                    INSERT INTO agroscan.inspections
                        (selection_id,previous_id,inspector_id,attempt_no,station_code,ai_versions,checkpoint)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
                """, (selection, previous, actor, (attempt_no or 0) + 1, session.station,
                      Json({"detector": detector, "evaluation": "workstation-v1.2"}), Json(checkpoint)))
                inspection_id = cur.fetchone()[0]
                batch, classes, confidence = self._insert_batch_evidence(
                    cur, inspection_id, items, "demo" if demo else "operational", expected_model,
                    session.product, session.session_id,
                )
                denominator = len(items[-1].units)
                result = self._machine_result(
                    cur, inspection_id, classes, confidence, denominator,
                    denominator < session.product.min_objects,
                )
                cur.execute("SELECT clock_timestamp()")
                submitted = cur.fetchone()[0]
                coverage = {
                    "confirmed": True, "inspector_id": actor, "confirmed_at": submitted.isoformat(),
                    "batch_ids": [batch],
                }
                cur.execute("""
                    UPDATE agroscan.inspections
                    SET state='submitted',submitted_at=%s,coverage=%s,machine_box_result=%s
                    WHERE id=%s
                """, (submitted, Json(coverage), Json(result), inspection_id))
                details = {"operation_id": session.session_id, "view_zones": {
                    im.relative_path: im.zone.value for im in items if im.zone is not None
                }}
                if record.deep_analysis:
                    details["workstation_vlm_analysis"] = record.deep_analysis.to_dict()
                    details["workstation_vlm_simulated"] = record.deep_analysis.is_simulated
                cur.execute("""
                    INSERT INTO agroscan.audit_logs (actor_id,action,target_type,target_key,details,occurred_at)
                    VALUES (%s,'inspection_submitted','inspection',%s,%s,%s)
                """, (actor, str(inspection_id), Json(details), submitted))
        session.session_id = f"INS-{inspection_id}"
        session.status = SessionStatus.PENDING_REVIEW
        record.whole_box_confirmed = True
        record.assessment.recommendation = _RECOMMENDATION.get(
            result["outcome"], AiRecommendation.NEEDS_REVIEW,
        )

    def apply_review(self, record: InspectionRecord, review: ReviewRecord) -> None:
        if not review.notes.strip():
            raise ValueError("Enter a reason for this review.")
        result = {ReviewerDecision.PASS: "conforming", ReviewerDecision.FAIL: "nonconforming"}
        box_result = result.get(review.decision)
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                UPDATE agroscan.inspections i
                SET state=%s, reviewer_id=u.id, reviewed_at=clock_timestamp(), box_result=%s, review_note=%s
                FROM agroscan.users u
                WHERE i.id=%s AND i.state='submitted' AND u.login=%s AND u.active AND u.can_review
                RETURNING i.reviewed_at,u.id,i.id,i.attempt_no
            """, ("reviewed" if box_result else "reinspect", box_result, review.notes.strip(),
                  int(record.session_id.removeprefix("INS-")), review.reviewer))
            row = cur.fetchone()
            if not row:
                raise ValueError("The attempt is no longer pending or this reviewer is unauthorized.")
            cur.execute("""
                INSERT INTO agroscan.audit_logs (actor_id,action,target_type,target_key,details,occurred_at)
                VALUES (%s,'inspection_reviewed','inspection',%s,%s,%s)
            """, (row[1], str(row[2]), Json({"decision": review.decision.value, "text": review.notes.strip(),
                                           "attempt_no": row[3]}), row[0]))
        review.reviewed_at = _local(row[0])
        record.review = review
        record.session.status = SessionStatus.COMPLETED

    @property
    def export_history(self) -> list[tuple[datetime, str, str, str]]:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT occurred_at,details->>'format',details->>'path',details->>'filter'
                FROM agroscan.audit_logs WHERE action='workstation_export' ORDER BY id DESC
            """)
            return [(_local(ts), fmt, path, filters) for ts, fmt, path, filters in cur.fetchall()]

    def record_export(self, fmt: str, file_path: str, filter_summary: str = "All") -> None:
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO agroscan.audit_logs (action,target_type,target_key,details)
                VALUES ('workstation_export','export',%s,%s)
            """, (file_path, Json({"format": fmt, "path": file_path, "filter": filter_summary})))

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

    def sample_progress(self) -> list[OrderSummary]:
        """Count each active sample slot once, using its latest inspection attempt."""
        with self._connection() as conn, conn.cursor() as cur:
            orders = self._fetch_orders(conn)
            cur.execute("""
                SELECT b.lot_id, count(*),
                       count(*) FILTER (WHERE i.state='reviewed' AND i.box_result='conforming'),
                       count(*) FILTER (WHERE i.state='reviewed' AND i.box_result='nonconforming'),
                       count(*) FILTER (WHERE i.state IN ('submitted','reinspect')),
                       count(*) FILTER (WHERE i.state='reinspect')
                FROM agroscan.current_selections s JOIN agroscan.boxes b ON b.id=s.box_id
                LEFT JOIN LATERAL (
                    SELECT state,box_result FROM agroscan.inspections WHERE selection_id=s.id
                    ORDER BY attempt_no DESC LIMIT 1
                ) i ON true
                GROUP BY b.lot_id
            """)
            counts = {lot: values for lot, *values in cur.fetchall()}
        result = []
        for order in orders.values():
            total, passed, failed, pending, reinspect = counts.get(order.lot_id, (0, 0, 0, 0, 0))
            result.append(OrderSummary(order, passed, failed, pending, total-passed-failed-pending,
                                       reinspect, required_boxes=total))
        return result

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
        result = []
        for record in self.all_records():
            session = record.session
            day = session.started_at.date()
            identifiers = (session.box_code.text, session.session_id, session.order.lot_code or "")
            if needle and not any(needle in value.upper() for value in identifiers):
                continue
            decision = record.review.decision if record.review else record.assessment.recommendation
            if outcome and decision.value.casefold() != outcome.casefold():
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

