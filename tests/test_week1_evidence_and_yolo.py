"""Automated test suite for Week 1 remaining tasks: T1.3, T1.4, and T1.6.

Verifies:
1. T1.6 (`evidence_service.py`):
   - Raw QImage / bytes are hashed with SHA-256 BEFORE bounding boxes are drawn.
   - Evidence files are persisted to disk without overwriting existing files (D-008).
   - `EvidenceImage.relative_path` and `EvidenceImage.sha256` are populated and verified.
2. T1.3 (`models/weights/*.onnx` & `scripts/export_yolo_onnx.py`):
   - ONNX models (`fruit_defect.onnx`, `banana_defect.onnx`, `apple_defect.onnx`) exist and
     execute on `onnxruntime.InferenceSession`.
3. T1.4 (`yolo_engine.py` & `LiveInspectionPage` integration):
   - `YoloEngine` preprocesses frames, runs ONNX Runtime inference, applies NMS and
     `CentroidTracker` (D-025), and returns `DetectionResult(is_simulated=False)`.
   - `YoloInferenceThread` (`QThread`) executes inference asynchronously in the background
     without blocking the Qt UI thread.
   - `LiveInspectionPage` captures raw evidence (matching raw SHA-256 on disk) while
     drawing bounding boxes only on the display copy.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from agroscan.models.inspection_models import AiRecommendation
from agroscan.services.app_settings import AppSettings
from agroscan.services.evidence_service import (
    capture_and_save_evidence,
    compute_sha256,
    encode_qimage_bytes,
    load_evidence_qimage,
    resolve_evidence_path,
    verify_evidence_integrity,
)
from agroscan.services.mock_repository import MockRepository
from agroscan.services.yolo_engine import (
    YoloEngine,
    YoloInferenceOutput,
    YoloInferenceThread,
    draw_detections_on_qimage,
    resolve_model_path,
)
from agroscan.ui.pages.live_inspection_page import LiveInspectionPage
from agroscan.ui.theme import apply_theme
from scripts.export_yolo_onnx import export_baseline_models

_APP: QApplication | None = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)
    # Ensure ONNX model files exist before running tests
    if resolve_model_path("fruit_defect.onnx") is None:
        export_baseline_models()


class TestEvidenceServiceT16(unittest.TestCase):
    """Verify T1.6: Evidence capture, disk persistence, and pre-overlay SHA-256 hashing."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.storage_dir = Path(self.tmp.name) / "captures"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_capture_saves_raw_bytes_and_computes_exact_sha256(self) -> None:
        raw_img = QImage(320, 240, QImage.Format.Format_RGB32)
        raw_img.fill(QColor(24, 140, 80))

        expected_bytes = encode_qimage_bytes(raw_img)
        expected_sha256 = compute_sha256(expected_bytes)
        self.assertEqual(len(expected_sha256), 64)

        item = capture_and_save_evidence(
            raw_image=raw_img,
            session_id="INS-20261114-0001",
            sequence=1,
            is_auto_capture=False,
            storage_root=self.storage_dir,
        )

        self.assertEqual(item.sha256, expected_sha256)
        self.assertTrue(item.relative_path.endswith(".png"))
        self.assertNotIn("\\", item.relative_path)

        saved_path = resolve_evidence_path(item, storage_root=self.storage_dir)
        self.assertIsNotNone(saved_path)
        self.assertTrue(saved_path.is_file())
        self.assertEqual(saved_path.read_bytes(), expected_bytes)
        self.assertTrue(verify_evidence_integrity(item, storage_root=self.storage_dir))

        reloaded = load_evidence_qimage(item, storage_root=self.storage_dir)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.size(), raw_img.size())

    def test_never_overwrites_existing_evidence_files_d008(self) -> None:
        from datetime import datetime

        fixed_ts = datetime(2026, 11, 14, 10, 30, 0)
        raw_img = QImage(120, 90, QImage.Format.Format_RGB32)
        raw_img.fill(QColor(100, 120, 140))

        first = capture_and_save_evidence(
            raw_image=raw_img,
            session_id="INS-20261114-0099",
            sequence=1,
            captured_at=fixed_ts,
            storage_root=self.storage_dir,
        )
        second = capture_and_save_evidence(
            raw_image=raw_img,
            session_id="INS-20261114-0099",
            sequence=1,
            captured_at=fixed_ts,
            storage_root=self.storage_dir,
        )

        self.assertNotEqual(first.relative_path, second.relative_path)
        self.assertTrue(verify_evidence_integrity(first, storage_root=self.storage_dir))
        self.assertTrue(verify_evidence_integrity(second, storage_root=self.storage_dir))


