"""Simulated AI outputs for the UI-shell phase.

Nothing here runs YOLO or Qwen-VL. Every result is flagged
``is_simulated=True`` so the UI can label it clearly.

``assess_quality`` is a placeholder for the Python rule engine (D-023). It
reads thresholds from ``Product.criteria`` (mock catalog values) and must be
replaced by the real engine reading criteria from the database. The order in
which rules are evaluated is not yet confirmed by the user.
"""

import random
from typing import Optional

from agroscan.models.inspection_models import (
    AiRecommendation,
    DetectionResult,
    Product,
    QualityAssessmentResult,
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


def simulate_deep_analysis(product: Product, detection: DetectionResult) -> str:
    """Nhận xét kiểu Qwen-VL giả lập, tách quan sát / nhận định / độ chắc chắn."""
    defects = [
        f"{count} {cls}" for cls, count in detection.class_counts.items()
        if cls != product.detect_classes[0] and count > 0
    ]
    observed = ", ".join(defects) if defects else "no visible defects"
    return (
        f"Observations: {detection.total_objects} {product.name.lower()} units visible; "
        f"{observed}.\n"
        "Assessment: surface discoloration is consistent with handling bruises; "
        "no mold texture identified.\n"
        f"Uncertainty: moderate — mean detector confidence "
        f"{detection.mean_confidence:.0%}, partial occlusion at box edges.\n"
        "Suggestion: rotate the top layer and capture one more image if in doubt."
    )
