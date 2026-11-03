"""Validation rules for the goods catalog and defect criteria (step 2, D-023/D-024).

Pure functions with no UI or storage dependency, so the same checks can be
reused by the Catalog & Criteria editor, the future Excel/CSV import (D-029)
and the PostgreSQL data-access layer.

These rules only check that a configuration is *well-formed*; they do not
change how the rule engine evaluates boxes (``mock_ai.assess_quality``).
"""

import re
from collections.abc import Iterable

from agroscan.models.inspection_models import Product

CODE_PATTERN  = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")
CLASS_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MODEL_SUFFIXES = (".onnx", ".pt", ".engine")
MAX_NAME_LENGTH = 60
MIN_OBJECTS_RANGE = (1, 500)


def parse_class_list(text: str) -> list[str]:
    """``"Fresh, bruised ,rotten"`` → ``["fresh", "bruised", "rotten"]`` (order kept)."""
    return [part.strip().lower() for part in text.split(",") if part.strip()]


def validate_product(product: Product, existing_codes: Iterable[str] = ()) -> list[str]:
    """Return human-readable errors (English UI, D-013); empty list means valid.

    Args:
        product: Candidate configuration.
        existing_codes: Codes already used by *other* products (uniqueness check).
    """
    errors: list[str] = []

    if not CODE_PATTERN.match(product.code):
        errors.append(
            "Code must be 2–20 characters: uppercase letters, digits or underscore, "
            "starting with a letter (e.g. BANANA)."
        )
    elif product.code in set(existing_codes):
        errors.append(f"Code {product.code} is already used by another product.")

    if not product.name.strip():
        errors.append("Name is required.")
    elif len(product.name) > MAX_NAME_LENGTH:
        errors.append(f"Name must be at most {MAX_NAME_LENGTH} characters.")

    if not product.category.strip():
        errors.append("Category is required.")

    model = product.model_file.strip()
    if not model:
        errors.append("YOLO model file is required.")
    elif any(sep in model for sep in ("/", "\\")) or not model.lower().endswith(MODEL_SUFFIXES):
        errors.append(
            "YOLO model file must be a file name (no folder) ending with "
            + ", ".join(MODEL_SUFFIXES) + "."
        )

    classes = product.detect_classes
    if len(classes) < 2:
        errors.append("Detect classes need at least 2 entries: the healthy class first, then defects.")
    bad = [c for c in classes if not CLASS_PATTERN.match(c)]
    if bad:
        errors.append(
            f"Invalid class name(s): {', '.join(bad)}. Use lowercase letters, digits or underscore."
        )
    if len(set(classes)) != len(classes):
        errors.append("Detect classes must be unique.")

    low, high = MIN_OBJECTS_RANGE
    if not low <= product.min_objects <= high:
        errors.append(f"Minimum objects must be between {low} and {high}.")
    if not 0.0 <= product.min_confidence <= 1.0:
        errors.append("Minimum confidence must be between 0% and 100%.")

    defect_classes = set(classes[1:])
    seen: set[str] = set()
    for criterion in product.criteria:
        name = criterion.defect_class
        if classes and name == classes[0]:
            errors.append(f"'{name}' is the healthy class and cannot have a defect criterion.")
        elif name not in defect_classes:
            errors.append(f"Criterion '{name}' is not one of the detect classes.")
        if name in seen:
            errors.append(f"Criterion '{name}' is defined more than once.")
        seen.add(name)
        if not 0.0 <= criterion.max_ratio <= 1.0:
            errors.append(f"Max ratio for '{name}' must be between 0% and 100%.")
    return errors

