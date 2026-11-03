"""Automated verification suite for Sprint 2 task 3.2.4.2.

Covers all five checklist items:
1. Login wireframe, role badges, RBAC sidebar visibility, and logout state.
2. Goods Category & Criteria Editor (CatalogPage + validation + rule engine).
3. QR Scanner, manual order lookup, re-inspection notice, and continuous scan.
4. VLM Result Panel (defects, label OCR + mismatch flag, uncertainty, error states).
5. VLM JSON Schema contract (docs/api/vlm_analysis.schema.json <-> vlm_models.py).

Run with:
    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m unittest discover -s tests -v
"""

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from agroscan.models.inspection_models import (  # noqa: E402
    AiRecommendation,
    BoxCode,
    DefectCriterion,
    DetectionResult,
    Product,
)
from agroscan.models.user_models import Role  # noqa: E402
from agroscan.models.vlm_models import (  # noqa: E402
    VLM_JSON_SCHEMA,
    VlmErrorCode,
    VlmSchemaError,
    VlmStatus,
    parse_vlm_response,
)
from agroscan.services import mock_ai  # noqa: E402
from agroscan.services.app_settings import AppSettings  # noqa: E402
from agroscan.services.catalog_validation import validate_product  # noqa: E402
from agroscan.services.mock_auth import MockAuthService  # noqa: E402
from agroscan.services.mock_repository import MockRepository  # noqa: E402
from agroscan.ui.components.record_detail import RecordDetailWidget  # noqa: E402
from agroscan.ui.components.vlm_result_panel import VlmResultPanel  # noqa: E402
from agroscan.ui.main_window import MainWindow  # noqa: E402
from agroscan.ui.navigation import PageKey  # noqa: E402
from agroscan.ui.pages.catalog_page import CatalogPage  # noqa: E402
from agroscan.ui.pages.login_dialog import LoginDialog  # noqa: E402
from agroscan.ui.theme import apply_theme  # noqa: E402


_APP: QApplication | None = None


def setUpModule() -> None:  # noqa: N802 — unittest hook
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


