"""Pure-ONNX ResNet18 whole-container binary pre-check classifier (apple vs other)."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import threading
from typing import Sequence, Union

import numpy as np
import onnxruntime as ort
from PIL import Image
from PySide6.QtGui import QImage

from agroscan.services.yolo_engine import qimage_to_rgb_array

_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class ContainerCheckResult:
    """Advisory container scene pre-check output from ResNet18 ONNX."""

    predicted_label: str
    confidence: float
    probabilities: dict[str, float]
    status: str  # MATCH | MISMATCH_ADVISORY | REVIEW_REQUIRED
    reason: str
    model_file: str
    development_only: bool = True
    can_make_final_decision: bool = False


class ContainerClassifier:
    """SHA-256 verified ONNX Runtime ResNet18 classifier for whole-container apple screening."""

    def __init__(
        self,
        model_path: Union[Path, str],
        expected_sha256: str,
        *,
        labels: Sequence[str] = ("apple", "other"),
        image_size: int = 224,
        letterbox_fill: tuple[int, int, int] = (114, 114, 114),
        mean: Sequence[float] = (0.485, 0.456, 0.406),
        std: Sequence[float] = (0.229, 0.224, 0.225),
        temperature: float = 0.5,
        min_confidence: float = 0.85,
        development_only: bool = True,
    ) -> None:
        resolved = Path(model_path).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Classifier ONNX model not found: {resolved}")
        if not isinstance(expected_sha256, str) or not _HEX64_RE.fullmatch(expected_sha256.strip()):
            raise ValueError("Classifier expected_sha256 must be a 64-character hex string.")
        actual_sha = _sha256_file(resolved)
        if actual_sha.lower() != expected_sha256.strip().lower():
            raise ValueError(f"Classifier ONNX SHA-256 mismatch for {resolved.name}.")

        self._labels = [str(lbl) for lbl in labels]
        if len(self._labels) < 2 or len(set(self._labels)) != len(self._labels):
            raise ValueError("Classifier labels must contain at least 2 unique entries.")
        self._image_size = int(image_size)
        if self._image_size <= 0:
            raise ValueError("Classifier image_size must be positive.")
        if temperature <= 0 or not math.isfinite(temperature):
            raise ValueError("Classifier temperature must be finite and positive.")
        if not 0.0 <= min_confidence <= 1.0 or not math.isfinite(min_confidence):
            raise ValueError("Classifier min_confidence must be in [0, 1].")

        self._fill = (int(letterbox_fill[0]), int(letterbox_fill[1]), int(letterbox_fill[2]))
        self._mean = np.array(mean, dtype=np.float32)
        self._std = np.array(std, dtype=np.float32)
        if self._mean.shape != (3,) or self._std.shape != (3,) or np.any(self._std <= 0):
            raise ValueError("Classifier mean and std must have length 3 with positive std.")

        self._temperature = float(temperature)
        self._min_confidence = float(min_confidence)
        self._development_only = bool(development_only)
        self._model_path = resolved
        self._lock = threading.Lock()

        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 2
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            str(resolved),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        )
        inputs = self._session.get_inputs()
        self._input_name = inputs[0].name if inputs else "images"

    @property
    def labels(self) -> list[str]:
        return list(self._labels)

    @property
    def model_path(self) -> Path:
        return self._model_path

    @property
    def development_only(self) -> bool:
        return self._development_only

    def preprocess(self, frame: Union[QImage, np.ndarray]) -> np.ndarray:
        """Letterbox RGB frame to `(1, 3, S, S)` float32 tensor matching PyTorch transform."""
        rgb = qimage_to_rgb_array(frame) if isinstance(frame, QImage) else np.asarray(frame)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            raise ValueError("Expected RGB image array with 3 channels.")
        if rgb.shape[2] > 3:
            rgb = rgb[:, :, :3]
        orig_h, orig_w = rgb.shape[:2]
        if orig_h <= 0 or orig_w <= 0:
            raise ValueError("Image must have positive dimensions.")

        size = self._image_size
        scale = min(size / orig_w, size / orig_h)
        new_w = max(1, min(size, int(round(orig_w * scale))))
        new_h = max(1, min(size, int(round(orig_h * scale))))
        pil_rgb = Image.fromarray(np.ascontiguousarray(rgb, dtype=np.uint8), mode="RGB")
        resized = pil_rgb.resize((new_w, new_h), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (size, size), self._fill)
        canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2))

        normalized = (np.asarray(canvas, dtype=np.float32) / 255.0 - self._mean) / self._std
        tensor = np.transpose(normalized, (2, 0, 1))[np.newaxis, ...]
        return np.ascontiguousarray(tensor, dtype=np.float32)

    def classify(
        self,
        frame: Union[QImage, np.ndarray],
        *,
        expected_product: str = "apple",
        scene_condition: str = "single_product",
    ) -> ContainerCheckResult:
        """Run advisory container pre-check with temperature calibration and confidence guard."""
        if scene_condition not in (None, "single_product", "mixed_or_uncertain"):
            raise ValueError(f"Unknown scene_condition: {scene_condition!r}")

        tensor = self.preprocess(frame)
        with self._lock:
            outputs = self._session.run(None, {self._input_name: tensor})

        logits = np.asarray(outputs[0], dtype=np.float32).reshape(-1)
        if logits.shape[0] != len(self._labels):
            raise ValueError("Classifier output dimension mismatch.")
        if not bool(np.isfinite(logits).all()):
            raise ValueError("Non-finite classifier logits produced.")

        scaled = logits / self._temperature
        shifted = scaled - float(np.max(scaled))
        exp = np.exp(shifted)
        probs = exp / float(np.sum(exp))
        if not bool(np.isfinite(probs).all()):
            raise ValueError("Non-finite classifier probabilities produced.")

        best_idx = int(np.argmax(probs))
        top_label = self._labels[best_idx]
        top_conf = float(probs[best_idx])
        prob_map = {lbl: round(float(probs[i]), 6) for i, lbl in enumerate(self._labels)}

        if scene_condition != "single_product":
            status, reason = "REVIEW_REQUIRED", "SCENE_CONDITION_NOT_CONFIRMED"
        elif top_conf < self._min_confidence:
            status, reason = "REVIEW_REQUIRED", "LOW_CONFIDENCE"
        elif top_label.lower() == expected_product.strip().lower():
            status, reason = "MATCH", ""
        else:
            status, reason = "MISMATCH_ADVISORY", "PREDICTED_OTHER_OR_MISMATCH"

        return ContainerCheckResult(
            predicted_label=top_label,
            confidence=round(top_conf, 6),
            probabilities=prob_map,
            status=status,
            reason=reason,
            model_file=self._model_path.name,
            development_only=self._development_only,
            can_make_final_decision=False,
        )
