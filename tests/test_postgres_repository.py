"""Integration & unit tests for PostgreSQL database configuration and PostgresRepository (T1.2)."""

from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from agroscan.models.inspection_models import (
    AiRecommendation,
    BoxCode,
    DefectCriterion,
    DetectionResult,
    EvidenceImage,
    InspectionRecord,
    Product,
    QualityAssessmentResult,
    ReviewerDecision,
    ReviewRecord,
    SessionStatus,
)
from agroscan.models.user_models import Role
from agroscan.services import mock_ai
from agroscan.services.app_settings import AppSettings, ConnectionSettings
from agroscan.services.database import parse_env_file, resolve_db_config
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.postgres_repository import PostgresRepository
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
    """Live integration tests against local PostgreSQL 'agroscan' database."""

    def setUp(self) -> None:
        self.repo = PostgresRepository()
        ok, msg = self.repo.ping()
        if not ok:
            self.fail(f"PostgreSQL must be reachable for live repository tests: {msg}")
        self._created_session_ids: list[str] = []
        self._created_product_codes: list[str] = []

    def tearDown(self) -> None:
        with self.repo._connection() as conn:
            with conn.cursor() as cur:
                for sid in self._created_session_ids:
                    cur.execute("DELETE FROM inspection_sessions WHERE session_id = %s", (sid,))
                for code in self._created_product_codes:
                    cur.execute("DELETE FROM products WHERE code = %s", (code,))

    def test_seeded_catalog_orders_and_users(self) -> None:
        products = self.repo.products
        codes = {p.code for p in products}
        self.assertTrue({"BANANA", "APPLE", "MANGO"}.issubset(codes))

        banana = self.repo.find_product("BANANA")
        assert banana is not None
        self.assertEqual(banana.model_file, "banana_defect.onnx")
        self.assertGreaterEqual(len(banana.criteria), 2)

        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        self.assertEqual(box_code, BoxCode("DH00123", 1, 10))
        self.assertEqual(order.product.code, "BANANA")

        with self.assertRaises(ValueError):
            self.repo.resolve_box("AGS:NOPE999-01/10")

        users = {u.username: u for u in self.repo.users}
        self.assertIn("admin", users)
        self.assertEqual(users["admin"].role, Role.ADMIN)
        self.assertEqual(users["inspector"].role, Role.INSPECTOR)
        self.assertEqual(users["reviewer"].role, Role.REVIEWER)

    def test_product_crud_persists_across_instances(self) -> None:
        code = "TSTKIWI"
        self._created_product_codes.append(code)
        kiwi = Product(
            code=code,
            name="Test Kiwi",
            category="Fruit",
            model_file="kiwi_defect.onnx",
            detect_classes=["fresh", "bruised", "rotten"],
            criteria=[
                DefectCriterion("bruised", 0.15, False),
                DefectCriterion("rotten", 0.0, True),
            ],
            min_objects=4,
            min_confidence=0.65,
        )
        saved = self.repo.save_product(kiwi)
        self.assertEqual(saved.code, code)

        # Update existing
        kiwi.name = "Test Green Kiwi"
        kiwi.criteria[0].max_ratio = 0.08
        self.repo.save_product(kiwi, original_code=code)

        fresh_repo = PostgresRepository()
        reloaded = fresh_repo.find_product(code)
        assert reloaded is not None
        self.assertEqual(reloaded.name, "Test Green Kiwi")
        self.assertAlmostEqual(reloaded.criteria[0].max_ratio, 0.08)

        fresh_repo.delete_product(code)
        self.assertIsNone(fresh_repo.find_product(code))
        self._created_product_codes.remove(code)

    def test_inspection_lifecycle_persists_and_aggregates(self) -> None:
        box_code, order = self.repo.resolve_box("AGS:DH00123-02/10")
        session = self.repo.create_session(box_code, order, "inspector", "STATION-01")
        self._created_session_ids.append(session.session_id)

        detection = DetectionResult(
            total_objects=20,
            class_counts={"fresh": 17, "bruised": 3, "rotten": 0},
            mean_confidence=0.89,
            is_simulated=False,
        )
        assessment = QualityAssessmentResult(
            recommendation=AiRecommendation.FAIL,
            reasons=["Bruised ratio 15% exceeds limit 10%."],
            defect_ratios={"bruised": 0.15, "rotten": 0.0},
            is_simulated=False,
        )
        vlm = mock_ai.simulate_deep_analysis(session, detection, mock_ai.VlmScenario.NORMAL)
        evidence = [EvidenceImage(datetime.now(), False, "DH00123/box_02.jpg", "a" * 64)]

        record = InspectionRecord(session, evidence, detection, assessment, deep_analysis=vlm)
        self.repo.submit_for_review(record)
        self.assertEqual(record.status, SessionStatus.PENDING_REVIEW)

        # Reload from a brand new PostgresRepository instance (simulating app restart)
        repo2 = PostgresRepository()
        pending = [r for r in repo2.pending_records() if r.session_id == session.session_id]
        self.assertEqual(len(pending), 1)
        loaded = pending[0]
        self.assertEqual(loaded.detection.total_objects, 20)
        self.assertEqual(loaded.evidence[0].sha256, "a" * 64)
        self.assertIsNotNone(loaded.deep_analysis)

        # Reviewer applies decision
        review = ReviewRecord(ReviewerDecision.FAIL, "reviewer", "Confirmed bruised > 10%")
        repo2.apply_review(loaded, review)

        repo3 = PostgresRepository()
        completed = [r for r in repo3.records_for_box(box_code) if r.session_id == session.session_id]
        self.assertEqual(len(completed), 1)
        self.assertEqual(completed[0].status, SessionStatus.COMPLETED)
        assert completed[0].review is not None
        self.assertEqual(completed[0].review.decision, ReviewerDecision.FAIL)

        summaries = {s.order.order_code: s for s in repo3.order_summaries()}
        self.assertGreaterEqual(summaries["DH00123"].failed, 1)

        today = date.today()
        outcomes = repo3.daily_outcomes(today, today, product_code="BANANA")
        self.assertEqual(len(outcomes), 1)
        self.assertGreaterEqual(outcomes[0][2], 1)  # failed count >= 1

    def test_main_window_boots_with_postgres_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = AppSettings(QSettings(str(Path(tmp) / "s.ini"), QSettings.Format.IniFormat))
            auth = MockAuthService()
            admin = auth.authenticate("admin", "admin123")
            assert admin is not None
            win = MainWindow(admin, auth, self.repo, settings)
            self.assertIsNotNone(win.page(PageKey.DASHBOARD))
            self.assertIsNotNone(win.page(PageKey.BOX_INTAKE))
            self.assertIsNotNone(win.page(PageKey.REVIEW_QUEUE))
            self.assertIsNotNone(win.page(PageKey.CATALOG))
            win.shutdown()
            win.deleteLater()


if __name__ == "__main__":
    unittest.main()

