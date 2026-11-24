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

from dataclasses import dataclass, field
import math
from pathlib import Path
import time
from typing import Optional, Sequence, Union

import cv2
import numpy as np
import onnxruntime as ort
from PySide6.QtCore import QMutex, QMutexLocker, QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from agroscan.models.inspection_models import DetectionResult, Product

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WEIGHTS_DIR = REPO_ROOT / "models" / "weights"
FALLBACK_WEIGHTS_DIR = REPO_ROOT / "models_ai"
DEFAULT_CLASSES: tuple[str, ...] = ("fresh", "bruised", "rotten")


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
    if direct.is_absolute() and direct.is_file():
        return direct

    dirs: list[Path] = []
    if search_dirs:
        dirs.extend(Path(d) for d in search_dirs)
    dirs.extend([DEFAULT_WEIGHTS_DIR, FALLBACK_WEIGHTS_DIR, REPO_ROOT])

    candidates = [cleaned]
    if Path(cleaned).name != "fruit_defect.onnx":
        candidates.append("fruit_defect.onnx")

    for base in dirs:
        for candidate in candidates:
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
    ) -> None:
        self._class_names = list(class_names) if class_names else list(DEFAULT_CLASSES)
        self._conf_threshold = conf_threshold
        self._iou_threshold = iou_threshold
        self._session: Optional[ort.InferenceSession] = None
        self._input_name: str = "images"
        self._model_path: Optional[Path] = None
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

    def reset_tracker(self) -> None:
        with QMutexLocker(self._lock):
            self._tracker.reset()

    def load_model(
        self,
        model_file_or_path: Union[Path, str],
        class_names: Optional[Sequence[str]] = None,
    ) -> bool:
        """Load an `.onnx` model into `onnxruntime.InferenceSession`."""
        with QMutexLocker(self._lock):
            if class_names:
                self._class_names = [str(c) for c in class_names]
            resolved = resolve_model_path(str(model_file_or_path))
            if resolved is None or not resolved.is_file():
                self._session = None
                self._model_path = None
                return False

            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = 2
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            self._session = ort.InferenceSession(
                str(resolved),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )
            inputs = self._session.get_inputs()
            self._input_name = inputs[0].name if inputs else "images"
            self._model_path = resolved
            self._tracker.reset()
            return True

    def load_for_product(self, product: Product) -> bool:
        """Load the `.onnx` model configured for ``product`` (D-024)."""
        return self.load_model(product.model_file, class_names=product.detect_classes)

    def preprocess(
        self, rgb_image: np.ndarray
    ) -> tuple[np.ndarray, float, int, int]:
        """Letterbox resize `(H, W, 3)` RGB uint8 array to `(1, 3, 640, 640)` float32."""
        orig_h, orig_w = rgb_image.shape[:2]
        target_w, target_h = self.INPUT_SIZE
        scale = min(target_w / max(1, orig_w), target_h / max(1, orig_h))
        new_w = int(round(orig_w * scale))
        new_h = int(round(orig_h * scale))

        resized = cv2.resize(rgb_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_h, target_w, 3), (18, 22, 28), dtype=np.uint8)
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
        preds = raw_output[0] if raw_output.ndim == 3 else raw_output
        # YOLOv8 shape is (4 + num_classes, num_anchors) -> transpose to (num_anchors, 4 + num_classes)
        if preds.shape[0] < preds.shape[1]:
            preds = preds.T

        if preds.shape[1] < 5:
            empty_counts = {cls: 0 for cls in self._class_names}
            return [], DetectionResult(0, empty_counts, 0.0, is_simulated=False)

        boxes_xywh = preds[:, :4]
        class_scores = preds[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        max_scores = class_scores[np.arange(len(class_scores)), class_ids]

        mask = max_scores >= self._conf_threshold
        boxes_xywh = boxes_xywh[mask]
        class_ids = class_ids[mask]
        max_scores = max_scores[mask]

        candidates: list[BoundingBox] = []
        inv_scale = 1.0 / max(scale, 1e-6)
        for (cx, cy, bw, bh), cls_id, score in zip(boxes_xywh, class_ids, max_scores):
            x1 = int(round((cx - bw * 0.5 - pad_x) * inv_scale))
            y1 = int(round((cy - bh * 0.5 - pad_y) * inv_scale))
            x2 = int(round((cx + bw * 0.5 - pad_x) * inv_scale))
            y2 = int(round((cy + bh * 0.5 - pad_y) * inv_scale))

            x1 = max(0, min(orig_w - 1, x1))
            y1 = max(0, min(orig_h - 1, y1))
            x2 = max(x1 + 1, min(orig_w, x2))
            y2 = max(y1 + 1, min(orig_h, y2))

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
        self._pending_frame: Optional[QImage] = None
        self._pending_track: bool = True
        self._pending_request_id: int = 0
        self._stop_requested: bool = False

    def submit_frame(
        self, frame: QImage, track: bool = True, request_id: int = 0
    ) -> None:
        """Queue the latest frame for background inference (drops stale intermediate frames)."""
        if frame.isNull():
            return
        with QMutexLocker(self._mutex):
            self._pending_frame = frame.copy()
            self._pending_track = track
            self._pending_request_id = request_id
            self._stop_requested = False
        if not self.isRunning():
            self.start()

    def stop_worker(self, wait_ms: int = 1000) -> None:
        with QMutexLocker(self._mutex):
            self._pending_frame = None
            self._stop_requested = True
        if self.isRunning():
            self.wait(wait_ms)

    def run(self) -> None:
        while True:
            with QMutexLocker(self._mutex):
                if self._stop_requested or self._pending_frame is None:
                    return
                frame = self._pending_frame
                track = self._pending_track
                req_id = self._pending_request_id
                self._pending_frame = None

            try:
                result = self._engine.infer(frame, track=track, request_id=req_id)
                self.inference_ready.emit(result)
            except Exception as exc:  # pragma: no cover - defensive worker guard
                self.inference_error.emit(str(exc))


def draw_detections_on_qimage(
    raw_image: QImage,
    boxes: Sequence[BoundingBox],
    fps_text: str = "",
) -> QImage:
    """Return a NEW ``QImage`` with YOLO bounding boxes and track IDs drawn.

    The input ``raw_image`` is never mutated so raw evidence SHA-256 remains intact.
    """
    annotated = raw_image.copy()
    painter = QPainter(annotated)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    for box in boxes:
        lower_label = box.label.lower()
        if "rotten" in lower_label:
            color = QColor(239, 68, 68)
            fill = QColor(239, 68, 68, 38)
        elif "bruised" in lower_label:
            color = QColor(245, 158, 11)
            fill = QColor(245, 158, 11, 38)
        else:
            color = QColor(16, 185, 129)
            fill = QColor(16, 185, 129, 38)

        painter.setPen(QPen(color, 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(box.x1, box.y1, box.width, box.height, 5, 5)

        track_prefix = f"#{box.track_id} " if box.track_id is not None else ""
        caption = f" {track_prefix}{box.label} {box.confidence:.2f} "
        badge_w = min(max(78, len(caption) * 6 + 6), 140)
        badge_y = max(2, box.y1 - 18)

        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(box.x1, badge_y, badge_w, 17, 3, 3)

        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Inter", 7, QFont.Weight.Bold))
        painter.drawText(box.x1 + 3, badge_y + 12, caption)

    if fps_text:
        painter.setPen(QColor(148, 163, 184))
        painter.setFont(QFont("Inter", 9, QFont.Weight.Medium))
        painter.drawText(550, 75, fps_text)

    painter.end()
    return annotated

