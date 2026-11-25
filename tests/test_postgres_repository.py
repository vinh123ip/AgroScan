"""Configuration and workstation integration tests for PostgreSQL v1.2."""

from contextlib import contextmanager
from datetime import datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from agroscan.models.inspection_models import (
    AiRecommendation,
    BoxCode,
    BoxZone,
    DetectedUnit,
    DefectCriterion,
    DetectionResult,
    InspectionRecord,
    Product,
    QualityAssessmentResult,
    ReviewerDecision,
    ReviewRecord,
    SessionStatus,
)
from agroscan.models.user_models import Role
from agroscan.services.app_settings import ConnectionSettings
from agroscan.services.database import get_connection, parse_env_file, resolve_db_config
from agroscan.services.evidence_service import capture_and_save_evidence
from agroscan.services.postgres_auth import PostgresAuthService
from agroscan.services.postgres_repository import PostgresRepository
from agroscan.main import create_repository
from agroscan.services.app_settings import AppSettings
from agroscan.ui.main_window import MainWindow
from agroscan.ui.navigation import PageKey
from agroscan.ui.theme import apply_theme

_APP: QApplication | None = None


def setUpModule() -> None:  # noqa: N802
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


class TestDatabaseConfigResolution(unittest.TestCase):
    """Verify .env parsing and ConnectionSettings precedence without network."""

    def test_parse_env_and_resolve_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "# comment\n"
                "AGROSCAN_DB_HOST=10.0.0.5\n"
                'AGROSCAN_DB_USER="pg_custom"\n'
                "AGROSCAN_DB_PASSWORD='secret'\n",
                encoding="utf-8",
            )
            parsed = parse_env_file(env_file)
            self.assertEqual(parsed["AGROSCAN_DB_HOST"], "10.0.0.5")
            self.assertEqual(parsed["AGROSCAN_DB_USER"], "pg_custom")
            self.assertEqual(parsed["AGROSCAN_DB_PASSWORD"], "secret")

            settings = ConnectionSettings(db_host="127.0.0.1", db_port=5432, db_name="agroscan", db_user="agroscan")
            old_val = os.environ.pop("AGROSCAN_DB_HOST", None)
            try:
                cfg = resolve_db_config(settings, env_path=env_file)
                self.assertEqual(cfg.host, "10.0.0.5")
                self.assertEqual(cfg.user, "pg_custom")
                self.assertEqual(cfg.password, "secret")

                os.environ["AGROSCAN_DB_HOST"] = "192.168.1.99"
                cfg_override = resolve_db_config(settings, env_path=env_file)
                self.assertEqual(cfg_override.host, "192.168.1.99")
            finally:
                os.environ.pop("AGROSCAN_DB_HOST", None)
                if old_val is not None:
                    os.environ["AGROSCAN_DB_HOST"] = old_val


