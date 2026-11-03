"""Simulated AI outputs for the UI-shell phase.

Nothing here runs YOLO or Qwen-VL. Every result is flagged
``is_simulated=True`` so the UI can label it clearly.

``assess_quality`` is a placeholder for the Python rule engine (D-023). It
reads thresholds from ``Product.criteria`` (mock catalog values) and must be
replaced by the real engine reading criteria from the database. The order in
which rules are evaluated is not yet confirmed by the user.
"""

import json
import random
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from agroscan.models.inspection_models import (
    AiRecommendation,
    DetectionResult,
    InspectionSession,
    Product,
    QualityAssessmentResult,
)
from agroscan.models.vlm_models import (
    SCHEMA_VERSION,
    VlmAnalysis,
    VlmErrorCode,
    VlmSchemaError,
    parse_vlm_response,
)


def simulate_frame_counts(product: Product, rng: Optional[random.Random] = None) -> dict[str, int]:
    """Số quả theo lớp trong một khung hình video giả lập (chỉ số realtime, D-026)."""
    rng = rng or random.Random()
    counts = {cls: 0 for cls in product.detect_classes}
    first, *others = product.detect_classes
    counts[first] = rng.randint(14, 22)
    for cls in others:
        counts[cls] = rng.choice([0, 0, 1, 1, 2, 3])
    return counts


def simulate_detection(product: Product, rng: Optional[random.Random] = None) -> DetectionResult:
    """Kết quả YOLO giả lập trên ảnh tĩnh."""
    rng = rng or random.Random()
    first, *others = product.detect_classes
    counts = {first: rng.randint(16, 28)}
    for cls in others:
        is_severe = any(c.defect_class == cls and c.is_critical for c in product.criteria)
        counts[cls] = (1 if rng.random() < 0.15 else 0) if is_severe else rng.randint(0, 4)
    total = sum(counts.values())
    if rng.random() < 0.12:
        confidence = rng.uniform(0.40, 0.58)   # Ảnh "khó" → Needs Review
    else:
        confidence = rng.uniform(0.72, 0.95)
    return DetectionResult(total, counts, round(confidence, 2))


def assess_quality(product: Product, detection: DetectionResult) -> QualityAssessmentResult:
    """Placeholder rule engine (D-023) — xem docstring của module."""
    ratios = {c.defect_class: detection.ratio(c.defect_class) for c in product.criteria}
    reasons: list[str] = []

    for criterion in product.criteria:
        count = detection.class_counts.get(criterion.defect_class, 0)
        if criterion.is_critical and count > 0:
            reasons.append(f"Critical defect detected: {criterion.defect_class} ({count}).")
    for criterion in product.criteria:
        ratio = ratios[criterion.defect_class]
        if not criterion.is_critical and ratio > criterion.max_ratio:
            reasons.append(
                f"{criterion.defect_class.capitalize()} ratio {ratio:.0%} exceeds "
                f"limit {criterion.max_ratio:.0%}."
            )
    if reasons:
        return QualityAssessmentResult(AiRecommendation.FAIL, reasons, ratios)

    if detection.total_objects < product.min_objects:
        reasons.append(
            f"Only {detection.total_objects} objects detected "
            f"(minimum {product.min_objects})."
        )
    if detection.mean_confidence < product.min_confidence:
        reasons.append(
            f"Detection confidence {detection.mean_confidence:.0%} is below "
            f"{product.min_confidence:.0%}."
        )
    if reasons:
        return QualityAssessmentResult(AiRecommendation.NEEDS_REVIEW, reasons, ratios)

    return QualityAssessmentResult(
        AiRecommendation.PASS, ["All defect ratios are within limits."], ratios
    )


class VlmScenario(Enum):
    """Demo outcomes of a simulated Qwen-VL call, used to show every panel state."""

    NORMAL              = "Normal result"
    LABEL_UNREADABLE    = "Partial — label unreadable"
    IMAGE_UNUSABLE      = "Error — image unusable"
    TIMEOUT             = "Error — timeout"
    SERVICE_UNAVAILABLE = "Error — service unavailable"
    INVALID_RESPONSE    = "Error — invalid response"


_SEVERITY_BY_CLASS = {"rotten": "critical", "moldy": "critical", "bruised": "minor"}


