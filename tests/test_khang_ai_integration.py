"""Integration & regression tests for Khang's local ONNX models, UI safety, HTTP VLM bridge, and multi-product specs."""

from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import numpy as np
from PIL import Image
from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QFileDialog

from agroscan.models.inspection_models import (
    AiRecommendation,
    BoxCode,
    BoxZone,
    DefectCriterion,
    DetectionResult,
    Order,
    Product,
)
from agroscan.models.vlm_models import VlmErrorCode, VlmStatus, parse_vlm_response
from agroscan.services import rule_engine
from agroscan.services import yolo_engine as yolo_mod
from agroscan.services.app_settings import AppSettings
from agroscan.services.container_classifier import ContainerCheckResult
from agroscan.services.evidence_service import compute_sha256, encode_qimage_bytes, resolve_evidence_path
from agroscan.services.khang_ai_adapter import (
    KhangAiAdapter,
    MANIFEST_SCHEMA_V2,
    load_apple_detector_preset,
    load_khang_manifest,
    load_product_detector_preset,
)
from agroscan.services.mock_repository import MockRepository
from agroscan.services.vlm_client import request_deep_analysis
from agroscan.services.yolo_engine import (
    BoundingBox,
    YoloEngine,
    YoloInferenceOutput,
    YoloInferenceThread,
    draw_detections_on_qimage,
)
from agroscan.ui.pages.live_inspection_page import LiveInspectionPage
from agroscan.ui.theme import apply_theme
import server.qwen_service as qwen_srv
from server.qwen_service import (
    _assert_loopback_http,
    _call_llama_br14,
    _call_lm_studio,
    _detect_image_mime,
    build_vlm_response,
    create_server,
    map_br14_to_vlm_findings,
)

WORKSPACE_VAL_DIR = Path(__file__).resolve().parents[3] / "data" / "development" / "apple-box-v2" / "val" / "images"
_KHANG_BUNDLE_READY = KhangAiAdapter().is_available()

_APP: QApplication | None = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