class TestPostgresRepositoryLive(unittest.TestCase):
    """Exercise the seeded schema, including writes that roll back after each test."""

    def setUp(self) -> None:
        self.repo = PostgresRepository()
        ok, message = self.repo.ping()
        self.assertTrue(ok, message)

    @contextmanager
    def isolated_writes(self):
        connection = get_connection(self.repo.db_config)
        try:
            @contextmanager
            def use_transaction():
                with connection.cursor() as cur:
                    cur.execute("SAVEPOINT repository_call")
                    cur.execute("SET CONSTRAINTS ALL DEFERRED")
                try:
                    yield connection
                    with connection.cursor() as cur:
                        cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
                        cur.execute("RELEASE SAVEPOINT repository_call")
                except Exception:
                    with connection.cursor() as cur:
                        cur.execute("ROLLBACK TO SAVEPOINT repository_call")
                        cur.execute("RELEASE SAVEPOINT repository_call")
                    raise

            with patch.object(self.repo, "_connection", use_transaction):
                yield
        finally:
            connection.rollback()
            connection.close()

    def test_seeded_lots_and_scan_tokens(self) -> None:
        orders = self.repo.orders
        seeded = [orders[f"DEMO-V12-{index:02d}"] for index in range(1, 6)]
        self.assertEqual([o.product.code for o in seeded], ["APPLE", "ORANGE", "BANANA", "SHRIMP", "SQUID"])
        self.assertEqual([o.total_boxes for o in seeded], [3, 4, 3, 3, 3])
        self.assertEqual(seeded[-1].lot_outcome, "approve")
        box, order = self.repo.resolve_box("00000000-0000-4000-8000-000000120024")
        self.assertEqual(box, BoxCode("DEMO-V12-02", 4, 4))
        self.assertEqual(self.repo.resolve_box(box.text), (box, order))
        with self.assertRaises(ValueError):
            self.repo.resolve_box("AGS:DEMO-V12-02-01/3")

    def test_seeded_history_and_historical_accounts(self) -> None:
        entries = {r.session_id: r for r in self.repo.records}
        self.assertEqual(entries["INS--120311"].status, SessionStatus.IN_PROGRESS)
        self.assertEqual(len(entries["INS--120411"].evidence), 3)
        self.assertEqual(entries["INS--120511"].review.decision, ReviewerDecision.RE_INSPECT)
        auth = PostgresAuthService(self.repo)
        self.assertIsNone(auth.authenticate("demo12.admin", "!"))

    def test_account_catalog_and_order_import(self) -> None:
        with self.isolated_writes():
            admin = self.repo.save_user(
                f"test-{uuid4().hex}", "Test Admin", Role.ADMIN, password="Temporary-Pass-123",
            )
            self.assertEqual(PostgresAuthService(self.repo).authenticate(admin.username, "Temporary-Pass-123"), admin)
            code = f"TST{uuid4().hex[:10].upper()}"
            product = Product(code, "Test Kiwi", "Fruit", "fruit_defect.onnx",
                              ["fresh", "bruised"], [DefectCriterion("bruised", 0.15)])
            self.repo.save_product(product)
            self.assertEqual(self.repo.find_product(code), product)
            self.repo.delete_product(code)
            self.assertIsNone(self.repo.find_product(code))

            order_code = f"TEST-{uuid4().hex.upper()}"
            data = [{"order_code": order_code, "product_code": "APPLE", "supplier": "Test",
                     "total_boxes": 3, "expected_quantity": 15}]
            result = self.repo.import_orders(data, actor=admin.username, source_file="test.csv")
            self.assertEqual(result, (1, []))
            order = self.repo.orders[order_code]
            self.assertEqual(order.expected_quantity, 15)
            self.assertEqual(self.repo.resolve_box(f"AGS:{order_code}-01/03")[1], order)

    def test_inspection_submission_and_independent_review(self) -> None:
        with self.isolated_writes(), tempfile.TemporaryDirectory() as tmp:
            maker = self.repo.save_user(f"test-{uuid4().hex}", "Maker", Role.INSPECTOR, password="Temporary-Pass-123")
            reviewer = self.repo.save_user(f"test-{uuid4().hex}", "Reviewer", Role.REVIEWER, password="Temporary-Pass-123")
            box, order = self.repo.resolve_box("AGS:DEMO-V12-04-02/03")
            session = self.repo.create_session(box, order, maker.username, "STATION-TEST")
            original = QImage(12, 12, QImage.Format.Format_RGB32)
            original.fill(0xFFFFFFFF)
            image = capture_and_save_evidence(original, session.session_id, storage_root=tmp)
            image.zone = BoxZone.LEFT
            image.width_px = image.height_px = 12
            image.model_file = "fruit_defect.onnx"
            image.units = [DetectedUnit(1, 1, 5, 5, "fresh", 0.9)]
            record = InspectionRecord(
                session, [image], DetectionResult(1, {"fresh": 1}, 0.9, False),
                QualityAssessmentResult(AiRecommendation.NEEDS_REVIEW, [], {}),
            )
            with self.assertRaisesRegex(ValueError, "Confirm whole-box coverage"):
                self.repo.submit_for_review(record)
            with patch("agroscan.services.postgres_repository.verify_evidence_integrity", return_value=True):
                self.repo.submit_for_review(record, coverage_confirmed=True)
                self.repo.submit_for_review(record, coverage_confirmed=True)
            self.assertEqual(record.status, SessionStatus.PENDING_REVIEW)
            reloaded = next(r for r in self.repo.pending_records() if r.session_id == record.session_id)
            self.assertEqual(reloaded.evidence[0].sha256, image.sha256)
            self.assertEqual(reloaded.evidence[0].zone, BoxZone.LEFT)
            self.assertTrue(reloaded.whole_box_confirmed)
            self.assertFalse(reloaded.coverage.is_complete)
            self.assertEqual(reloaded.detection.total_objects, 1)
            with self.assertRaises(ValueError):
                self.repo.apply_review(reloaded, ReviewRecord(ReviewerDecision.PASS, maker.username, "Test"))
            self.repo.apply_review(reloaded, ReviewRecord(ReviewerDecision.PASS, reviewer.username, "Verified"))
            reread = next(r for r in self.repo.records if r.session_id == record.session_id)
            self.assertEqual(reread.status, SessionStatus.COMPLETED)
            self.assertEqual(reread.review.reviewer, reviewer.username)

    def test_signed_history_note_permissions_and_frozen_manifest(self) -> None:
        with self.isolated_writes():
            session_id = "INS--120512"
            record, = self.repo.filter_records(text=session_id, outcome="Pass")
            versions = self.repo.box_versions(record.session.box_code)
            self.assertEqual([r.version for r in versions], [1, 2])
            self.assertTrue(record.whole_box_confirmed)
            self.assertEqual(record.session.order.lot_outcome, "approve")
            self.assertEqual(record.session.order.sampling_recommendation, "reject")
            self.assertIn(record.session_id, record.session.order.signed_attempts)
            self.assertNotIn(versions[0].session_id, record.session.order.signed_attempts)
            self.assertEqual(self.repo.filter_records(text=session_id, outcome="Fail"), [])

            def signed_payload():
                with self.repo._connection() as conn, conn.cursor() as cur:
                    cur.execute("""SELECT manifest_bytes,signature FROM agroscan.latest_lot_decisions
                                   WHERE lot_id=%s""", (record.session.order.lot_id,))
                    return tuple(bytes(field) for field in cur.fetchone())

            original = signed_payload()
            reviewer = self.repo.save_user("review-" + uuid4().hex, "Reviewer", Role.REVIEWER,
                                           password="Temporary-Pass-123")
            with self.assertRaisesRegex(ValueError, "Reviewer"):
                self.repo.add_attributed_note(session_id, "demo12.admin", "Reviewer", "Unauthorized")
            self.repo.add_attributed_note(session_id, reviewer.username, reviewer.role.value, "Follow-up")
            reloaded, = self.repo.filter_records(text=session_id)
            self.assertEqual(reloaded.attributed_notes[-1].author, reviewer.username)
            self.assertEqual(reloaded.attributed_notes[-1].text, "Follow-up")
            self.assertTrue(any(e.action == "review_note_added" for e in reloaded.audit_trail))
            self.assertEqual(reloaded.assessment, record.assessment)
            self.assertEqual(reloaded.review, record.review)
            self.assertEqual(signed_payload(), original)

    def test_dashboard_counts_current_slots_only(self) -> None:
        summaries = {row.order.order_code: row for row in self.repo.sample_progress()}
        self.assertEqual(summaries["DEMO-V12-01"].sample_size, 0)
        squid = summaries["DEMO-V12-05"]
        self.assertEqual((squid.sample_size, squid.passed, squid.failed, squid.reinspect), (2, 1, 1, 0))
        self.assertEqual(squid.completion_rate, 100)

    def test_default_workstation_loads_the_new_schema(self) -> None:
        self.assertIsInstance(create_repository(AppSettings()), PostgresRepository)
        with self.isolated_writes():
            admin = self.repo.save_user(f"test-{uuid4().hex}", "Admin", Role.ADMIN, password="Temporary-Pass-123")
            auth = PostgresAuthService(self.repo)
            window = MainWindow(admin, auth_service=auth, repo=self.repo)
            try:
                window.navigate_to(PageKey.BOX_INTAKE)
                self.assertTrue(window.box_intake_page.load_code("AGS:DEMO-V12-02-04/04"))
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
