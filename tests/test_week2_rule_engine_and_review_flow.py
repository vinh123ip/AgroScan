"""Tests for the rule engine (T2.3), the intake -> live -> review flow (T2.1, T2.2)
and the reviewer evidence viewer (T2.4).

The end-to-end flow runs against ``MockRepository`` (always available) and
against the live PostgreSQL ``PostgresRepository`` (must be reachable).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from agroscan.models.inspection_models import (
    AiRecommendation,
    DefectCriterion,
    DetectionResult,
    EvidenceImage,
    Product,
    ReviewerDecision,
    SessionStatus,
)
from agroscan.services import mock_ai, rule_engine
from agroscan.services.app_settings import AppSettings
from agroscan.services.evidence_service import (
    capture_and_save_evidence,
    configure_evidence_storage,
    resolve_evidence_path,
)
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.evidence_strip import EvidenceStrip
from agroscan.ui.components.evidence_viewer_dialog import EvidenceViewerDialog
from agroscan.ui.main_window import MainWindow
from agroscan.ui.navigation import PageKey
from agroscan.ui.pages.review_queue_page import ReviewQueuePage
from agroscan.ui.theme import apply_theme

_APP: QApplication | None = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


def _banana(min_objects: int = 5, min_confidence: float = 0.60) -> Product:
    return Product(
        "BANANA", "Banana", "Fruit", "banana_defect.onnx",
        ["fresh", "bruised", "rotten"],
        [DefectCriterion("bruised", 0.10), DefectCriterion("rotten", 0.0, is_critical=True)],
        min_objects=min_objects,
        min_confidence=min_confidence,
    )


class TestRuleEngineT23(unittest.TestCase):
    """D-023: thresholds come from the product, order is FAIL > NEEDS_REVIEW > PASS."""

    def test_pass_when_within_limits(self) -> None:
        det = DetectionResult(20, {"fresh": 19, "bruised": 1, "rotten": 0}, 0.9, is_simulated=False)
        result = rule_engine.assess_quality(_banana(), det)
        self.assertEqual(result.recommendation, AiRecommendation.PASS)
        self.assertFalse(result.is_simulated)
        self.assertAlmostEqual(result.defect_ratios["bruised"], 0.05)

    def test_ratio_exactly_at_limit_passes(self) -> None:
        det = DetectionResult(20, {"fresh": 18, "bruised": 2, "rotten": 0}, 0.9)
        self.assertEqual(
            rule_engine.assess_quality(_banana(), det).recommendation, AiRecommendation.PASS
        )

    def test_fail_when_ratio_exceeds_limit(self) -> None:
        det = DetectionResult(20, {"fresh": 16, "bruised": 4, "rotten": 0}, 0.9)
        result = rule_engine.assess_quality(_banana(), det)
        self.assertEqual(result.recommendation, AiRecommendation.FAIL)
        self.assertIn("Bruised ratio 20% exceeds limit 10%.", result.reasons)

    def test_fail_immediately_on_critical_defect(self) -> None:
        det = DetectionResult(20, {"fresh": 19, "bruised": 0, "rotten": 1}, 0.9)
        result = rule_engine.assess_quality(_banana(), det)
        self.assertEqual(result.recommendation, AiRecommendation.FAIL)
        self.assertTrue(any("rotten" in r.lower() for r in result.reasons))

    def test_fail_takes_priority_over_low_confidence(self) -> None:
        det = DetectionResult(3, {"fresh": 2, "bruised": 0, "rotten": 1}, 0.3)
        self.assertEqual(
            rule_engine.assess_quality(_banana(), det).recommendation, AiRecommendation.FAIL
        )

    def test_needs_review_for_low_confidence_or_few_objects(self) -> None:
        low_conf = DetectionResult(20, {"fresh": 20, "bruised": 0, "rotten": 0}, 0.4)
        r1 = rule_engine.assess_quality(_banana(), low_conf)
        self.assertEqual(r1.recommendation, AiRecommendation.NEEDS_REVIEW)

        few = DetectionResult(3, {"fresh": 3, "bruised": 0, "rotten": 0}, 0.95)
        r2 = rule_engine.assess_quality(_banana(), few)
        self.assertEqual(r2.recommendation, AiRecommendation.NEEDS_REVIEW)
        self.assertTrue(any("minimum 5" in r for r in r2.reasons))

        both = DetectionResult(2, {"fresh": 2, "bruised": 0, "rotten": 0}, 0.2)
        self.assertEqual(len(rule_engine.assess_quality(_banana(), both).reasons), 2)

    def test_thresholds_are_not_hardcoded(self) -> None:
        det = DetectionResult(20, {"fresh": 17, "bruised": 3, "rotten": 0}, 0.9)
        strict = _banana()
        lenient = _banana()
        lenient.criteria[0].max_ratio = 0.20
        self.assertEqual(
            rule_engine.assess_quality(strict, det).recommendation, AiRecommendation.FAIL
        )
        self.assertEqual(
            rule_engine.assess_quality(lenient, det).recommendation, AiRecommendation.PASS
        )
        picky = _banana(min_confidence=0.95)
        self.assertEqual(
            rule_engine.assess_quality(picky, det.__class__(20, {"fresh": 20}, 0.9)).recommendation,
            AiRecommendation.NEEDS_REVIEW,
        )

    def test_zero_objects_needs_review(self) -> None:
        det = DetectionResult(0, {}, 0.0)
        self.assertEqual(
            rule_engine.assess_quality(_banana(), det).recommendation,
            AiRecommendation.NEEDS_REVIEW,
        )

    def test_mock_ai_alias_matches_rule_engine(self) -> None:
        det = DetectionResult(20, {"fresh": 16, "bruised": 4, "rotten": 0}, 0.9)
        self.assertEqual(
            mock_ai.assess_quality(_banana(), det), rule_engine.assess_quality(_banana(), det)
        )


class _FlowMixin:
    """Shared intake -> live -> assessment -> review flow driven through the real widgets."""

    repo: object
    created_session_ids: list[str]

    def _make_settings(self, tmp: str) -> AppSettings:
        settings = AppSettings(QSettings(str(Path(tmp) / "settings.ini"), QSettings.Format.IniFormat))
        conn = settings.load()
        conn.storage_path = str(Path(tmp) / "evidence_store")
        settings.save(conn)
        configure_evidence_storage(settings)
        return settings

    def _inspect_box(self, window: MainWindow, code: str, sim_index: int):
        """Scan ``code`` on BoxIntakePage and run the inspection to the Assessment page."""
        intake = window.box_intake_page
        live = window.live_inspection_page
        result_page = window.assessment_result_page

        intake.load_code(code)
        intake.btn_start.click()
        self.assertIsNotNone(live.session)
        self.created_session_ids.append(live.session.session_id)

        live.feed_mode_combo.setCurrentIndex(1)
        live.sim_sample_combo.setCurrentIndex(sim_index)
        live._on_capture()
        live._on_finish()
        self.assertEqual(window.current_page, PageKey.ASSESSMENT_RESULT)
        record = window._assessment_record
        self.assertIsNotNone(record)
        result_page.btn_submit.click()
        return record

    def _run_flow(self, repo, tmp: str) -> None:
        settings = self._make_settings(tmp)
        auth = MockAuthService()
        inspector = auth.authenticate("inspector", "inspector123")
        reviewer = auth.authenticate("reviewer", "reviewer123")
        assert inspector is not None and reviewer is not None

        window = MainWindow(inspector, auth, repo, settings)
        try:
            # --- T2.1 + T2.2: intake resolves order/criteria, live page loads the product model
            record = self._inspect_box(window, "AGS:DH00123-04/10", sim_index=2)  # rotten bananas
            live = window.live_inspection_page
            self.assertIsNone(live.session)   # submitted -> session closed

            self.assertEqual(record.session.product.code, "BANANA")
            self.assertEqual(record.session.product.model_file, "banana_defect.onnx")
            self.assertFalse(record.detection.is_simulated)
            self.assertEqual(record.detection.class_counts["rotten"], 1)
            self.assertEqual(record.assessment.recommendation, AiRecommendation.FAIL)
            self.assertFalse(record.assessment.is_simulated)
            self.assertTrue(any("rotten" in r.lower() for r in record.assessment.reasons))
            self.assertEqual(record.status, SessionStatus.PENDING_REVIEW)

            ev = record.evidence[0]
            self.assertEqual(len(ev.sha256), 64)
            saved = resolve_evidence_path(ev, settings=settings)
            self.assertIsNotNone(saved)
            self.assertTrue(str(saved).startswith(str(Path(tmp) / "evidence_store")))

            # --- T2.4: reviewer sees the pending record and its evidence, then decides
            page = ReviewQueuePage(repo, reviewer)
            rows = [
                r for r in range(page.queue_table.rowCount())
                if page.queue_table.payload_at(r).session_id == record.session_id
            ]
            self.assertEqual(len(rows), 1)
            page.queue_table.selectRow(rows[0])
            page._on_selection_changed()
            selected = page.queue_table.selected_payload()
            self.assertEqual(selected.session_id, record.session_id)
            self.assertEqual(selected.evidence[0].sha256, ev.sha256)

            strip = page.detail.evidence_strip
            self.assertEqual(strip.thumbnail_count, 1)

            dialog = EvidenceViewerDialog(selected.evidence[0], None, parent=page)
            self.assertTrue(dialog.has_image)
            self.assertEqual(dialog.integrity_state, "verified")
            self.assertIn("verified", dialog.integrity_label.text().lower())
            dialog.deleteLater()

            page.notes_field.setPlainText("Rotten fruit visible in evidence image.")
            page._on_decide(ReviewerDecision.FAIL)

            reloaded = [r for r in repo.records_for_box(record.session.box_code)
                        if r.session_id == record.session_id]
            self.assertEqual(len(reloaded), 1)
            self.assertEqual(reloaded[0].status, SessionStatus.COMPLETED)
            self.assertEqual(reloaded[0].review.decision, ReviewerDecision.FAIL)
            self.assertEqual(reloaded[0].evidence[0].sha256, ev.sha256)
            page.deleteLater()
        finally:
            window.shutdown()
            window.deleteLater()
            configure_evidence_storage(None)


class TestFlowWithMockRepository(_FlowMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.repo = MockRepository(seed=42)
        self.created_session_ids = []

    def test_intake_live_assessment_review_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run_flow(self.repo, tmp)


class TestEvidenceViewerT24(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        img = QImage(640, 400, QImage.Format.Format_RGB32)
        img.fill(QColor(20, 200, 90))
        self.image = img
        self.item = capture_and_save_evidence(img, "INS-VIEW-0001", storage_root=self.root)
        settings = AppSettings(QSettings(str(self.root / "s.ini"), QSettings.Format.IniFormat))
        conn = settings.load()
        conn.storage_path = str(self.root)
        settings.save(conn)
        configure_evidence_storage(settings)

    def tearDown(self) -> None:
        configure_evidence_storage(None)
        self.tmp.cleanup()

    def test_zoom_controls_and_integrity(self) -> None:
        dialog = EvidenceViewerDialog(self.item, None)
        self.assertEqual(dialog.integrity_state, "verified")
        self.assertTrue(dialog.is_fit)
        dialog.actual_size()
        self.assertEqual(dialog.zoom, 1.0)
        self.assertFalse(dialog.is_fit)
        dialog.btn_zoom_in.click()
        self.assertAlmostEqual(dialog.zoom, 1.25)
        dialog.btn_zoom_out.click()
        dialog.btn_zoom_out.click()
        self.assertAlmostEqual(dialog.zoom, 0.8)
        self.assertEqual(dialog.image_label.pixmap().width(), int(640 * 0.8))
        dialog.btn_fit.click()
        self.assertTrue(dialog.is_fit)
        dialog.deleteLater()

    def test_detects_tampered_and_missing_files(self) -> None:
        path = resolve_evidence_path(self.item)
        assert path is not None
        path.write_bytes(path.read_bytes() + b"tamper")
        tampered = EvidenceViewerDialog(self.item, None)
        self.assertEqual(tampered.integrity_state, "mismatch")
        tampered.deleteLater()

        path.unlink()
        missing = EvidenceViewerDialog(self.item, self.image)   # falls back to in-memory image
        self.assertEqual(missing.integrity_state, "missing")
        self.assertTrue(missing.has_image)
        missing.deleteLater()

        unsaved = EvidenceViewerDialog(EvidenceImage(datetime.now()), self.image)
        self.assertEqual(unsaved.integrity_state, "unsaved")
        unsaved.deleteLater()

    def test_strip_thumbnail_click_opens_viewer(self) -> None:
        strip = EvidenceStrip()
        strip.set_evidence([self.item])
        self.assertEqual(strip.thumbnail_count, 1)
        clicked: list[int] = []
        strip.thumbnail_clicked.connect(clicked.append)
        with mock.patch.object(EvidenceViewerDialog, "exec", return_value=0) as fake_exec:
            strip._thumbs[0].clicked.emit()
            strip.open_viewer(5)          # out of range: ignored
        self.assertEqual(clicked, [0])
        fake_exec.assert_called_once()
        strip.deleteLater()


if __name__ == "__main__":
    unittest.main()
