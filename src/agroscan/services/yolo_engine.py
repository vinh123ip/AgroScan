"""YOLOv8 ONNX Runtime inference engine, tracker, and QThread worker (T1.4, D-003, D-024, D-025, D-026).

Key capabilities:
1. Loads product-specialized `.onnx` models (`banana_defect.onnx`, `apple_defect.onnx`,
   `fruit_defect.onnx`) via ``onnxruntime.InferenceSession``.
2. Preprocesses ``QImage`` or ``numpy.ndarray`` frames with aspect-preserving letterbox
   resize to ``640x640`` (`float32` NCHW `[0, 1]`).
3. Postprocesses YOLOv8 `[1, 4+C, 8400]` output tensors with confidence filtering and
   Non-Maximum Suppression (NMS), mapping bounding boxes back to original pixel space.
4. Assigns persistent object IDs across video frames using a lightweight Centroid/IoU
   tracker (D-025) while keeping official detection counts tied to still captures (D-026).
5. Executes inference asynchronously on a background ``QThread`` (`YoloInferenceThread`)
   so the PySide6 UI remains responsive at all times.
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass, field
import logging
import math
from pathlib import Path
import threading
import time
from typing import Optional, Sequence, Union
import weakref

import cv2
import numpy as np
import onnxruntime as ort
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, QWaitCondition, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from agroscan.models.inspection_models import DetectionResult, Product

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WEIGHTS_DIR = REPO_ROOT / "models" / "weights"
FALLBACK_WEIGHTS_DIR = REPO_ROOT / "models_ai"
DEFAULT_CLASSES: tuple[str, ...] = ("fresh", "bruised", "rotten")
_SPECIES_ONLY_LABELS = frozenset({"apple", "orange", "banana", "shrimp", "squid", "fruit", "object"})


@dataclass
class BoundingBox:
    """Single object detection bounding box in original image pixel coordinates."""

    x1: int
    y1: int
    x2: int
    y2: int
    label: str
    confidence: float
    class_id: int = 0
    track_id: Optional[int] = None

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) * 0.5, (self.y1 + self.y2) * 0.5)


@dataclass
class YoloInferenceOutput:
    """Complete result returned by a single YOLO inference pass."""

    boxes: list[BoundingBox] = field(default_factory=list)
    detection: DetectionResult = field(
        default_factory=lambda: DetectionResult(
            total_objects=0, class_counts={}, mean_confidence=0.0, is_simulated=False
        )
    )
    inference_ms: float = 0.0
    model_path: str = ""
    request_id: int = 0


def resolve_model_path(
    model_file: str = "fruit_defect.onnx",
    search_dirs: Optional[Sequence[Union[Path, str]]] = None,
) -> Optional[Path]:
    """Locate an `.onnx` model file across standard AgroScan model directories."""
    cleaned = (model_file or "fruit_defect.onnx").strip()
    direct = Path(cleaned)
    if direct.is_absolute():
        return direct if direct.is_file() else None

    dirs: list[Path] = []
    if search_dirs:
        dirs.extend(Path(d) for d in search_dirs)
    dirs.extend([DEFAULT_WEIGHTS_DIR, FALLBACK_WEIGHTS_DIR, REPO_ROOT])

    candidates = [cleaned]
    if Path(cleaned).name != "fruit_defect.onnx":
        candidates.append("fruit_defect.onnx")

    for candidate in candidates:
        for base in dirs:
            path = base / candidate
            if path.is_file():
                return path
            by_name = base / Path(candidate).name
            if by_name.is_file():
                return by_name

    return None


def qimage_to_rgb_array(image: QImage) -> np.ndarray:
    """Convert a ``QImage`` into a contiguous `(H, W, 3)` uint8 RGB numpy array."""
    if image.isNull():
        raise ValueError("Cannot convert a null QImage to numpy array.")
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    ptr = converted.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((height, bytes_per_line))
    rgb = arr[:, : width * 3].reshape((height, width, 3)).copy()
    return rgb


def _compute_iou(box_a: BoundingBox, box_b: BoundingBox) -> float:
    inter_x1 = max(box_a.x1, box_b.x1)
    inter_y1 = max(box_a.y1, box_b.y1)
    inter_x2 = min(box_a.x2, box_b.x2)
    inter_y2 = min(box_a.y2, box_b.y2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0
    area_a = box_a.width * box_a.height
    area_b = box_b.width * box_b.height
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def non_max_suppression(
    boxes: Sequence[BoundingBox], iou_threshold: float = 0.40
) -> list[BoundingBox]:
    """Perform greedy Non-Maximum Suppression sorted by descending confidence."""
    sorted_boxes = sorted(boxes, key=lambda b: b.confidence, reverse=True)
    kept: list[BoundingBox] = []
    for candidate in sorted_boxes:
        if all(_compute_iou(candidate, existing) < iou_threshold for existing in kept):
            kept.append(candidate)
    return kept


class CentroidTracker:
    """Lightweight centroid + IoU tracker for stable per-object IDs on preview (D-025)."""

    def __init__(self, max_distance_px: float = 65.0, max_disappeared: int = 8) -> None:
        self._max_distance = max_distance_px
        self._max_disappeared = max_disappeared
        self._next_id = 1
        self._tracks: dict[int, tuple[float, float, int]] = {}  # id -> (cx, cy, disappeared)

    def reset(self) -> None:
        self._next_id = 1
        self._tracks.clear()

    def update(self, boxes: list[BoundingBox]) -> list[BoundingBox]:
        if not boxes:
            to_delete = []
            for tid, (cx, cy, disappeared) in self._tracks.items():
                if disappeared + 1 > self._max_disappeared:
                    to_delete.append(tid)
                else:
                    self._tracks[tid] = (cx, cy, disappeared + 1)
            for tid in to_delete:
                del self._tracks[tid]
            return boxes

        unmatched_boxes = list(range(len(boxes)))
        unmatched_tracks = list(self._tracks.keys())

        pairs: list[tuple[float, int, int]] = []
        for tid in unmatched_tracks:
            tx, ty, _ = self._tracks[tid]
            for b_idx in unmatched_boxes:
                bx, by = boxes[b_idx].center
                dist = math.hypot(tx - bx, ty - by)
                if dist <= self._max_distance:
                    pairs.append((dist, tid, b_idx))

        pairs.sort(key=lambda item: item[0])
        matched_tracks: set[int] = set()
        matched_boxes: set[int] = set()

        for _dist, tid, b_idx in pairs:
            if tid in matched_tracks or b_idx in matched_boxes:
                continue
            matched_tracks.add(tid)
            matched_boxes.add(b_idx)
            bx, by = boxes[b_idx].center
            self._tracks[tid] = (bx, by, 0)
            boxes[b_idx].track_id = tid

        for tid in list(self._tracks.keys()):
            if tid not in matched_tracks:
                tx, ty, disappeared = self._tracks[tid]
                if disappeared + 1 > self._max_disappeared:
                    del self._tracks[tid]
                else:
                    self._tracks[tid] = (tx, ty, disappeared + 1)

        for b_idx in unmatched_boxes:
            if b_idx not in matched_boxes:
                tid = self._next_id
                self._next_id += 1
                bx, by = boxes[b_idx].center
                self._tracks[tid] = (bx, by, 0)
                boxes[b_idx].track_id = tid

        return boxes


class YoloEngine:
    """ONNX Runtime YOLOv8 inference engine (T1.4)."""

    INPUT_SIZE = (640, 640)

    def __init__(
        self,
        model_path: Optional[Union[Path, str]] = None,
        class_names: Sequence[str] = DEFAULT_CLASSES,
        conf_threshold: float = 0.45,
        iou_threshold: float = 0.40,
        max_det: int = 1000,
        letterbox_fill: tuple[int, int, int] = (18, 22, 28),
    ) -> None:
        self._class_names = list(class_names) if class_names else list(DEFAULT_CLASSES)
        self._conf_threshold = float(conf_threshold)
        self._iou_threshold = float(iou_threshold)
        self._max_det = max(1, int(max_det))
        self._input_size: tuple[int, int] = self.INPUT_SIZE
        self._letterbox_fill: tuple[int, int, int] = tuple(int(c) for c in letterbox_fill)
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: str = "images"
        self._model_path: Optional[Path] = None
        self._model_class_count: Optional[int] = None
        self._tracker = CentroidTracker()
        self._lock = QMutex()

        if model_path is not None:
            self.load_model(model_path, class_names=self._class_names)

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def model_path(self) -> Optional[Path]:
        return self._model_path

    @property
    def class_names(self) -> list[str]:
        return list(self._class_names)

    @property
    def input_size(self) -> tuple[int, int]:
        return self._input_size

    def unload(self) -> None:
        """Unload any active ONNX session safely."""
        with QMutexLocker(self._lock):
            self._session = None
            self._model_path = None
            self._model_class_count = None
            self._input_size = self.INPUT_SIZE
            self._tracker.reset()

    def reset_tracker(self) -> None:
        with QMutexLocker(self._lock):
            self._tracker.reset()

    def load_model(
        self,
        model_file_or_path: Union[Path, str],
        class_names: Optional[Sequence[str]] = None,
        *,
        conf_threshold: Optional[float] = None,
        iou_threshold: Optional[float] = None,
        max_det: Optional[int] = None,
        letterbox_fill: Optional[tuple[int, int, int]] = None,
    ) -> bool:
        """Load an `.onnx` model atomically into `onnxruntime.InferenceSession`."""
        with QMutexLocker(self._lock):
            resolved = resolve_model_path(str(model_file_or_path))
            if resolved is None or not resolved.is_file():
                return False

            next_classes = (
                [str(c).strip() for c in class_names]
                if class_names is not None
                else list(self._class_names)
            )
            if not next_classes or any(not c for c in next_classes):
                return False
            if len(set(next_classes)) != len(next_classes):
                return False
            next_conf = self._conf_threshold if conf_threshold is None else float(conf_threshold)
            next_iou = self._iou_threshold if iou_threshold is None else float(iou_threshold)
            next_max_det = self._max_det if max_det is None else max(1, int(max_det))
            next_fill = (
                self._letterbox_fill
                if letterbox_fill is None
                else (int(letterbox_fill[0]), int(letterbox_fill[1]), int(letterbox_fill[2]))
            )

            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 2
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            try:
                session = ort.InferenceSession(
                    str(resolved),
                    sess_options=sess_options,
                    providers=["CPUExecutionProvider"],
                )
                inputs = session.get_inputs()
                outputs = session.get_outputs()
                if not inputs or not outputs:
                    return False

                output_shape = outputs[0].shape
                if (
                    output_shape is None
                    or len(output_shape) != 3
                    or (output_shape[0] not in (1, None) and not isinstance(output_shape[0], str))
                    or not isinstance(output_shape[1], int)
                    or output_shape[1] <= 4
                ):
                    return False

                model_class_count = output_shape[1] - 4
                if model_class_count != len(next_classes):
                    return False

                input_name = inputs[0].name
                inferred_size = self.INPUT_SIZE
                input_shape = inputs[0].shape
                if (
                    input_shape is not None
                    and len(input_shape) == 4
                    and isinstance(input_shape[2], int)
                    and isinstance(input_shape[3], int)
                    and input_shape[2] > 0
                    and input_shape[3] > 0
                ):
                    inferred_size = (int(input_shape[3]), int(input_shape[2]))
            except Exception:
                return False

            self._session = session
            self._input_name = input_name
            self._input_size = inferred_size
            self._model_path = resolved
            self._model_class_count = model_class_count
            self._class_names = next_classes
            self._conf_threshold = next_conf
            self._iou_threshold = next_iou
            self._max_det = next_max_det
            self._letterbox_fill = next_fill
            self._tracker.reset()
            return True

    def load_for_product(self, product: Product) -> bool:
        """Load the `.onnx` model configured for ``product`` (D-024)."""
        return self.load_model(product.model_file, class_names=product.detect_classes)

    def preprocess(
        self, rgb_image: np.ndarray
    ) -> tuple[np.ndarray, float, int, int]:
        """Letterbox resize `(H, W, 3)` RGB uint8 array to `(1, 3, H_in, W_in)` float32."""
        orig_h, orig_w = rgb_image.shape[:2]
        target_w, target_h = self._input_size
        scale = min(target_w / max(1, orig_w), target_h / max(1, orig_h))
        new_w = max(1, int(round(orig_w * scale)))
        new_h = max(1, int(round(orig_h * scale)))

        resized = cv2.resize(rgb_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_h, target_w, 3), self._letterbox_fill, dtype=np.uint8)
        pad_x = (target_w - new_w) // 2
        pad_y = (target_h - new_h) // 2
        canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized

        tensor = canvas.astype(np.float32) / 255.0
        tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis, ...]
        return np.ascontiguousarray(tensor, dtype=np.float32), scale, pad_x, pad_y

    def postprocess(
        self,
        raw_output: np.ndarray,
        orig_w: int,
        orig_h: int,
        scale: float,
        pad_x: int,
        pad_y: int,
        track: bool = True,
    ) -> tuple[list[BoundingBox], DetectionResult]:
        """Decode YOLOv8 `(1, 4+C, N)` predictions into `BoundingBox` list and `DetectionResult`."""
        if self._model_class_count is None:
            raise RuntimeError("YOLO output class count has not been verified.")
        arr = np.asarray(raw_output)
        if (
            arr.ndim != 3
            or arr.shape[0] != 1
            or arr.shape[1] != 4 + self._model_class_count
        ):
            raise ValueError(f"Unexpected YOLO output shape: {arr.shape!r}")
        if len(self._class_names) != self._model_class_count:
            raise RuntimeError("YOLO class configuration no longer matches the model.")
        if orig_w <= 0 or orig_h <= 0 or not math.isfinite(scale) or scale <= 0:
            raise ValueError("Invalid original image dimensions or letterbox scale.")

        has_defect_classes = (
            self._model_class_count == len(self._class_names)
            and self._model_class_count > 1
            and not all(c.strip().lower() in _SPECIES_ONLY_LABELS for c in self._class_names)
        )
        preds = arr[0].T
        if preds.shape[0] == 0:
            empty_counts = {cls: 0 for cls in self._class_names}
            return [], DetectionResult(
                0,
                empty_counts,
                0.0,
                is_simulated=False,
                defect_classification_available=has_defect_classes,
            )

        boxes_xywh = preds[:, :4]
        class_scores = preds[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        max_scores = class_scores[np.arange(len(class_scores)), class_ids]

        mask = max_scores >= self._conf_threshold
        boxes_xywh = boxes_xywh[mask]
        class_ids = class_ids[mask]
        max_scores = max_scores[mask]

        candidates: list[BoundingBox] = []
        inv_scale = 1.0 / scale
        for (cx, cy, bw, bh), cls_id, score in zip(boxes_xywh, class_ids, max_scores):
            if not np.isfinite([cx, cy, bw, bh, score]).all() or bw <= 0 or bh <= 0:
                continue
            x1 = int(round((cx - bw * 0.5 - pad_x) * inv_scale))
            y1 = int(round((cy - bh * 0.5 - pad_y) * inv_scale))
            x2 = int(round((cx + bw * 0.5 - pad_x) * inv_scale))
            y2 = int(round((cy + bh * 0.5 - pad_y) * inv_scale))

            x1 = max(0, min(orig_w, x1))
            y1 = max(0, min(orig_h, y1))
            x2 = max(0, min(orig_w, x2))
            y2 = max(0, min(orig_h, y2))
            if x2 <= x1 or y2 <= y1:
                continue

            cls_idx = int(cls_id)
            label = (
                self._class_names[cls_idx]
                if 0 <= cls_idx < len(self._class_names)
                else f"class_{cls_idx}"
            )
            candidates.append(
                BoundingBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    label=label,
                    confidence=float(score),
                    class_id=cls_idx,
                )
            )

        kept = non_max_suppression(candidates, iou_threshold=self._iou_threshold)
        if self._max_det > 0 and len(kept) > self._max_det:
            kept = kept[: self._max_det]
        # Sort top-to-bottom, left-to-right for stable track ordering
        kept.sort(key=lambda b: (b.y1 // 40, b.x1))
        if track:
            kept = self._tracker.update(kept)

        counts: dict[str, int] = {cls: 0 for cls in self._class_names}
        for box in kept:
            counts[box.label] = counts.get(box.label, 0) + 1

        total = len(kept)
        mean_conf = (
            round(sum(b.confidence for b in kept) / total, 3) if total > 0 else 0.0
        )
        detection = DetectionResult(
            total_objects=total,
            class_counts=counts,
            mean_confidence=mean_conf,
            is_simulated=False,
            defect_classification_available=has_defect_classes,
        )
        return kept, detection

    def infer(
        self,
        frame: Union[QImage, np.ndarray],
        track: bool = True,
        request_id: int = 0,
    ) -> YoloInferenceOutput:
        """Run synchronous YOLOv8 ONNX inference on ``frame``."""
        with QMutexLocker(self._lock):
            if self._session is None:
                raise RuntimeError("YOLO ONNX model is not loaded.")

            t0 = time.perf_counter()
            rgb = qimage_to_rgb_array(frame) if isinstance(frame, QImage) else frame
            orig_h, orig_w = rgb.shape[:2]
            tensor, scale, pad_x, pad_y = self.preprocess(rgb)
            outputs = self._session.run(None, {self._input_name: tensor})
            boxes, detection = self.postprocess(
                outputs[0],
                orig_w=orig_w,
                orig_h=orig_h,
                scale=scale,
                pad_x=pad_x,
                pad_y=pad_y,
                track=track,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return YoloInferenceOutput(
                boxes=boxes,
                detection=detection,
                inference_ms=round(elapsed_ms, 2),
                model_path=str(self._model_path or ""),
                request_id=request_id,
            )


_LOG = logging.getLogger(__name__)
_ACTIVE_WORKERS_LOCK = threading.Lock()
_ACTIVE_WORKERS: weakref.WeakSet["YoloInferenceThread"] = weakref.WeakSet()


def _shutdown_active_yolo_workers() -> None:
    with _ACTIVE_WORKERS_LOCK:
        workers = list(_ACTIVE_WORKERS)
    for worker in workers:
        try:
            joined = worker.stop_worker(wait_ms=10000, permanent=True)
            if not joined:
                _LOG.warning("YoloInferenceThread did not stop within 10s during exit cleanup")
                worker.setParent(None)
        except RuntimeError:
            pass


atexit.register(_shutdown_active_yolo_workers)


class YoloInferenceThread(QThread):
    """Background ``QThread`` executing ``YoloEngine.infer`` without blocking the UI (T1.4)."""

    inference_ready = Signal(object)  # YoloInferenceOutput
    inference_error = Signal(str)

    def __init__(
        self, engine: YoloEngine, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._mutex = QMutex()
        self._work_available = QWaitCondition()
        self._pending_frame: Optional[QImage] = None
        self._pending_track: bool = True
        self._pending_request_id: int = 0
        self._stop_requested: bool = False
        self._permanent_stop: bool = False
        self._started: bool = False
        with _ACTIVE_WORKERS_LOCK:
            _ACTIVE_WORKERS.add(self)

    def submit_frame(
        self, frame: QImage, track: bool = True, request_id: int = 0
    ) -> None:
        """Queue the latest frame for background inference (drops stale intermediate frames)."""
        if frame.isNull():
            return
        need_start = False
        with QMutexLocker(self._mutex):
            if self._stop_requested or self._permanent_stop:
                return
            self._pending_frame = frame.copy()
            self._pending_track = track
            self._pending_request_id = request_id
            if not self._started:
                self._started = True
                need_start = True
            else:
                self._work_available.wakeOne()
        if need_start:
            if self.isRunning() and QThread.currentThread() != self:
                self.wait(5000)
            with QMutexLocker(self._mutex):
                if self._stop_requested or self._permanent_stop:
                    self._started = False
                    if not self._permanent_stop:
                        self._stop_requested = False
                    return
                if self.isRunning():
                    self._started = False
                    _LOG.warning("Timed out waiting for prior YoloInferenceThread run to exit")
                    return
                self.start()

    def stop_worker(self, wait_ms: int = 1000, *, permanent: bool = False) -> bool:
        """Stop the worker thread cleanly; set ``permanent=True`` on final teardown."""
        if wait_ms < 0:
            raise ValueError("wait_ms must be non-negative")
        with QMutexLocker(self._mutex):
            self._pending_frame = None
            if permanent:
                self._permanent_stop = True
            if not self._started:
                self._stop_requested = permanent
                return True
            self._stop_requested = True
            self._work_available.wakeAll()
        if QThread.currentThread() == self:
            return False
        return self.wait(wait_ms)

    def run(self) -> None:
        try:
            while True:
                with QMutexLocker(self._mutex):
                    while not self._stop_requested and self._pending_frame is None:
                        self._work_available.wait(self._mutex)
                    if self._stop_requested:
                        return
                    frame = self._pending_frame
                    track = self._pending_track
                    req_id = self._pending_request_id
                    self._pending_frame = None

                try:
                    result = self._engine.infer(frame, track=track, request_id=req_id)
                except Exception as exc:  # pragma: no cover - defensive worker guard
                    with QMutexLocker(self._mutex):
                        stopped = self._stop_requested
                    if not stopped:
                        self.inference_error.emit(str(exc))
                else:
                    with QMutexLocker(self._mutex):
                        stopped = self._stop_requested
                    if not stopped:
                        self.inference_ready.emit(result)
        finally:
            with QMutexLocker(self._mutex):
                self._started = False
                if not self._permanent_stop:
                    self._stop_requested = False


def draw_detections_on_qimage(
    raw_image: QImage,
    boxes: Sequence[BoundingBox],
    fps_text: str = "",
) -> QImage:
    """Return a NEW ``QImage`` with YOLO bounding boxes and track IDs drawn.

    The input ``raw_image`` is never mutated so raw evidence SHA-256 remains intact.
    """
    annotated = raw_image.copy()
    if annotated.isNull():
        return annotated

    painter = QPainter(annotated)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    img_w = annotated.width()
    img_h = annotated.height()
    dense_mode = len(boxes) > 30

    for idx, box in enumerate(boxes, start=1):
        lower_label = box.label.lower()
        if "rotten" in lower_label:
            color = QColor(239, 68, 68)
            fill = QColor(239, 68, 68, 38)
        elif "bruised" in lower_label:
            color = QColor(245, 158, 11)
            fill = QColor(245, 158, 11, 38)
        elif lower_label == "apple":
            color = QColor(59, 130, 246)
            fill = QColor(59, 130, 246, 24)
        else:
            color = QColor(16, 185, 129)
            fill = QColor(16, 185, 129, 38)

        painter.setPen(QPen(color, 1 if dense_mode else 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(box.x1, box.y1, box.width, box.height, 4, 4)

        if dense_mode:
            tag = f"{idx}"
            tag_w = min(26, max(16, len(tag) * 7 + 6))
            tag_x = max(0, min(img_w - tag_w, box.x1))
            tag_y = max(0, min(img_h - 14, box.y1))
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(tag_x, tag_y, tag_w, 13)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Inter", 6, QFont.Weight.Bold))
            painter.drawText(tag_x + 2, tag_y + 10, tag)
        else:
            track_prefix = f"#{box.track_id} " if box.track_id is not None else ""
            caption = f" {track_prefix}{box.label} {box.confidence:.2f} "
            badge_w = min(max(78, len(caption) * 6 + 6), min(160, max(24, img_w)))
            badge_x = max(0, min(img_w - badge_w, box.x1))
            badge_y = max(2, min(max(2, img_h - 17), box.y1 - 18))

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_x, badge_y, badge_w, 17, 3, 3)

            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Inter", 7, QFont.Weight.Bold))
            painter.drawText(badge_x + 3, badge_y + 12, caption)

    if fps_text and img_w >= 48 and img_h >= 28:
        font = QFont("Inter", 8 if img_w < 480 else 9, QFont.Weight.Medium)
        painter.setFont(font)
        text_w = min(img_w - 16, painter.fontMetrics().horizontalAdvance(fps_text) + 12)
        text_h = 20
        pos_x = max(8, img_w - text_w - 8)
        pos_y = 8
        painter.setBrush(QColor(15, 23, 42, 185))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pos_x, pos_y, text_w, text_h, 4, 4)
        painter.setPen(QColor(226, 232, 240))
        painter.drawText(pos_x + 6, pos_y + 14, fps_text)

    painter.end()
    return annotated

