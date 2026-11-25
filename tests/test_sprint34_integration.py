"""Regression tests for Sprint 3.4 on the workstation."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from openpyxl import load_workbook

from agroscan.models.user_models import Role, User
from agroscan.models.vlm_models import VlmErrorCode, parse_vlm_response
from agroscan.services.app_settings import AppSettings
from agroscan.services.evidence_service import resolve_evidence_path
from agroscan.services.i18n import set_language
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
from agroscan.services.pdf_report_service import export_report_excel
from agroscan.ui.main_window import MainWindow
from agroscan.ui.navigation import PageKey
from agroscan.ui.pages.inspection_history_page import InspectionHistoryPage
from server.qwen_service import build_vlm_response


class Sprint34Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = AppSettings(Path(self.tmp.name) / "test.ini")
        config = self.settings.load()
        config.storage_path = self.tmp.name
        self.settings.save(config)
        self.repo = MockRepository()
        self.auth = MockAuthService()
        self.addCleanup(set_language, "en")

    def test_original_import_language_switch_and_submission_confirmation(self):
        user = self.auth.authenticate("inspector", "inspector123")
        window = MainWindow(user, self.auth, self.repo, self.settings)
        self.addCleanup(window.close)
        self.addCleanup(window.shutdown)
        box, order = self.repo.resolve_box("AGS:DH00124-01/08")
        window._open_session(box, order, "")
        live = window.live_inspection_page
        image = QImage(64, 64, QImage.Format.Format_RGB32)
        image.fill(0xff00aa00)
        source = Path(self.tmp.name) / "test.jpg"
        self.assertTrue(image.save(str(source), "JPEG"))
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")):
            live.btn_import.click()
        record = live.finalize()
        evidence, = record.evidence
        expected = source.read_bytes()
        self.assertEqual(resolve_evidence_path(evidence, settings=self.settings).read_bytes(), expected)
        self.assertEqual(evidence.sha256, hashlib.sha256(expected).hexdigest())
        self.assertEqual(evidence.source_kind, "imported_image")
        self.assertFalse(evidence.demo_image)
        window.language_button.click()
        self.assertEqual(self.settings.load().language, "vi")
        self.assertEqual(window.current_page, PageKey.LIVE_INSPECTION)
        self.assertEqual(live.finalize().session_id, record.session_id)
        self.assertEqual(live.finalize().evidence, [evidence])
        self.assertEqual(live.btn_import.text(), "Nhập ảnh gốc")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            self.assertFalse(window._submit_record(record))
        self.assertIsNotNone(live.session)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(window._submit_record(record))
        self.assertTrue(record.whole_box_confirmed)

    def test_reviewer_notes_and_english_export_in_vietnamese(self):
        actor = self.auth.authenticate("reviewer", "reviewer123")
        history = InspectionHistoryPage(self.repo, self.settings, current_user=actor)
        self.addCleanup(history.close)
        reviewed = next(record for record in self.repo.records if record.review)
        history.search_field.setText(reviewed.session_id)
        history.detail_widget.note_input.setText("Check with supplier")
        history.detail_widget.btn_add_note.click()
        self.assertEqual(reviewed.attributed_notes[-1].author, actor.username)
        manager = InspectionHistoryPage(self.repo, self.settings, current_user=User("m", "M", Role.MANAGER))
        self.addCleanup(manager.close)
        self.assertTrue(manager.detail_widget.audit_card.isHidden())
        self.assertTrue(manager.detail_widget.btn_add_note.isHidden())
        with self.assertRaises(ValueError):
            self.repo.add_attributed_note(reviewed.session_id, "inspector", "Reviewer", "Denied")
        set_language("vi")
        export = export_report_excel([reviewed], [], Path(self.tmp.name) / "report.xlsx")
        book = load_workbook(export, read_only=True)
        try:
            rows = list(book["Inspection Sessions"].values)
            self.assertEqual(rows[1][13], reviewed.review.decision.value)
        finally:
            book.close()

    def test_qwen_bridge_preserves_model_findings_over_http(self):
        from threading import Thread
        from agroscan.services.vlm_client import request_deep_analysis
        from server.qwen_service import create_server

        findings = {"defects": [], "observations": ["The label is obscured."],
                    "ocr": {"readable": False, "fields": [], "raw_text": ""},
                    "assessment": "Label unreadable.", "suggestion": "Retake the image.",
                    "uncertainty": {"level": "high", "score": 0.85, "reasons": ["Occlusion"]}}
        server = create_server("127.0.0.1", 0)
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join, 3)
        self.addCleanup(server.shutdown)
        cfg = self.settings.load()
        cfg.ai_url = f"http://127.0.0.1:{server.server_port}"
        record = self.repo.records[0]
        image = QImage(20, 20, QImage.Format.Format_RGB32)
        image.fill(0xff000000)
        with patch("server.qwen_service._call_lm_studio", return_value=findings):
            result = request_deep_analysis(record.session, record.detection, image, cfg, fallback_to_mock=False)
        self.assertFalse(result.is_error)
        self.assertFalse(result.ocr.readable)
        self.assertEqual(result.observations, findings["observations"])
        self.assertEqual(result.defects, [])

    def test_unavailable_vision_model_does_not_fabricate_results(self):
        import base64
        from agroscan.services.evidence_service import encode_qimage_bytes

        image = QImage(12, 12, QImage.Format.Format_RGB32)
        image.fill(0xff113355)
        encoded = base64.b64encode(encode_qimage_bytes(image)).decode()
        with patch("server.qwen_service._call_lm_studio", return_value=None):
            result = parse_vlm_response(build_vlm_response({"image_base64": encoded}))
        self.assertTrue(result.is_error)
        self.assertEqual(result.error.code, VlmErrorCode.MODEL_ERROR)
        self.assertIsNone(result.ocr)
        self.assertEqual(result.defects, [])
