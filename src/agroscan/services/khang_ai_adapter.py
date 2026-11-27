"""Integration adapter bridging Khang's local ONNX detectors & ResNet18 pre-check gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Optional, Union

import numpy as np
from PySide6.QtGui import QImage

from agroscan.services.container_classifier import ContainerCheckResult, ContainerClassifier
from agroscan.services.yolo_engine import DEFAULT_WEIGHTS_DIR, YoloEngine

MANIFEST_SCHEMA = "agroscan.khang-ai-onnx-bundle/1"
MANIFEST_SCHEMA_V2 = "agroscan.khang-ai-onnx-bundle/2"
_SUPPORTED_SCHEMAS = (MANIFEST_SCHEMA, MANIFEST_SCHEMA_V2)
_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_manifest_relative(ref: object, root: Path, field_name: str) -> Path:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError(f"Manifest missing {field_name}.")
    normalized = ref.strip().replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        raise ValueError(f"Manifest path {field_name} must be relative.")
    resolved_root = root.resolve()
    candidate = (resolved_root / normalized).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Manifest path {field_name} escapes weights directory.") from exc
    return candidate


def resolve_khang_manifest(manifest_path: Optional[Union[Path, str]] = None) -> Path:
    """Return path to ``khang_ai_manifest.json`` under ``models/weights``."""
    if manifest_path is not None:
        return Path(manifest_path).resolve()
    return (DEFAULT_WEIGHTS_DIR / "khang_ai_manifest.json").resolve()


def load_khang_manifest(manifest_path: Optional[Union[Path, str]] = None) -> tuple[dict, Path]:
    """Load and validate schema (v1 or v2) of ``khang_ai_manifest.json``."""
    path = resolve_khang_manifest(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"Khang AI ONNX manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") not in _SUPPORTED_SCHEMAS:
        raise ValueError("Unsupported Khang AI ONNX manifest schema.")
    return data, path.parent


def _get_product_detectors(manifest: dict, product_code: str = "apple") -> dict:
    """Extract detector presets dict for ``product_code`` from v1 or v2 manifest."""
    normalized = (product_code or "apple").strip().lower()
    if manifest.get("schema") == MANIFEST_SCHEMA_V2:
        products = manifest.get("products")
        if not isinstance(products, dict):
            return {}
        prod_entry = products.get(normalized)
        if not isinstance(prod_entry, dict):
            return {}
        detectors = prod_entry.get("detectors")
        return detectors if isinstance(detectors, dict) else {}

    # v1 schema covers Apple detectors only.
    if normalized != "apple":
        return {}
    detectors = manifest.get("detectors")
    return detectors if isinstance(detectors, dict) else {}


def load_product_detector_preset(
    engine: YoloEngine,
    product_code: str = "apple",
    preset: str = "open_box",
    *,
    manifest_path: Optional[Union[Path, str]] = None,
) -> dict:
    """Verify SHA-256 and load the requested product ONNX preset into ``YoloEngine``."""
    normalized_product = (product_code or "apple").strip().lower()
    manifest, base_dir = load_khang_manifest(manifest_path)
    detectors = _get_product_detectors(manifest, normalized_product)
    if preset not in detectors:
        raise ValueError(
            f"Unknown Khang detector preset {preset!r} for product {normalized_product!r}"
        )
    entry = detectors[preset]
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid detector preset entry for {normalized_product}.{preset!r}")

    expected_sha = entry.get("sha256")
    if not isinstance(expected_sha, str) or not _HEX64_RE.fullmatch(expected_sha.strip()):
        raise ValueError(f"Detector preset {preset!r} missing valid 64-hex sha256.")

    model_path = _resolve_manifest_relative(
        entry.get("model_file"),
        base_dir,
        f"detectors.{normalized_product}.{preset}.model_file",
    )
    if not model_path.is_file():
        raise FileNotFoundError(f"Detector ONNX not found: {model_path}")
    actual_sha = _sha256_file(model_path)
    if actual_sha.lower() != expected_sha.strip().lower():
        raise ValueError(f"Detector ONNX SHA-256 mismatch for preset {preset!r}.")

    fill_raw = entry.get("letterbox_fill", [114, 114, 114])
    fill = (int(fill_raw[0]), int(fill_raw[1]), int(fill_raw[2]))
    classes = [str(c) for c in entry.get("classes", [normalized_product])]
    ok = engine.load_model(
        model_path,
        class_names=classes,
        conf_threshold=float(entry.get("confidence", 0.25)),
        iou_threshold=float(entry.get("nms_iou", 0.55)),
        max_det=int(entry.get("max_det", 1000)),
        letterbox_fill=fill,
    )
    if not ok:
        raise RuntimeError(f"Failed to load ONNX session for {model_path.name}")
    return dict(entry, model_path=str(model_path), preset=preset, product=normalized_product)


def load_apple_detector_preset(
    engine: YoloEngine,
    preset: str = "open_box",
    *,
    manifest_path: Optional[Union[Path, str]] = None,
) -> dict:
    """Verify SHA-256 and load the requested Apple ONNX preset into ``YoloEngine``."""
    return load_product_detector_preset(
        engine,
        product_code="apple",
        preset=preset,
        manifest_path=manifest_path,
    )


class KhangAiAdapter:
    """Lazy, thread-safe coordinator for Khang's local ONNX detectors and ResNet18 pre-check."""

    def __init__(self, manifest_path: Optional[Union[Path, str]] = None) -> None:
        self._manifest_path = manifest_path
        self._lock = threading.Lock()
        self._classifier: Optional[ContainerClassifier] = None

    def is_preset_available(self, product_code: str = "apple", preset: str = "open_box") -> bool:
        """Return True only if manifest is valid AND the requested ONNX weight file exists on disk."""
        try:
            manifest, base_dir = load_khang_manifest(self._manifest_path)
            detectors = _get_product_detectors(manifest, product_code)
            entry = detectors.get(preset)
            if not isinstance(entry, dict):
                return False
            model_path = _resolve_manifest_relative(
                entry.get("model_file"),
                base_dir,
                f"detectors.{product_code}.{preset}.model_file",
            )
            return model_path.is_file()
        except Exception:
            return False

    def available_presets(self, product_code: str = "apple") -> list[str]:
        """Return preset names whose ONNX weights actually exist on disk."""
        try:
            manifest, _ = load_khang_manifest(self._manifest_path)
        except Exception:
            return []
        detectors = _get_product_detectors(manifest, product_code)
        return [
            str(preset)
            for preset in detectors.keys()
            if self.is_preset_available(product_code, str(preset))
        ]

    def is_available(self, product_code: str = "apple") -> bool:
        """Return True only when at least one ONNX detector for ``product_code`` exists on disk."""
        return bool(self.available_presets(product_code))

    def is_classifier_available(self) -> bool:
        """Return True when the classifier ONNX file declared in manifest exists on disk."""
        try:
            manifest, base_dir = load_khang_manifest(self._manifest_path)
            cfg = manifest.get("classifier")
            if not isinstance(cfg, dict):
                return False
            model_path = _resolve_manifest_relative(
                cfg.get("model_file"), base_dir, "classifier.model_file"
            )
            return model_path.is_file()
        except Exception:
            return False

    def load_detector_preset(
        self,
        engine: YoloEngine,
        preset: str = "open_box",
        *,
        product_code: str = "apple",
    ) -> dict:
        return load_product_detector_preset(
            engine,
            product_code=product_code,
            preset=preset,
            manifest_path=self._manifest_path,
        )

    def _get_classifier(self) -> ContainerClassifier:
        with self._lock:
            if self._classifier is None:
                manifest, base_dir = load_khang_manifest(self._manifest_path)
                cfg = manifest.get("classifier")
                if not isinstance(cfg, dict):
                    raise ValueError("Manifest missing classifier configuration.")
                model_path = _resolve_manifest_relative(
                    cfg.get("model_file"), base_dir, "classifier.model_file"
                )
                fill_raw = cfg.get("letterbox_fill", [114, 114, 114])
                self._classifier = ContainerClassifier(
                    model_path=model_path,
                    expected_sha256=str(cfg.get("sha256", "")),
                    labels=cfg.get("labels", ["apple", "other"]),
                    image_size=int(cfg.get("image_size", 224)),
                    letterbox_fill=(int(fill_raw[0]), int(fill_raw[1]), int(fill_raw[2])),
                    mean=cfg.get("mean", [0.485, 0.456, 0.406]),
                    std=cfg.get("std", [0.229, 0.224, 0.225]),
                    temperature=float(cfg.get("temperature", 0.5)),
                    min_confidence=float(cfg.get("min_confidence", 0.85)),
                    development_only=bool(cfg.get("development_only", True)),
                )
            return self._classifier

    def check_container(
        self,
        frame: Union[QImage, np.ndarray],
        *,
        expected_product: str = "apple",
        scene_condition: str = "single_product",
    ) -> ContainerCheckResult:
        """Run advisory ResNet18 check, returning ``UNSUPPORTED_PRODUCT`` if unconfigured."""
        expected_norm = (expected_product or "").strip().lower()
        manifest, _base_dir = load_khang_manifest(self._manifest_path)
        cfg = manifest.get("classifier")
        if not isinstance(cfg, dict):
            return ContainerCheckResult(
                predicted_label="unknown",
                confidence=0.0,
                probabilities={},
                status="REVIEW_REQUIRED",
                reason="UNSUPPORTED_PRODUCT",
                model_file="",
                development_only=True,
                can_make_final_decision=False,
            )
        labels = cfg.get("labels", ["apple", "other"])
        supported = {
            str(lbl).strip().lower()
            for lbl in labels
            if str(lbl).strip().lower() != "other"
        }
        if not expected_norm or expected_norm not in supported:
            raw_model = str(cfg.get("model_file") or "")
            return ContainerCheckResult(
                predicted_label="unknown",
                confidence=0.0,
                probabilities={},
                status="REVIEW_REQUIRED",
                reason="UNSUPPORTED_PRODUCT",
                model_file=Path(raw_model).name if raw_model else "",
                development_only=bool(cfg.get("development_only", True)),
                can_make_final_decision=False,
            )
        clf = self._get_classifier()
        return clf.classify(frame, expected_product=expected_norm, scene_condition=scene_condition)

    def check_apple_container(
        self,
        frame: Union[QImage, np.ndarray],
        *,
        scene_condition: str = "single_product",
    ) -> ContainerCheckResult:
        return self.check_container(
            frame, expected_product="apple", scene_condition=scene_condition
        )