class TestYoloEngineAndLiveIntegrationT13T14(unittest.TestCase):
    """Verify T1.3 & T1.4: YOLOv8 ONNX model, QThread worker, and LiveInspectionPage."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        ini_path = Path(self.tmp.name) / "settings.ini"
        store = QSettings(str(ini_path), QSettings.Format.IniFormat)
        self.settings = AppSettings(store)
        conn = self.settings.load()
        conn.storage_path = str(Path(self.tmp.name) / "evidence_store")
        self.settings.save(conn)

        self.repo = MockRepository(seed=42)
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        self.session = self.repo.create_session(box_code, order, "inspector", "STATION-01")
        self.page = LiveInspectionPage(self.settings)
        self.page.start_session(self.session)

    def tearDown(self) -> None:
        self.page.clear_session()
        self.page.deleteLater()
        self.tmp.cleanup()

    def test_onnx_models_exist_and_classify_fresh_bruised_rotten(self) -> None:
        for fname in ("fruit_defect.onnx", "banana_defect.onnx", "apple_defect.onnx"):
            path = resolve_model_path(fname)
            self.assertIsNotNone(path, f"Missing ONNX model: {fname}")
            self.assertTrue(path.is_file())

        engine = YoloEngine()
        self.assertTrue(engine.load_for_product(self.session.product))
        self.assertTrue(engine.is_loaded)

        # 1. Fresh crate frame -> 19 fresh, 1 bruised
        raw_fresh = self.page._render_raw_sim_image("fresh")
        out_fresh = engine.infer(raw_fresh, track=True)
        self.assertFalse(out_fresh.detection.is_simulated)
        self.assertEqual(out_fresh.detection.total_objects, 20)
        self.assertEqual(
            out_fresh.detection.class_counts,
            {"fresh": 19, "bruised": 1, "rotten": 0},
        )
        self.assertGreaterEqual(out_fresh.detection.mean_confidence, 0.85)
        self.assertTrue(all(b.track_id is not None for b in out_fresh.boxes))

        # 2. Bruised crate frame -> 16 fresh, 4 bruised
        raw_bruised = self.page._render_raw_sim_image("bruised")
        out_bruised = engine.infer(raw_bruised, track=True)
        self.assertEqual(out_bruised.detection.total_objects, 20)
        self.assertEqual(
            out_bruised.detection.class_counts,
            {"fresh": 16, "bruised": 4, "rotten": 0},
        )

        # 3. Rotten crate frame -> 17 fresh, 2 bruised, 1 rotten
        raw_rotten = self.page._render_raw_sim_image("rotten")
        out_rotten = engine.infer(raw_rotten, track=True)
        self.assertEqual(out_rotten.detection.total_objects, 20)
        self.assertEqual(
            out_rotten.detection.class_counts,
            {"fresh": 17, "bruised": 2, "rotten": 1},
        )

    def test_qthread_worker_runs_asynchronously_without_blocking(self) -> None:
        engine = YoloEngine("fruit_defect.onnx")
        worker = YoloInferenceThread(engine)
        received: list[YoloInferenceOutput] = []
        worker.inference_ready.connect(lambda out: received.append(out))

        raw_frame = self.page._render_raw_sim_image("rotten")
        worker.submit_frame(raw_frame, track=True, request_id=7)

        deadline = time.perf_counter() + 3.0
        while not received and time.perf_counter() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.02)

        worker.stop_worker()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].request_id, 7)
        self.assertEqual(received[0].detection.total_objects, 20)
        self.assertEqual(received[0].detection.class_counts["rotten"], 1)

    def test_live_inspection_capture_hashes_raw_image_before_drawing_boxes(self) -> None:
        self.page.feed_mode_combo.setCurrentIndex(1)  # Simulation Feed
        self.page.sim_sample_combo.setCurrentIndex(0)  # Fresh Bananas

        raw_before = self.page._current_raw_sim_image
        self.assertIsNotNone(raw_before)
        raw_sha256 = compute_sha256(encode_qimage_bytes(raw_before))

        self.page._on_capture()
        record = self.page.finalize()
        self.assertIsNotNone(record)
        self.assertEqual(len(record.evidence), 1)

        ev = record.evidence[0]
        # Saved evidence SHA-256 must match the UNANNOTATED raw frame bytes
        self.assertEqual(ev.sha256, raw_sha256)
        self.assertTrue(verify_evidence_integrity(ev, settings=self.settings))

        # Meanwhile, the UI thumbnail image has bounding boxes drawn on it, so its bytes differ
        ui_display_img = self.page.captured_images[0]
        ui_sha256 = compute_sha256(encode_qimage_bytes(ui_display_img))
        self.assertNotEqual(ui_sha256, raw_sha256)

        # And the detection comes from real ONNX inference (`is_simulated=False`)
        self.assertFalse(record.detection.is_simulated)
        self.assertEqual(record.assessment.recommendation, AiRecommendation.PASS)


if __name__ == "__main__":
    unittest.main()

