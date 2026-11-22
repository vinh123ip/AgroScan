"""Python rule engine — the business arbiter of AgroScan (D-007, D-023, step 6).

YOLO only detects, counts and classifies; Qwen-VL only explains on demand. This
module turns a still-image ``DetectionResult`` plus the product criteria stored
in the database into one system recommendation:

1. A critical defect class (``is_critical``) with at least one detection, or a
   non-critical defect ratio above its ``max_ratio``  ->  ``FAIL``.
2. Otherwise too few objects (``Product.min_objects``) or a mean detector
   confidence below ``Product.min_confidence``  ->  ``NEEDS_REVIEW``.
3. Otherwise  ->  ``PASS``.

The recommendation is a suggestion only; the reviewer makes the final decision
(D-027, D-030). Thresholds always come from ``Product`` (loaded from the
database) and are never hardcoded here. No UI or Qt dependency.
"""

from agroscan.models.inspection_models import (
    AiRecommendation,
    DefectCriterion,
    DetectionResult,
    Product,
    QualityAssessmentResult,
)


def defect_ratios(product: Product, detection: DetectionResult) -> dict[str, float]:
    """Return ``{defect_class: count / total_objects}`` for every configured criterion."""
    return {c.defect_class: detection.ratio(c.defect_class) for c in product.criteria}


def _critical_reasons(product: Product, detection: DetectionResult) -> list[str]:
    reasons: list[str] = []
    for criterion in product.criteria:
        count = detection.class_counts.get(criterion.defect_class, 0)
        if criterion.is_critical and count > 0:
            reasons.append(f"Critical defect detected: {criterion.defect_class} ({count}).")
    return reasons


def _ratio_reasons(
    product: Product, detection: DetectionResult, ratios: dict[str, float]
) -> list[str]:
    reasons: list[str] = []
    for criterion in product.criteria:
        if criterion.is_critical:
            continue
        if _exceeds_limit(criterion, ratios[criterion.defect_class]):
            reasons.append(
                f"{criterion.defect_class.capitalize()} ratio "
                f"{ratios[criterion.defect_class]:.0%} exceeds limit {criterion.max_ratio:.0%}."
            )
    return reasons


def _exceeds_limit(criterion: DefectCriterion, ratio: float) -> bool:
    # Small epsilon so 10% of 20 objects (0.1) is not flagged by float noise.
    return ratio > criterion.max_ratio + 1e-9


def _uncertainty_reasons(product: Product, detection: DetectionResult) -> list[str]:
    reasons: list[str] = []
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
    return reasons


def assess_quality(product: Product, detection: DetectionResult) -> QualityAssessmentResult:
    """Evaluate one box against ``product`` criteria (D-023).

    ``is_simulated`` on the result mirrors ``detection.is_simulated`` so a real
    ONNX detection produces a non-simulated assessment.
    """
    ratios = defect_ratios(product, detection)
    simulated = detection.is_simulated

    fail_reasons = _critical_reasons(product, detection) + _ratio_reasons(
        product, detection, ratios
    )
    if fail_reasons:
        return QualityAssessmentResult(AiRecommendation.FAIL, fail_reasons, ratios, simulated)

    review_reasons = _uncertainty_reasons(product, detection)
    if review_reasons:
        return QualityAssessmentResult(
            AiRecommendation.NEEDS_REVIEW, review_reasons, ratios, simulated
        )

    return QualityAssessmentResult(
        AiRecommendation.PASS, ["All defect ratios are within limits."], ratios, simulated
    )