def _simulated_payload(
    session: InspectionSession,
    detection: DetectionResult,
    scenario: VlmScenario,
    rng: random.Random,
) -> dict:
    """Schema-1.0 body the Qwen-VL service would return (D-017)."""
    product = session.product
    now = datetime.now()
    base = {
        "schema_version": SCHEMA_VERSION,
        "request_id":     f"vlm-{now:%Y%m%d%H%M%S}-{rng.randint(100, 999)}",
        "model":          "qwen2.5-vl-7b-instruct (simulated)",
        "latency_ms":     rng.randint(900, 2400),
        "analyzed_at":    now.isoformat(timespec="seconds"),
    }
    if scenario == VlmScenario.IMAGE_UNUSABLE:
        return {**base, "status": "error", "error": {
            "code": "IMAGE_UNUSABLE",
            "message": "The image is too blurred to analyze — the box surface is not in focus.",
            "retryable": False,
        }}

    critical = {c.defect_class for c in product.criteria if c.is_critical}
    defects = []
    for cls, count in detection.class_counts.items():
        if cls == product.detect_classes[0] or count == 0:
            continue
        severity = "critical" if cls in critical else _SEVERITY_BY_CLASS.get(cls, "major")
        defects.append({
            "defect_class": cls,
            "count":        count,
            "severity":     severity,
            "confidence":   round(rng.uniform(0.62, 0.93), 2),
            "description":  (
                "Dark soft patches with sunken skin." if severity == "critical"
                else "Surface discoloration consistent with handling bruises."
            ),
            "region": [round(rng.uniform(0.05, 0.6), 2), round(rng.uniform(0.05, 0.6), 2), 0.2, 0.2],
        })

    supplier = session.order.supplier
    if rng.random() < 0.15:
        supplier = "Unknown Packer Ltd."   # Demo: label differs from the order
    label_readable = scenario != VlmScenario.LABEL_UNREADABLE
    ocr_fields = [
        {"key": "box_code",    "value": session.box_code.text,                  "confidence": 0.97},
        {"key": "supplier",    "value": supplier,                               "confidence": 0.88},
        {"key": "packed_date", "value": f"{now - timedelta(days=2):%Y-%m-%d}", "confidence": 0.81},
        {"key": "lot_number",  "value": f"LOT-{rng.randint(1000, 9999)}",       "confidence": 0.74},
        {"key": "origin",      "value": "Viet Nam",                             "confidence": 0.92},
    ] if label_readable else []

    uncertainty_score = round(min(1.0, 1.0 - detection.mean_confidence + rng.uniform(0.0, 0.15)), 2)
    level = "low" if uncertainty_score < 0.3 else "medium" if uncertainty_score < 0.55 else "high"
    reasons = [f"Mean detector confidence {detection.mean_confidence:.0%}."]
    if level != "low":
        reasons.append("Partial occlusion at the box edges.")
    if not label_readable:
        reasons.append("Box label could not be read.")

    observed = ", ".join(f"{d['count']} {d['defect_class']}" for d in defects) or "no visible defects"
    return {
        **base,
        "status": "ok" if label_readable else "partial",
        "defects": defects,
        "ocr": {
            "readable": label_readable,
            "fields":   ocr_fields,
            "raw_text": "\n".join(f["value"] for f in ocr_fields),
        },
        "observations": [
            f"{detection.total_objects} {product.name.lower()} units visible.",
            f"Defects seen: {observed}.",
        ],
        "assessment": (
            "Critical decay is present; the box is unlikely to meet the criteria."
            if any(d["severity"] == "critical" for d in defects)
            else "Surface marks are consistent with handling; no mold texture identified."
        ),
        "uncertainty": {"level": level, "score": uncertainty_score, "reasons": reasons},
        "suggestion": (
            "Rotate the top layer and capture one more image."
            if level != "low" else "No further action needed."
        ),
        "warnings": [] if label_readable else ["OCR skipped: label glare or out of frame."],
        "error": None,
    }


def simulate_deep_analysis(
    session: InspectionSession,
    detection: DetectionResult,
    scenario: VlmScenario = VlmScenario.NORMAL,
    timeout_s: int = 30,
    rng: Optional[random.Random] = None,
) -> VlmAnalysis:
    """Simulated Qwen-VL client call. Always returns a ``VlmAnalysis`` (never raises).

    Transport failures become client-side ERROR results, and the server body is
    validated with ``parse_vlm_response`` exactly as the real client must do.
    """
    rng = rng or random.Random()
    if scenario == VlmScenario.TIMEOUT:
        result = VlmAnalysis.client_error(
            VlmErrorCode.TIMEOUT, f"The AI service did not respond within {timeout_s} s."
        )
    elif scenario == VlmScenario.SERVICE_UNAVAILABLE:
        result = VlmAnalysis.client_error(
            VlmErrorCode.SERVICE_UNAVAILABLE,
            "Cannot reach the AI service. Check the server address in Settings.",
        )
    else:
        payload = _simulated_payload(session, detection, scenario, rng)
        if scenario == VlmScenario.INVALID_RESPONSE:
            payload["uncertainty"] = {"level": "unsure", "score": 1.7}   # Violates schema
        try:
            result = parse_vlm_response(json.dumps(payload))
        except VlmSchemaError as exc:
            result = VlmAnalysis.client_error(
                VlmErrorCode.INVALID_RESPONSE, f"The AI service returned invalid data — {exc}"
            )
    result.is_simulated = True
    return result