class TestChecklist1LoginAndSessionState(unittest.TestCase):
    """Checklist #1: Login wireframe and login/logout states."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.settings = AppSettings(store)
        self.auth = MockAuthService()
        self.repo = MockRepository(seed=7)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_login_dialog_validation_and_quick_demo_roles(self) -> None:
        dialog = LoginDialog(self.auth, self.settings)
        dialog.username.setText("admin")
        dialog.password.setText("wrong-pass")
        dialog._on_sign_in()
        self.assertIsNone(dialog.user)
        self.assertFalse(dialog.error_label.isHidden())

        dialog._quick_sign_in("inspector", "inspector123")
        self.assertIsNotNone(dialog.user)
        self.assertEqual(dialog.user.role, Role.INSPECTOR)
        dialog.deleteLater()

    def test_role_visibility_and_logout_guard(self) -> None:
        admin = self.auth.authenticate("admin", "admin123")
        inspector = self.auth.authenticate("inspector", "inspector123")
        reviewer = self.auth.authenticate("reviewer", "reviewer123")
        assert admin and inspector and reviewer

        admin_win = MainWindow(admin, self.auth, self.repo, self.settings)
        self.assertIsNotNone(admin_win.page(PageKey.CATALOG))
        self.assertIsInstance(admin_win.page(PageKey.CATALOG), CatalogPage)
        self.assertEqual(admin_win.role_badge.property("role"), "admin")
        admin_win.shutdown()
        admin_win.deleteLater()

        insp_win = MainWindow(inspector, self.auth, self.repo, self.settings)
        self.assertIsNone(insp_win.page(PageKey.CATALOG))
        self.assertIsNotNone(insp_win.page(PageKey.BOX_INTAKE))
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        insp_win._open_session(box_code, order, "test note")
        logged_out = []
        insp_win.logout_requested.connect(lambda: logged_out.append(True))
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            insp_win._on_logout_clicked()
        self.assertEqual(logged_out, [])
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            insp_win._on_logout_clicked()
        self.assertEqual(logged_out, [True])
        insp_win.deleteLater()

        rev_win = MainWindow(reviewer, self.auth, self.repo, self.settings)
        self.assertIsNone(rev_win.page(PageKey.CATALOG))
        self.assertIsNone(rev_win.page(PageKey.BOX_INTAKE))
        self.assertIsNotNone(rev_win.page(PageKey.REVIEW_QUEUE))
        rev_win.shutdown()
        rev_win.deleteLater()


class TestChecklist2CatalogAndCriteriaEditor(unittest.TestCase):
    """Checklist #2: Goods Category & Criteria Editor."""

    def setUp(self) -> None:
        self.repo = MockRepository(seed=11)
        self.page = CatalogPage(self.repo)

    def tearDown(self) -> None:
        self.page.deleteLater()

    def test_edit_existing_product_criteria_updates_rule_engine(self) -> None:
        self.assertEqual(self.page.product_table.rowCount(), 3)
        self.assertEqual(self.page.code_field.text(), "BANANA")
        self.assertTrue(self.page.code_field.isReadOnly())

        spin = self.page.criteria_table.cellWidget(0, CatalogPage._COL_RATIO)
        spin.setValue(5.0)
        self.assertTrue(self.page.is_dirty)
        self.page._on_save()
        self.assertFalse(self.page.is_dirty)
        self.assertTrue(self.page.error_label.isHidden())

        banana = self.repo.find_product("BANANA")
        assert banana is not None
        self.assertAlmostEqual(
            self.repo.orders["DH00123"].product.criteria[0].max_ratio, 0.05
        )
        detection = DetectionResult(
            total_objects=20,
            class_counts={"fresh": 18, "bruised": 2, "rotten": 0},  # 10% bruised
            mean_confidence=0.90,
        )
        assessment = mock_ai.assess_quality(banana, detection)
        self.assertEqual(assessment.recommendation, AiRecommendation.FAIL)

    def test_create_new_product_category_filter_and_delete_protection(self) -> None:
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.page._on_delete()
        self.assertFalse(self.page.error_label.isHidden())
        self.assertIsNotNone(self.repo.find_product("BANANA"))

        self.page._on_new()
        self.assertFalse(self.page.code_field.isReadOnly())
        self.page.code_field.setText("potato")
        self.page.name_field.setText("Potato")
        self.page.category_field.setEditText("Root Vegetable")
        self.page.model_field.setText("potato_defect.onnx")
        self.page.classes_field.setText("fresh, sprouted, rotten")
        self.page._add_criterion_row(DefectCriterion("sprouted", 0.08, False))
        self.page._add_criterion_row(DefectCriterion("rotten", 0.0, True))
        self.page._on_save()

        self.assertTrue(self.page.error_label.isHidden())
        self.assertIn("Root Vegetable", self.repo.categories())
        potato = self.repo.find_product("POTATO")
        self.assertIsNotNone(potato)

        idx = self.page.category_filter.findText("Root Vegetable")
        self.assertGreaterEqual(idx, 0)
        self.page.category_filter.setCurrentIndex(idx)
        self.assertEqual(self.page.product_table.rowCount(), 1)

        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.page._on_delete()
        self.assertIsNone(self.repo.find_product("POTATO"))

    def test_validation_rejects_invalid_product(self) -> None:
        bad = Product(
            code="1bad",
            name="",
            category="",
            model_file="folder/model.txt",
            detect_classes=["fresh"],
            criteria=[DefectCriterion("fresh", 1.5)],
            min_objects=0,
            min_confidence=1.5,
        )
        errors = validate_product(bad, existing_codes=["BANANA"])
        self.assertGreaterEqual(len(errors), 5)