def _make_stub_output(
    count: int,
    *,
    request_id: int = 0,
    label: str = "fresh",
    count_only: bool = False,
) -> YoloInferenceOutput:
    return YoloInferenceOutput(
        boxes=[
            BoundingBox(
                x1=2 + (i % 10) * 12,
                y1=4 + (i // 10) * 14,
                x2=10 + (i % 10) * 12,
                y2=16 + (i // 10) * 14,
                label=label,
                confidence=0.9,
            )
            for i in range(count)
        ],
        detection=DetectionResult(
            total_objects=count,
            class_counts={label: count} if count else {label: 0},
            mean_confidence=0.9 if count else 0.0,
            is_simulated=False,
            defect_classification_available=not count_only,
        ),
        inference_ms=1.5,
        model_path="stub.onnx",
        request_id=request_id,
    )


class TestKhangOnnxAndBugFixes(unittest.TestCase):
    """Verify ONNX manifest/SHA checks, YoloEngine safety, worker lifecycle, and adapter contracts."""

    @unittest.skipUnless(_KHANG_BUNDLE_READY, "Optional Khang ONNX bundle not installed")
    def test_load_khang_manifest_and_presets_with_dynamic_sizes(self) -> None:
        manifest, base_dir = load_khang_manifest()
        self.assertEqual(manifest["product"], "apple")
        self.assertIn("open_box", manifest["detectors"])
        self.assertIn("tray", manifest["detectors"])

        engine = YoloEngine()
        meta_open = load_apple_detector_preset(engine, "open_box")
        self.assertEqual(engine.input_size, (1280, 1280))
        self.assertEqual(engine.class_names, ["apple"])
        self.assertTrue((base_dir / meta_open["model_file"]).is_file())

        meta_tray = load_apple_detector_preset(engine, "tray")
        self.assertEqual(engine.input_size, (960, 960))
        self.assertEqual(meta_tray["image_size"], 960)

    @unittest.skipUnless(_KHANG_BUNDLE_READY, "Optional Khang ONNX bundle not installed")
    def test_tampered_manifest_sha256_is_rejected(self) -> None:
        manifest, base_dir = load_khang_manifest()
        tampered = json.loads(json.dumps(manifest))
        tampered["detectors"]["open_box"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            fake_onnx = Path(tmp) / "fake.onnx"
            fake_onnx.write_bytes(b"not-a-real-onnx")
            tampered["detectors"]["open_box"]["model_file"] = "fake.onnx"
            tampered_manifest = Path(tmp) / "manifest.json"
            tampered_manifest.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_apple_detector_preset(YoloEngine(), "open_box", manifest_path=tampered_manifest)

        self.assertTrue((base_dir / manifest["classifier"]["model_file"]).is_file())

    def test_yolo_engine_load_model_is_atomic_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid_onnx = root / "valid.onnx"
            valid_onnx.write_bytes(b"valid-onnx")
            missing_abs = root / "does_not_exist_12345.onnx"
            corrupt_abs = root / "corrupt.onnx"
            corrupt_abs.write_bytes(b"not-valid-onnx")

            valid_sess = Mock()
            valid_sess.get_inputs.return_value = [SimpleNamespace(name="images", shape=[1, 3, 640, 640])]
            valid_sess.get_outputs.return_value = [SimpleNamespace(name="output0", shape=[1, 7, 8400])]

            def _fake_session(path_str: str, **_kwargs):
                if Path(path_str) == valid_onnx:
                    return valid_sess
                raise RuntimeError("corrupt onnx")

            engine = YoloEngine()
            with patch.object(yolo_mod.ort, "InferenceSession", side_effect=_fake_session):
                self.assertTrue(engine.load_model(valid_onnx, class_names=["fresh", "bruised", "rotten"]))
                prior_path = engine.model_path
                self.assertFalse(engine.load_model(missing_abs, class_names=["broken"]))
                self.assertFalse(engine.load_model(corrupt_abs, class_names=["broken2"]))

            self.assertTrue(engine.is_loaded)
            self.assertEqual(engine.model_path, prior_path)
            self.assertEqual(engine.class_names, ["fresh", "bruised", "rotten"])

    def test_resolve_model_path_requested_beats_generic_fallback_across_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            early = root / "early"
            later = root / "later"
            early.mkdir()
            later.mkdir()
            (early / "fruit_defect.onnx").write_bytes(b"generic")
            requested = later / "apple_defect.onnx"
            requested.write_bytes(b"specific")

            with (
                patch.object(yolo_mod, "DEFAULT_WEIGHTS_DIR", root / "absent1"),
                patch.object(yolo_mod, "FALLBACK_WEIGHTS_DIR", root / "absent2"),
                patch.object(yolo_mod, "REPO_ROOT", root / "absent3"),
            ):
                self.assertEqual(yolo_mod.resolve_model_path("apple_defect.onnx", [early, later]), requested)
                self.assertEqual(
                    yolo_mod.resolve_model_path("missing_specific.onnx", [early, later]),
                    early / "fruit_defect.onnx",
                )
                self.assertIsNone(yolo_mod.resolve_model_path(str(root / "missing_abs.onnx"), [early]))

    def test_load_model_validates_output_class_dim_and_capability(self) -> None:
        def _fake_session_factory(out_shape: list, in_shape: list = [1, 3, 640, 640]):
            sess = Mock()
            sess.get_inputs.return_value = [SimpleNamespace(name="images", shape=in_shape)]
            sess.get_outputs.return_value = [SimpleNamespace(name="output0", shape=out_shape)]
            return sess

        with tempfile.TemporaryDirectory() as tmp:
            fake_onnx = Path(tmp) / "dummy.onnx"
            fake_onnx.write_bytes(b"placeholder")
            engine = YoloEngine()

            # Class count mismatch fails cleanly
            with patch.object(yolo_mod.ort, "InferenceSession", return_value=_fake_session_factory([1, 5, 8400])):
                self.assertFalse(engine.load_model(fake_onnx, class_names=["fresh", "bruised", "rotten"]))

            # Species-only 3-class detector must NOT advertise defect classification
            with patch.object(yolo_mod.ort, "InferenceSession", return_value=_fake_session_factory([1, 7, 8400])):
                self.assertTrue(engine.load_model(fake_onnx, class_names=["apple", "orange", "banana"]))
            raw_species = np.zeros((1, 7, 1), dtype=np.float32)
            raw_species[0, :4, 0] = [50, 50, 20, 20]
            raw_species[0, 5, 0] = 0.9
            _boxes, det_species = engine.postprocess(raw_species, 100, 100, 1.0, 0, 0, track=False)
            self.assertFalse(det_species.defect_classification_available)
            self.assertEqual(det_species.total_objects, 1)

            # Defect 3-class model advertises defect classification
            with patch.object(yolo_mod.ort, "InferenceSession", return_value=_fake_session_factory([1, 7, 8400])):
                self.assertTrue(engine.load_model(fake_onnx, class_names=["fresh", "bruised", "rotten"]))
            _boxes2, det_defect = engine.postprocess(raw_species, 100, 100, 1.0, 0, 0, track=False)
            self.assertTrue(det_defect.defect_classification_available)

            # Runtime shape mismatch raises loudly instead of mislabeling
            with self.assertRaises(ValueError):
                engine.postprocess(np.zeros((1, 8, 2), dtype=np.float32), 100, 100, 1.0, 0, 0, track=False)

    def test_postprocess_clips_out_of_image_and_zero_area_boxes_before_nms(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_onnx = Path(tmp) / "clip.onnx"
            fake_onnx.write_bytes(b"placeholder")
            sess = Mock()
            sess.get_inputs.return_value = [SimpleNamespace(name="images", shape=[1, 3, 640, 640])]
            sess.get_outputs.return_value = [SimpleNamespace(name="output0", shape=[1, 7, "anchors"])]
            engine = YoloEngine(conf_threshold=0.45)
            with patch.object(yolo_mod.ort, "InferenceSession", return_value=sess):
                self.assertTrue(engine.load_model(fake_onnx, class_names=["fresh", "bruised", "rotten"]))

            # Cols: completely left, right edge collapse, clipped on left boundary, covers full frame, zero size
            raw = np.zeros((1, 7, 5), dtype=np.float32)
            preds = [
                (-10, 50, 10, 20),   # outside left
                (110, 50, 10, 20),   # outside right
                (0, 50, 20, 20),     # clips to (0, 40, 10, 60)
                (50, 50, 200, 200),  # clips to (0, 0, 100, 100)
                (25, 25, 0, 10),     # zero width
            ]
            for idx, (cx, cy, bw, bh) in enumerate(preds):
                raw[0, 0, idx] = cx
                raw[0, 1, idx] = cy
                raw[0, 2, idx] = bw
                raw[0, 3, idx] = bh
                raw[0, 4, idx] = 0.9

            seen_candidates: list[BoundingBox] = []
            orig_nms = yolo_mod.non_max_suppression

            def _spy_nms(cands, iou_threshold=0.4):
                seen_candidates.extend(cands)
                return orig_nms(cands, iou_threshold=iou_threshold)

            with patch.object(yolo_mod, "non_max_suppression", side_effect=_spy_nms):
                boxes, det = engine.postprocess(raw, orig_w=100, orig_h=100, scale=1.0, pad_x=0, pad_y=0, track=False)

            self.assertEqual(len(seen_candidates), 2)
            self.assertTrue(all(0 <= b.x1 < b.x2 <= 100 and 0 <= b.y1 < b.y2 <= 100 for b in seen_candidates))
            self.assertEqual(det.total_objects, len(boxes))

    def test_yolo_worker_idle_restart_reusable_and_permanent_stop(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        seen: list[int] = []
        ready_ev = threading.Event()

        class _SlowEngine:
            def __init__(self) -> None:
                self.block_first = False

            def infer(self, frame, track=True, request_id=0):
                if request_id == 10 and self.block_first:
                    entered.set()
                    release.wait(5)
                return _make_stub_output(1, request_id=request_id)

        eng = _SlowEngine()
        worker = YoloInferenceThread(eng)
        worker.inference_ready.connect(
            lambda res: (seen.append(res.request_id), ready_ev.set()),
            Qt.ConnectionType.DirectConnection,
        )
        frame = QImage(16, 16, QImage.Format.Format_RGB888)
        frame.fill(0)

        try:
            # 1. Idle worker stays running and handles subsequent submissions
            worker.submit_frame(frame, request_id=1)
            self.assertTrue(ready_ev.wait(2))
            self.assertTrue(worker.isRunning())

            ready_ev.clear()
            worker.submit_frame(frame, request_id=2)
            self.assertTrue(ready_ev.wait(2))
            self.assertEqual(seen, [1, 2])

            # 2. Reusable stop_worker(permanent=False) suppresses in-flight & allows next session reuse
            seen.clear()
            ready_ev.clear()
            eng.block_first = True
            worker.submit_frame(frame, request_id=10)
            self.assertTrue(entered.wait(2))
            self.assertFalse(worker.stop_worker(wait_ms=0, permanent=False))
            worker.submit_frame(frame, request_id=11)  # Dropped while stopping
            release.set()
            self.assertTrue(worker.wait(2000))
            self.assertEqual(seen, [])

            eng.block_first = False
            worker.submit_frame(frame, request_id=12)
            self.assertTrue(ready_ev.wait(2))
            self.assertEqual(seen, [12])

            # 3. Permanent shutdown prevents further starts
            self.assertTrue(worker.stop_worker(wait_ms=2000, permanent=True))
            ready_ev.clear()
            worker.submit_frame(frame, request_id=13)
            time.sleep(0.05)
            self.assertFalse(ready_ev.is_set())
        finally:
            release.set()
            worker.stop_worker(wait_ms=2000, permanent=True)

    def test_khang_adapter_fresh_checkout_missing_onnx_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "khang_ai_manifest.json"
            manifest_path.write_text(
                json.dumps({
                    "schema": "agroscan.khang-ai-onnx-bundle/1",
                    "product": "apple",
                    "detectors": {
                        "open_box": {
                            "model_file": "missing_apple.onnx",
                            "sha256": "a" * 64,
                            "classes": ["apple"],
                        }
                    },
                    "classifier": {
                        "model_file": "missing_resnet.onnx",
                        "sha256": "b" * 64,
                        "labels": ["apple", "other"],
                    },
                }),
                encoding="utf-8",
            )
            adapter = KhangAiAdapter(manifest_path=manifest_path)
            self.assertFalse(adapter.is_available())
            self.assertEqual(adapter.available_presets(), [])
            self.assertFalse(adapter.is_preset_available("apple", "open_box"))
            self.assertFalse(adapter.is_classifier_available())

    def test_khang_adapter_v2_manifest_multiproduct_and_unsupported_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            orange_onnx = root / "orange_detector_open_box.onnx"
            orange_onnx.write_bytes(b"orange-weights")
            orange_sha = hashlib.sha256(b"orange-weights").hexdigest()
            clf_onnx = root / "classifier.onnx"
            clf_onnx.write_bytes(b"clf-weights")
            clf_sha = hashlib.sha256(b"clf-weights").hexdigest()

            manifest_path = root / "khang_ai_manifest.json"
            manifest_path.write_text(
                json.dumps({
                    "schema": MANIFEST_SCHEMA_V2,
                    "default_product": "apple",
                    "products": {
                        "orange": {
                            "detectors": {
                                "open_box": {
                                    "model_file": "orange_detector_open_box.onnx",
                                    "sha256": orange_sha,
                                    "classes": ["orange"],
                                    "image_size": 960,
                                    "confidence": 0.3,
                                    "nms_iou": 0.5,
                                    "max_det": 500,
                                }
                            }
                        }
                    },
                    "classifier": {
                        "model_file": "classifier.onnx",
                        "sha256": clf_sha,
                        "labels": ["apple", "other"],
                    },
                }),
                encoding="utf-8",
            )
            adapter = KhangAiAdapter(manifest_path=manifest_path)
            self.assertFalse(adapter.is_available("apple"))
            self.assertTrue(adapter.is_available("orange"))
            self.assertEqual(adapter.available_presets("orange"), ["open_box"])

            fake_sess = Mock()
            fake_sess.get_inputs.return_value = [SimpleNamespace(name="images", shape=[1, 3, 960, 960])]
            fake_sess.get_outputs.return_value = [SimpleNamespace(name="output0", shape=[1, 5, 18900])]
            engine = YoloEngine()
            with patch.object(yolo_mod.ort, "InferenceSession", return_value=fake_sess):
                meta = load_product_detector_preset(engine, "orange", "open_box", manifest_path=manifest_path)
            self.assertEqual(meta["product"], "orange")
            self.assertEqual(engine.input_size, (960, 960))
            self.assertEqual(engine.class_names, ["orange"])

            # Unsupported product returns explicit REVIEW_REQUIRED advisory without initializing ONNX even when classifier weights are absent
            clf_onnx.unlink()
            with patch("agroscan.services.container_classifier.ort.InferenceSession") as mock_ort_cls:
                res = adapter.check_container(
                    QImage(64, 64, QImage.Format.Format_RGB888),
                    expected_product="banana",
                    scene_condition="single_product",
                )
            self.assertEqual(res.status, "REVIEW_REQUIRED")
            self.assertEqual(res.reason, "UNSUPPORTED_PRODUCT")
            self.assertFalse(res.can_make_final_decision)
            mock_ort_cls.assert_not_called()

    def test_draw_detections_handles_small_images_and_dense_crates_without_clutter(self) -> None:
        small = QImage(200, 120, QImage.Format.Format_RGB32)
        small.fill(QColor(25, 30, 35))
        dense_boxes = [
            BoundingBox(
                x1=(i % 10) * 18 + 2,
                y1=(i // 10) * 20 + 2,
                x2=(i % 10) * 18 + 16,
                y2=(i // 10) * 20 + 18,
                label="apple",
                confidence=0.85,
            )
            for i in range(40)
        ]
        annotated = draw_detections_on_qimage(small, dense_boxes, fps_text="Apple ONNX · 12.3 ms")
        self.assertEqual(annotated.size(), small.size())
        self.assertNotEqual(annotated.bits(), small.bits())

    def test_count_only_apple_detection_forces_needs_review_and_preserves_lot_N(self) -> None:
        apple_product = Product(
            "APPLE", "Apple", "Fruit", "apple_defect.onnx", ["fresh", "bruised", "rotten"],
            [DefectCriterion("bruised", 0.08), DefectCriterion("rotten", 0.0, is_critical=True)],
        )
        det = DetectionResult(
            total_objects=32,
            class_counts={"apple": 32},
            mean_confidence=0.91,
            is_simulated=False,
            defect_classification_available=False,
        )
        result = rule_engine.assess_quality(apple_product, det)
        self.assertEqual(result.recommendation, AiRecommendation.NEEDS_REVIEW)
        self.assertTrue(any("Count-only detector" in r for r in result.reasons))


class TestKhangRealAppleAndLiveInspection(unittest.TestCase):
    """Verify real apple ONNX inference, ResNet18 gate, and LiveInspectionPage safety guarantees."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.settings = AppSettings(store)
        conn = self.settings.load()
        conn.storage_path = str(Path(self.tmp.name) / "evidence")
        self.settings.save(conn)
        self.repo = MockRepository(seed=42)

    @staticmethod
    def _make_stub_engine():
        eng = Mock()
        eng.is_loaded = False
        eng.model_path = None
        eng.load_for_product.side_effect = lambda p: (
            setattr(eng, "is_loaded", True),
            setattr(eng, "model_path", Path(p.model_file)),
            True,
        )[-1]
        eng.unload.side_effect = lambda: (
            setattr(eng, "is_loaded", False),
            setattr(eng, "model_path", None),
        )
        return eng

    def _make_page_with_stubs(self):
        base_eng = self._make_stub_engine()
        khang_eng = self._make_stub_engine()
        adapter = Mock()
        adapter.is_available.return_value = False
        with (
            patch("agroscan.ui.pages.live_inspection_page.YoloEngine", side_effect=[base_eng, khang_eng]),
            patch("agroscan.ui.pages.live_inspection_page.KhangAiAdapter", return_value=adapter),
        ):
            page = LiveInspectionPage(self.settings)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.clear_session)
        return page, base_eng, khang_eng, adapter

    @unittest.skipUnless(_KHANG_BUNDLE_READY and WORKSPACE_VAL_DIR.is_dir(), "Optional Khang ONNX bundle or val images not present")
    def test_real_apple_val_image_import_runs_resnet18_and_yolo_and_keeps_N_separate(self) -> None:
        val_images = sorted(WORKSPACE_VAL_DIR.glob("*.jpg"))
        self.assertTrue(val_images, "Expected at least one validation apple JPEG")
        img_path = val_images[0]

        box_code, order = self.repo.resolve_box("AGS:DH00122-01/06")
        declared_N = order.expected_quantity
        session = self.repo.create_session(box_code, order, "inspector", "STATION-01")
        page = LiveInspectionPage(self.settings)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.clear_session)
        page.start_session(session)

        self.assertFalse(page.apple_preset_combo.isHidden())
        self.assertEqual(page.apple_preset_combo.currentData(), "open_box")

        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(img_path), "")):
            page.btn_import.click()

        record = page.finalize()
        self.assertIsNotNone(record)
        self.assertEqual(len(record.evidence), 1)
        ev = record.evidence[0]
        self.assertEqual(ev.model_file, "apple_detector_open_box.onnx")
        self.assertGreater(len(ev.units), 0)
        self.assertEqual(record.detection.total_objects, len(ev.units))
        self.assertFalse(record.detection.is_simulated)
        self.assertFalse(record.detection.defect_classification_available)
        self.assertEqual(record.assessment.recommendation, AiRecommendation.NEEDS_REVIEW)

        saved_path = resolve_evidence_path(ev, settings=self.settings)
        self.assertIsNotNone(saved_path)
        self.assertEqual(ev.sha256, compute_sha256(img_path.read_bytes()))
        self.assertEqual(saved_path.read_bytes(), img_path.read_bytes())
        self.assertEqual(order.expected_quantity, declared_N)

        self.assertIsNotNone(page._last_container_check)
        self.assertEqual(page._last_container_check.predicted_label, "apple")
        self.assertEqual(page._last_container_check.status, "MATCH")
        self.assertTrue(any(e.action == "Container Pre-Check (ResNet18)" for e in record.audit_trail))

    def test_count_and_declared_N_vary_independently_including_equality(self) -> None:
        page, base_eng, _khang, _adapter = self._make_page_with_stubs()
        raw_img = QImage(160, 120, QImage.Format.Format_RGB32)
        raw_img.fill(QColor(30, 80, 40))

        for declared_n, detected_count in ((2, 2), (9, 2), (2, 5)):
            product = Product("BANANA", "Banana", "Fruit", "banana_defect.onnx", ["fresh", "bruised", "rotten"], [])
            order = Order(
                f"IND-{declared_n}-{detected_count}",
                product,
                "Supplier",
                total_boxes=10,
                expected_quantity=declared_n,
            )
            session = self.repo.create_session(BoxCode(order.order_code, 1, order.total_boxes), order, "inspector", "S1")
            page.start_session(session)
            base_eng.infer.return_value = _make_stub_output(detected_count)
            page._capture_evidence(raw_img, "imported_image", False)
            record = page.finalize()
            self.assertIsNotNone(record)
            self.assertEqual(record.session.order.expected_quantity, declared_n)
            self.assertEqual(record.detection.total_objects, detected_count)
            self.assertEqual(len(record.evidence[0].units), detected_count)

    def test_camera_capture_binds_session_generation_and_zone(self) -> None:
        page, base_eng, _khang, _adapter = self._make_page_with_stubs()
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        session = self.repo.create_session(box_code, order, "inspector", "S1")
        page.start_session(session)
        base_eng.infer.return_value = _make_stub_output(3)

        page._camera = Mock()
        page._camera.isActive.return_value = True
        page._image_capture = Mock()
        page._image_capture.isReadyForCapture.return_value = True
        page._image_capture.capture.side_effect = [101, 102, 103, 104]

        raw_img = QImage(120, 90, QImage.Format.Format_RGB32)
        raw_img.fill(QColor(40, 120, 60))

        # Request at TOP, then switch combo to LEFT before callback 101 arrives
        page.set_capture_zone(BoxZone.TOP)
        page._on_capture()
        page.set_capture_zone(BoxZone.LEFT)
        page._on_image_captured(101, raw_img)
        self.assertEqual(len(page._evidence), 1)
        self.assertEqual(page._evidence[0].zone, BoxZone.TOP)

        # Duplicate callback 101 ignored
        page._on_image_captured(101, raw_img)
        self.assertEqual(len(page._evidence), 1)

        # Restart same session object invalidates prior request 102
        page._on_capture()
        page.start_session(session)
        page._on_image_captured(102, raw_img)
        self.assertEqual(len(page._evidence), 0)

        # Re-attach active mock camera after start_session() cleared the prior one
        page._camera = Mock()
        page._camera.isActive.return_value = True

        # Capture error drops pending request 103 so subsequent image callback is discarded
        page._on_capture()
        self.assertEqual(page._image_capture.capture.call_count, 3)
        page._on_capture_error(103, 0, "sensor busy")
        page._on_image_captured(103, raw_img)
        self.assertEqual(len(page._evidence), 0)

        # Stopping camera retires pending request 104 even once _camera_active() becomes False
        page._on_capture()
        self.assertEqual(page._image_capture.capture.call_count, 4)
        self.assertIn(104, page._capture_requests)
        page._stop_camera()
        page._on_image_captured(104, raw_img)
        self.assertEqual(len(page._evidence), 0)

    def test_preview_correlation_and_sim_frame_matching(self) -> None:
        page, base_eng, _khang, _adapter = self._make_page_with_stubs()
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        session = self.repo.create_session(box_code, order, "inspector", "S1")
        page.start_session(session)

        page._yolo_worker.submit_frame = Mock()
        page._khang_yolo_worker.submit_frame = Mock()

        page._is_sim_mode = True
        img_a = QImage(100, 80, QImage.Format.Format_RGB32)
        img_a.fill(QColor(200, 10, 10))
        img_b = QImage(100, 80, QImage.Format.Format_RGB32)
        img_b.fill(QColor(10, 10, 200))

        page._frame_token = 1
        page._sim_frame_token = 1
        page._current_raw_sim_image = img_a
        page._show_sim_image(img_a)
        page._submit_preview(img_a, simulation=True)
        req_a = page._preview_request_id

        # Advance to frame B
        page._frame_token = 2
        page._sim_frame_token = 2
        page._current_raw_sim_image = img_b
        page._show_sim_image(img_b)
        page._submit_preview(img_b, simulation=True)
        req_b = page._preview_request_id

        # Deliver stale frame A -> ignored
        page._on_yolo_inference_ready(_make_stub_output(5, request_id=req_a))
        self.assertEqual(page.realtime_total.text(), "—")

        # Deliver current frame B -> draws onto blue frame B and updates count
        out_b = _make_stub_output(2, request_id=req_b)
        with patch("agroscan.ui.pages.live_inspection_page.draw_detections_on_qimage", wraps=draw_detections_on_qimage) as spy_draw:
            page._on_yolo_inference_ready(out_b)
        self.assertEqual(page.realtime_total.text(), "2")
        self.assertEqual(QColor(spy_draw.call_args.args[0].pixel(5, 5)), QColor(10, 10, 200))

        # Slow live camera preview: 10 later submissions (> cap 8) must NOT evict in-flight req_live_1
        page._is_sim_mode = False
        page._sync_realtime_classes()
        page._submit_preview(img_a, simulation=False)
        req_live_1 = page._preview_request_id
        for _ in range(10):
            page._submit_preview(img_b, simulation=False)
        self.assertGreater(page._preview_request_id, req_live_1)
        page._on_yolo_inference_ready(_make_stub_output(7, request_id=req_live_1))
        self.assertEqual(page.realtime_total.text(), "7")
        page._on_yolo_inference_error("transient preview error")

    def test_preview_lifetime_timeout_and_inactive_camera_guard(self) -> None:
        page, _base, _khang, _adapter = self._make_page_with_stubs()
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        session = self.repo.create_session(box_code, order, "inspector", "S1")
        page.start_session(session)

        # Inactive camera object must NOT trigger headless direct-callback fallback
        page._camera = Mock()
        page._camera.isActive.return_value = False
        raw_img = QImage(80, 60, QImage.Format.Format_RGB32)
        raw_img.fill(QColor(30, 100, 30))
        page._on_image_captured(999, raw_img)
        self.assertEqual(len(page._evidence), 0)

        # Failed worker.wait() during _PreviewLifetime.shutdown must keep _closed=False and skip deleteLater()
        lifetime = page._preview_lifetime
        with (
            patch.object(lifetime.workers[0], "wait", return_value=False),
            patch.object(lifetime.workers[1], "wait", return_value=True),
            patch.object(lifetime, "deleteLater") as spy_delete,
        ):
            with self.assertRaises(RuntimeError):
                lifetime.shutdown()
        self.assertFalse(lifetime._closed)
        spy_delete.assert_not_called()
        with (
            patch.object(lifetime.workers[0], "wait", return_value=True),
            patch.object(lifetime.workers[1], "wait", return_value=True),
            patch.object(lifetime, "deleteLater") as spy_delete_ok,
        ):
            lifetime.shutdown()
        self.assertTrue(lifetime._closed)
        spy_delete_ok.assert_called_once()
        lifetime.deleteLater()

    def test_yolo_inference_failure_preserves_raw_evidence_and_blocks_finalize(self) -> None:
        page, base_eng, _khang, _adapter = self._make_page_with_stubs()
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        session = self.repo.create_session(box_code, order, "inspector", "S1")
        page.start_session(session)

        raw_ok = QImage(120, 90, QImage.Format.Format_RGB32)
        raw_ok.fill(QColor(20, 150, 40))
        base_eng.infer.return_value = _make_stub_output(4)
        page._capture_evidence(raw_ok, "imported_image", False)
        self.assertEqual(len(page._evidence), 1)
        self.assertIsNotNone(page.finalize())

        raw_fail = QImage(120, 90, QImage.Format.Format_RGB32)
        raw_fail.fill(QColor(150, 40, 20))
        base_eng.infer.side_effect = RuntimeError("boom onnx error")
        page._capture_evidence(raw_fail, "imported_image", False)

        self.assertEqual(len(page._evidence), 2)
        self.assertEqual(len(page.captured_images), 2)
        failed = page._evidence[-1]
        self.assertEqual(failed.units, [])
        self.assertIsNone(page._detection)
        self.assertIsNone(page.finalize())
        self.assertIn("boom onnx error", page._capture_analysis_error)
        self.assertEqual(failed.sha256, compute_sha256(encode_qimage_bytes(raw_fail)))
        saved = resolve_evidence_path(failed, settings=self.settings)
        self.assertEqual(saved.read_bytes(), encode_qimage_bytes(raw_fail))
        self.assertEqual(encode_qimage_bytes(page.captured_images[-1]), encode_qimage_bytes(raw_fail))
        self.assertTrue(any(e.action == "Evidence Analysis Failed" for e in page._session_audit))

    def test_nonapple_start_rebuilds_rows_and_clears_counts(self) -> None:
        page, _base, _khang, _adapter = self._make_page_with_stubs()
        p_a = Product("APPLE", "Apple", "Fruit", "apple_defect.onnx", ["fresh", "bruised", "rotten"], [])
        o_a = Order("ORD-A", p_a, "Sup", 2, 10)
        page.start_session(self.repo.create_session(BoxCode("ORD-A", 1, 2), o_a, "insp", "S1"))
        page._apply_realtime_counts({"fresh": 5, "bruised": 1, "rotten": 0})
        self.assertEqual(page.realtime_total.text(), "6")

        p_b = Product("ORANGE", "Orange", "Fruit", "orange_defect.onnx", ["healthy", "moldy"], [])
        o_b = Order("ORD-B", p_b, "Sup", 2, 10)
        page.start_session(self.repo.create_session(BoxCode("ORD-B", 1, 2), o_b, "insp", "S1"))
        self.assertEqual(set(page._realtime_labels.keys()), {"healthy", "moldy"})
        self.assertEqual(set(page._frame_history.keys()), {"healthy", "moldy"})
        self.assertEqual(page.realtime_total.text(), "—")

    def test_operational_model_mismatch_separated_and_enforced(self) -> None:
        base_eng = self._make_stub_engine()
        khang_eng = self._make_stub_engine()
        adapter = Mock()
        adapter.is_available.return_value = True
        adapter.load_detector_preset.side_effect = lambda eng, preset: (
            setattr(eng, "is_loaded", True),
            setattr(eng, "model_path", Path(f"apple_detector_{preset}.onnx")),
            {"model_file": f"apple_detector_{preset}.onnx", "image_size": 1280 if preset == "open_box" else 960},
        )[-1]
        adapter.check_apple_container.return_value = ContainerCheckResult(
            predicted_label="apple",
            confidence=0.95,
            probabilities={"apple": 0.95, "other": 0.05},
            status="MATCH",
            reason="",
            model_file="apple_vs_other_resnet18.onnx",
        )

        with (
            patch("agroscan.ui.pages.live_inspection_page.YoloEngine", side_effect=[base_eng, khang_eng]),
            patch("agroscan.ui.pages.live_inspection_page.KhangAiAdapter", return_value=adapter),
        ):
            page = LiveInspectionPage(self.settings)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.clear_session)

        op_apple = Product("APPLE", "Apple", "Fruit", "apple_defect.onnx", ["fresh", "bruised", "rotten"], [])
        op_order = Order("OP-M3-01", op_apple, "Orchard", 3, 60, lot_id=777)
        session = self.repo.create_session(BoxCode("OP-M3-01", 1, 3), op_order, "inspector", "S1")
        page.start_session(session)

        # Default picks baseline -> allowed
        self.assertEqual(page.apple_preset_combo.currentData(), "baseline")
        self.assertTrue(page.btn_import.isEnabled())
        self.assertFalse(page.operational_model_label.isVisible())

        # Manually select open_box -> operational warning stays separate and blocks non-demo capture
        idx_open = page.apple_preset_combo.findData("open_box")
        page.apple_preset_combo.setCurrentIndex(idx_open)
        self.assertFalse(page.operational_model_label.isHidden())
        self.assertIn("apple_defect.onnx", page.operational_model_label.text())
        self.assertFalse(page.btn_import.isEnabled())

        raw_img = QImage(100, 100, QImage.Format.Format_RGB32)
        raw_img.fill(QColor(10, 120, 40))
        page._capture_evidence(raw_img, "imported_image", False)
        self.assertEqual(len(page._evidence), 0)
        khang_eng.infer.assert_not_called()

        # Revert to baseline -> capture succeeds, and tampering evidence model_file blocks submit
        idx_base = page.apple_preset_combo.findData("baseline")
        page.apple_preset_combo.setCurrentIndex(idx_base)
        base_eng.infer.return_value = _make_stub_output(3)
        page._capture_evidence(raw_img, "imported_image", False)
        self.assertEqual(len(page._evidence), 1)
        page._evidence[0].model_file = "apple_detector_open_box.onnx"
        self.assertIsNone(page.finalize())
        emitted_next: list[str] = []
        page.next_box_scanned.connect(emitted_next.append)
        page.next_scan_field.setText("AGS:OP-M3-01-02/03")
        page._on_next_scanned()
        self.assertEqual(emitted_next, [])

    @unittest.skipUnless(_KHANG_BUNDLE_READY, "Optional Khang ONNX bundle not installed")
    def test_classifier_requires_explicit_single_product_scene_condition(self) -> None:
        adapter = KhangAiAdapter()
        blank = QImage(256, 256, QImage.Format.Format_RGB32)
        blank.fill(QColor(20, 20, 20))
        res = adapter.check_apple_container(blank, scene_condition="mixed_or_uncertain")
        self.assertEqual(res.status, "REVIEW_REQUIRED")
        self.assertEqual(res.reason, "SCENE_CONDITION_NOT_CONFIRMED")
        self.assertFalse(res.can_make_final_decision)

    @unittest.skipUnless(_KHANG_BUNDLE_READY, "Optional Khang ONNX bundle not installed")
    def test_live_inspection_respects_operational_db_assigned_apple_model(self) -> None:
        apple_baseline = Product(
            "APPLE", "Apple", "Fruit", "apple_defect.onnx",
            ["fresh", "bruised", "rotten"], [DefectCriterion("bruised", 0.08)],
        )
        op_order = Order("OP-APPLE-01", apple_baseline, "Orchard", 3, 60, lot_id=999)
        session = self.repo.create_session(BoxCode("OP-APPLE-01", 1, 3), op_order, "inspector", "S1")
        page = LiveInspectionPage(self.settings)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.clear_session)
        page.start_session(session)
        self.assertEqual(page.apple_preset_combo.currentData(), "baseline")
        self.assertFalse(page._use_khang_apple_detector())

        apple_tray = Product(
            "APPLE", "Apple", "Fruit", "apple_detector_tray.onnx",
            ["fresh", "bruised", "rotten"], [DefectCriterion("bruised", 0.08)],
        )
        op_order_tray = Order("OP-APPLE-02", apple_tray, "Orchard", 3, 60, lot_id=1000)
        session_tray = self.repo.create_session(BoxCode("OP-APPLE-02", 1, 3), op_order_tray, "inspector", "S1")
        page.start_session(session_tray)
        self.assertEqual(page.apple_preset_combo.currentData(), "tray")
        self.assertTrue(page._use_khang_apple_detector())
        self.assertEqual(list(page._realtime_labels.keys()), ["apple"])


class TestVlmBr14AndBugFixes(unittest.TestCase):
    """Verify Qwen3-VL BR14, HTTP framing/timeout, BMP handling, loopback proxy, and OpenAI chat route."""

    @staticmethod
    def _send_raw_http(port: int, payload_bytes: bytes) -> tuple[int, dict]:
        with socket.create_connection(("127.0.0.1", port), timeout=5.0) as sock:
            sock.sendall(payload_bytes)
            chunks = []
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        raw = b"".join(chunks).decode("utf-8", errors="replace")
        head, _, body = raw.partition("\r\n\r\n")
        status_line = head.splitlines()[0]
        code = int(status_line.split()[1])
        return code, json.loads(body) if body.strip() else {}

    def test_map_br14_to_vlm_schema_1_0_green_and_red(self) -> None:
        br14_red = {
            "ocr_status": "READABLE",
            "ocr_text": "LOT-APPLE-2026 | VIETNAM",
            "ai_findings": [
                {"rule_code": "bruise", "assessment": "NOT_OBSERVED", "detail": "No clear flattened area."},
                {"rule_code": "skin_damage", "assessment": "OBSERVED", "detail": "Split peel near stem cavity."},
                {"rule_code": "discoloration", "assessment": "UNCERTAIN", "detail": "Shadow on lower right edge."},
                {"rule_code": "visible_decay", "assessment": "OBSERVED", "detail": "Dark soft rot lesion visible."},
            ],
            "explanation_en": "Dark soft lesion and broken skin visible on the top apple surface.",
            "limits_note": "Visible upper surfaces only; occluded undersides cannot be assessed.",
        }
        mapped = map_br14_to_vlm_findings(br14_red, {"box_code": "AGS:APPLE-01/03"})
        parsed = parse_vlm_response({
            **mapped,
            "schema_version": "1.0",
            "request_id": "req-test-1",
            "status": "ok",
            "model": "Qwen3-VL-4B-Instruct-Q4_K_M",
            "latency_ms": 1200,
            "analyzed_at": "2026-11-26T10:00:00",
        })
        self.assertEqual(parsed.status, VlmStatus.OK)
        self.assertTrue(parsed.ocr.readable)
        self.assertEqual(parsed.ocr.raw_text, "LOT-APPLE-2026 | VIETNAM")
        self.assertEqual({d.defect_class for d in parsed.defects}, {"skin_damage", "rotten"})
        self.assertTrue(all(d.count == 0 and d.confidence == 0.0 for d in parsed.defects))
        self.assertTrue(parsed.warnings)
        self.assertEqual(parsed.uncertainty.level.value, "medium")

    def test_loopback_guard_and_mime_detection(self) -> None:
        self.assertEqual(
            _assert_loopback_http("http://127.0.0.1:18080/v1/chat/completions"),
            "http://127.0.0.1:18080/v1/chat/completions",
        )
        with self.assertRaises(ValueError):
            _assert_loopback_http("http://example.com:18080/v1/chat/completions")
        self.assertEqual(_detect_image_mime(b"\xff\xd8\xff\xe0" + b"0" * 32), "image/jpeg")
        self.assertEqual(_detect_image_mime(b"\x89PNG\r\n\x1a\n" + b"0" * 32), "image/png")
        self.assertEqual(_detect_image_mime(b"BM" + b"\x00" * 32), "image/bmp")
        with self.assertRaises(ValueError):
            _detect_image_mime(b"NOT_AN_IMAGE" + b"\x00" * 32)

    def test_bmp_transcodes_to_png_and_unknown_format_rejected(self) -> None:
        buf = BytesIO()
        Image.new("RGB", (32, 32), (200, 30, 30)).save(buf, format="BMP")
        bmp_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        captured_mime = []
        captured_b64 = []
        valid_reply = {
            "defects": [],
            "ocr": {"readable": False, "fields": [], "raw_text": ""},
            "observations": ["Clear surface."],
            "assessment": "Surface clean.",
            "uncertainty": {"level": "low", "score": 0.1, "reasons": ["Clear frame."]},
            "suggestion": "Proceed.",
        }

        def _fake_lm(image_b64, context, lm_studio_url, model_name):
            captured_b64.append(image_b64)
            captured_mime.append(context["image_mime"])
            return valid_reply

        with patch("server.qwen_service._call_lm_studio", side_effect=_fake_lm):
            res = build_vlm_response({"image_base64": bmp_b64, "product_code": "BANANA"})
        self.assertEqual(res["status"], "ok")
        self.assertEqual(captured_mime, ["image/png"])
        self.assertTrue(base64.b64decode(captured_b64[0]).startswith(b"\x89PNG\r\n\x1a\n"))

        bad_b64 = base64.b64encode(b"INVALID_IMAGE_HEADER" + b"\x00" * 40).decode("ascii")
        bad_res = parse_vlm_response(build_vlm_response({"image_base64": bad_b64}))
        self.assertTrue(bad_res.is_error)
        self.assertEqual(bad_res.error.code, VlmErrorCode.IMAGE_UNUSABLE)

    def test_lm_studio_disables_proxy_on_loopback(self) -> None:
        png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode("ascii")
        handlers_passed = []

        class _FakeOpener:
            def open(self, req, timeout=0):
                raise OSError("offline stop")

        def _capture_opener(*handlers):
            handlers_passed.extend(handlers)
            return _FakeOpener()

        with patch("urllib.request.build_opener", side_effect=_capture_opener):
            _call_lm_studio(png_b64, {"image_mime": "image/png"}, "http://127.0.0.1:1234/v1/chat/completions", "qwen")
        self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler) and h.proxies == {} for h in handlers_passed))

    def test_http_framing_limits_timeout_and_chat_route_translation(self) -> None:
        buf = BytesIO()
        Image.new("RGB", (24, 24), (10, 180, 30)).save(buf, format="PNG")
        png_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        fake_findings = {
            "defects": [],
            "ocr": {"readable": False, "fields": [], "raw_text": ""},
            "observations": ["Clean."],
            "assessment": "No issues.",
            "uncertainty": {"level": "low", "score": 0.1, "reasons": ["Clear."]},
            "suggestion": "Proceed.",
        }

        server = create_server("127.0.0.1", 0, model_name="TestQwen")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("server.qwen_service._call_lm_studio", return_value=fake_findings):
                # Malformed Content-Length -> 400
                code, _ = self._send_raw_http(port, b"POST /api/v1/vlm/analyze HTTP/1.1\r\nHost: localhost\r\nContent-Length: nope\r\n\r\n")
                self.assertEqual(code, 400)

                # Oversized Content-Length -> immediate 413 without reading body
                code, _ = self._send_raw_http(port, b"POST /api/v1/vlm/analyze HTTP/1.1\r\nHost: localhost\r\nContent-Length: 20971521\r\n\r\n")
                self.assertEqual(code, 413)

                # Transfer-Encoding rejected -> 400
                code, _ = self._send_raw_http(port, b"POST /api/v1/vlm/analyze HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n")
                self.assertEqual(code, 400)

                # Unknown route suffix -> 404
                code, _ = self._send_raw_http(port, b"POST /api/v1/vlm/analyzeXYZ HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n{}")
                self.assertEqual(code, 404)

                # Stalled partial body -> 408
                with patch.object(qwen_srv, "REQUEST_READ_TIMEOUT_S", 0.15):
                    with socket.create_connection(("127.0.0.1", port), timeout=3.0) as sock:
                        sock.sendall(b"POST /api/v1/vlm/analyze HTTP/1.1\r\nHost: localhost\r\nContent-Length: 500\r\n\r\n{")
                        resp = sock.recv(4096).decode("utf-8", errors="replace")
                    self.assertIn("408", resp.splitlines()[0])

                # /v1/chat/completions translates OpenAI vision messages -> chat.completion envelope
                chat_payload = json.dumps({
                    "model": "client-model",
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": "Inspect visible skin."},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Focus on bruises."},
                                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_b64}"}},
                            ],
                        },
                    ],
                }).encode("utf-8")
                req = (
                    f"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(chat_payload)}\r\n\r\n"
                ).encode("ascii") + chat_payload
                code, body = self._send_raw_http(port, req)
                self.assertEqual(code, 200)
                self.assertEqual(body["object"], "chat.completion")
                parsed_inner = json.loads(body["choices"][0]["message"]["content"])
                self.assertEqual(parsed_inner["status"], "ok")
        finally:
            server.shutdown()
            server.server_close()

    def test_llama_br14_backend_via_build_vlm_response(self) -> None:
        png_fake = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        b64 = base64.b64encode(png_fake).decode("ascii")
        mock_findings = {
            "defects": [],
            "ocr": {"readable": False, "fields": [], "raw_text": ""},
            "observations": ["No visible surface defect."],
            "assessment": "Visible-surface screening only; not a food-safety or clearance decision.",
            "uncertainty": {"level": "low", "score": 0.2, "reasons": ["Visible top surface only."]},
            "suggestion": "No BR14 surface defects observed.",
        }
        with patch("server.qwen_service._call_llama_br14", return_value=mock_findings):
            raw = build_vlm_response({
                "image_base64": b64,
                "product_code": "APPLE",
                "product_name": "Apple",
                "vlm_backend": "llama_br14",
            })
        parsed = parse_vlm_response(raw)
        self.assertFalse(parsed.is_error)
        self.assertEqual(parsed.uncertainty.level.value, "low")

        non_apple = parse_vlm_response(build_vlm_response({
            "image_base64": b64,
            "product_code": "BANANA",
            "product_name": "Banana",
            "vlm_backend": "llama_br14",
        }))
        self.assertTrue(non_apple.is_error)
        self.assertEqual(non_apple.error.code, VlmErrorCode.MODEL_ERROR)

    def test_llama_br14_disables_proxy_for_loopback_calls(self) -> None:
        png_fake = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        b64 = base64.b64encode(png_fake).decode("ascii")
        handlers_passed = []

        class _FakeOpener:
            def open(self, req, timeout=0):
                raise OSError("expected offline stop")

        def _capture_opener(*handlers):
            handlers_passed.extend(handlers)
            return _FakeOpener()

        with patch("urllib.request.build_opener", side_effect=_capture_opener):
            res = _call_llama_br14(b64, {"image_mime": "image/png"}, llama_url="http://127.0.0.1:18080/v1/chat/completions", api_key="secret")
        self.assertIsNone(res)
        proxy_handlers = [h for h in handlers_passed if isinstance(h, urllib.request.ProxyHandler)]
        self.assertTrue(proxy_handlers)
        self.assertEqual(proxy_handlers[0].proxies, {})

    def test_vlm_client_extracts_fenced_json_in_openai_chat_mode(self) -> None:
        from agroscan.services.app_settings import ConnectionSettings

        payload_dict = {
            "defects": [],
            "ocr": {"readable": False, "fields": [], "raw_text": ""},
            "observations": ["Apple surface looks intact."],
            "assessment": "No visible defect seen.",
            "uncertainty": {"level": "low", "score": 0.15, "reasons": ["Clear frame."]},
            "suggestion": "Proceed normally.",
        }
        fenced_reply = json.dumps({
            "model": "qwen2.5-vl",
            "choices": [{"message": {"content": "```json\n" + json.dumps(payload_dict) + "\n```"}}],
        }).encode("utf-8")

        class _FakeResp:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return fenced_reply

        repo = MockRepository(seed=42)
        session = repo.create_session(BoxCode("DH00122", 1, 6), repo.orders["DH00122"], "inspector", "S1")
        cfg = ConnectionSettings(ai_url="http://127.0.0.1:1234")
        with patch("urllib.request.urlopen", return_value=_FakeResp()):
            res = request_deep_analysis(session, DetectionResult(10, {"fresh": 10}, 0.9), None, cfg, fallback_to_mock=False)
        self.assertFalse(res.is_error)
        self.assertEqual(res.observations, ["Apple surface looks intact."])


if __name__ == "__main__":
    unittest.main()