class TestChecklist3QrScannerAndOrderLookup(unittest.TestCase):
    """Checklist #3: QR Scanner and Order Lookup."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.settings = AppSettings(store)
        self.auth = MockAuthService()
        self.repo = MockRepository(seed=19)
        admin = self.auth.authenticate("admin", "admin123")
        assert admin is not None
        self.win = MainWindow(admin, self.auth, self.repo, self.settings)

    def tearDown(self) -> None:
        self.win.shutdown()
        self.win.deleteLater()
        self.tmp.cleanup()

    def test_qr_scan_manual_lookup_and_continuous_next_box(self) -> None:
        intake = self.win.box_intake_page
        assert intake is not None

        self.assertFalse(intake.load_code("INVALID-CODE"))
        self.assertFalse(intake.error_label.isHidden())

        self.assertTrue(intake.load_code("AGS:DH00121-01/10"))
        self.assertFalse(intake.reinspect_label.isHidden())

        intake.order_combo.setCurrentIndex(3)  # DH00124
        intake.box_spin.setValue(2)
        intake._on_lookup()
        self.assertEqual(intake.scan_field.text(), "AGS:DH00124-02/08")
        intake._on_start()

        live = self.win.live_inspection_page
        assert live is not None
        self.assertEqual(live.session.box_code, BoxCode("DH00124", 2, 8))

        live._on_image_captured(1, QImage(64, 64, QImage.Format.Format_RGB32))
        live.next_scan_field.setText("AGS:DH00124-03/08")
        live._on_next_scanned()
        self.assertEqual(live.session.box_code, BoxCode("DH00124", 3, 8))
        self.assertEqual(len(self.repo.records_for_box(BoxCode("DH00124", 2, 8))), 1)


class TestChecklist4And5VlmSchemaAndResultPanel(unittest.TestCase):
    """Checklist #4 & #5: VLM JSON Schema contract and VLM Result Panel states."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = AppSettings(Path(self.tmp.name) / "settings.ini")
        self.repo = MockRepository(seed=23)
        box_code, order = self.repo.resolve_box("AGS:DH00123-07/10")
        self.session = self.repo.create_session(box_code, order, "inspector", "STATION-01")
        self.detection = DetectionResult(
            total_objects=22,
            class_counts={"fresh": 18, "bruised": 3, "rotten": 1},
            mean_confidence=0.52,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_published_json_schema_matches_vlm_models(self) -> None:
        schema_path = ROOT_DIR / "docs" / "api" / "vlm_analysis.schema.json"
        self.assertTrue(schema_path.is_file(), "docs/api/vlm_analysis.schema.json is missing")
        on_disk = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, VLM_JSON_SCHEMA)

    def test_schema_validation_accepts_valid_and_rejects_invalid_payloads(self) -> None:
        analysis = mock_ai.simulate_deep_analysis(
            self.session, self.detection, mock_ai.VlmScenario.NORMAL
        )
        round_trip = parse_vlm_response(json.dumps(analysis.to_dict()))
        self.assertEqual(round_trip.status, VlmStatus.OK)
        self.assertEqual(len(round_trip.defects), 2)
        self.assertTrue(round_trip.ocr and round_trip.ocr.readable)

        bad_version = analysis.to_dict()
        bad_version["schema_version"] = "2.0"
        with self.assertRaises(VlmSchemaError):
            parse_vlm_response(bad_version)

        extra_key = analysis.to_dict()
        extra_key["unexpected"] = 123
        with self.assertRaises(VlmSchemaError):
            parse_vlm_response(extra_key)

        missing_uncertainty = analysis.to_dict()
        missing_uncertainty["uncertainty"] = None
        with self.assertRaises(VlmSchemaError):
            parse_vlm_response(missing_uncertainty)

        missing_error = analysis.to_dict()
        missing_error["status"] = "error"
        with self.assertRaises(VlmSchemaError):
            parse_vlm_response(missing_error)

    def test_vlm_result_panel_all_states_and_record_detail_integration(self) -> None:
        panel = VlmResultPanel()
        self.assertEqual(panel.state, "idle")
        self.assertFalse(panel.idle_label.isHidden())

        panel.set_loading()
        self.assertEqual(panel.state, "loading")
        self.assertFalse(panel.loading_box.isHidden())

        ok_analysis = mock_ai.simulate_deep_analysis(
            self.session, self.detection, mock_ai.VlmScenario.NORMAL, rng=random.Random(1)
        )
        assert ok_analysis.ocr is not None and ok_analysis.uncertainty is not None
        ok_analysis.ocr.fields[1].value = "Different Packer Co."
        panel.set_analysis(ok_analysis, {
            "box_code": self.session.box_code.text,
            "supplier": self.session.order.supplier,
        })
        self.assertEqual(panel.state, "result")
        self.assertTrue(panel.ocr_note.isHidden())
        self.assertGreater(panel.defect_grid.count(), 4)
        self.assertIn(
            ok_analysis.uncertainty.level.value,
            panel.uncertainty_badge.text().lower(),
        )

        partial = mock_ai.simulate_deep_analysis(
            self.session, self.detection, mock_ai.VlmScenario.LABEL_UNREADABLE
        )
        panel.set_analysis(partial)
        self.assertEqual(panel.state, "result")
        self.assertEqual(panel.status_badge.property("tone"), "warning")
        self.assertFalse(panel.ocr_note.isHidden())
        self.assertFalse(panel.warnings_label.isHidden())

        for scenario, expected_code, retryable in (
            (mock_ai.VlmScenario.IMAGE_UNUSABLE,      VlmErrorCode.IMAGE_UNUSABLE,      False),
            (mock_ai.VlmScenario.TIMEOUT,             VlmErrorCode.TIMEOUT,             True),
            (mock_ai.VlmScenario.SERVICE_UNAVAILABLE, VlmErrorCode.SERVICE_UNAVAILABLE, True),
            (mock_ai.VlmScenario.INVALID_RESPONSE,    VlmErrorCode.INVALID_RESPONSE,    True),
        ):
            err = mock_ai.simulate_deep_analysis(self.session, self.detection, scenario)
            self.assertTrue(err.is_error)
            assert err.error is not None
            self.assertEqual(err.error.code, expected_code)
            panel.set_analysis(err)
            self.assertEqual(panel.state, "error")
            self.assertEqual(not panel.btn_retry.isHidden(), retryable)

        detail = RecordDetailWidget()
        pending = self.repo.pending_records()
        self.assertGreaterEqual(len(pending), 1)
        detail.set_record(pending[0])
        self.assertFalse(detail.deep_card.isHidden())
        self.assertEqual(detail.vlm_panel.state, "result")

        panel.deleteLater()
        detail.deleteLater()

    def test_live_inspection_deep_analysis_cancel_and_error_isolation(self) -> None:
        store = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)
        settings = AppSettings(store)
        auth = MockAuthService()
        admin = auth.authenticate("admin", "admin123")
        assert admin is not None
        win = MainWindow(admin, auth, self.repo, settings)
        live = win.live_inspection_page
        assert live is not None

        box_code, order = self.repo.resolve_box("AGS:DH00124-01/08")
        win._open_session(box_code, order, "")
        live._on_image_captured(1, QImage(64, 64, QImage.Format.Format_RGB32))

        # Start deep analysis -> loading -> cancel ignores late timer callback
        live._on_deep_analysis()
        self.assertEqual(live.vlm_panel.state, "loading")
        stale_token = live._analysis_token
        live._on_cancel_deep_analysis()
        self.assertEqual(live.vlm_panel.state, "idle")
        live._on_deep_analysis_done(stale_token)
        self.assertEqual(live.vlm_panel.state, "idle")

        # Simulated TIMEOUT error shows error state in panel without polluting record
        idx = live.scenario_combo.findData(mock_ai.VlmScenario.TIMEOUT)
        live.scenario_combo.setCurrentIndex(idx)
        live._on_deep_analysis()
        live._on_deep_analysis_done(live._analysis_token)
        self.assertEqual(live.vlm_panel.state, "error")
        record = live.finalize()
        assert record is not None
        self.assertIsNone(record.deep_analysis)

        # Normal scenario stores validated VlmAnalysis on record
        idx_ok = live.scenario_combo.findData(mock_ai.VlmScenario.NORMAL)
        live.scenario_combo.setCurrentIndex(idx_ok)
        live._on_deep_analysis()
        live._on_deep_analysis_done(live._analysis_token)
        self.assertEqual(live.vlm_panel.state, "result")
        record_ok = live.finalize()
        assert record_ok is not None and record_ok.deep_analysis is not None
        self.assertEqual(record_ok.deep_analysis.status, VlmStatus.OK)

        win.shutdown()
        win.deleteLater()


if __name__ == "__main__":
    unittest.main()
