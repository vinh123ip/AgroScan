"""VLM (Qwen-VL) deep-analysis contract — schema version 1.0.

This module is the single source of truth for the JSON returned by the
Qwen-VL service (D-017) and consumed by the desktop ``VlmResultPanel``.
``docs/api/vlm_analysis.schema.json`` is generated from ``VLM_JSON_SCHEMA``
(``python -m agroscan.models.vlm_models > docs/api/vlm_analysis.schema.json``)
and a unit test keeps both in sync.

Design rules (PROJECT.md §6 "Qwen-VL"):

* Observations, AI assessment, uncertainty and suggestion are separate fields.
* Output is untrusted: ``parse_vlm_response`` validates every field before
  the UI uses it and raises ``VlmSchemaError`` otherwise.
* VLM output never overrides YOLO numbers or the rule-engine recommendation;
  it is advisory information for the inspector and reviewer.
* Transport failures (timeout, service down, malformed JSON) are represented
  with the same structure via ``VlmAnalysis.client_error`` so the UI has one
  rendering path for every outcome.

Only the standard library is used (no new dependency, RULES.md §5).
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class VlmStatus(Enum):
    """Overall outcome of one deep-analysis request."""

    OK      = "ok"        # All sections produced
    PARTIAL = "partial"   # Usable result, but some section is missing (see warnings)
    ERROR   = "error"     # No usable result (see error)


class DefectSeverity(Enum):
    MINOR    = "minor"
    MAJOR    = "major"
    CRITICAL = "critical"


class UncertaintyLevel(Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"


class VlmErrorCode(Enum):
    """Error codes. ``source`` tells who produces each code."""

    TIMEOUT             = "TIMEOUT"              # client: no response within ai_timeout_s
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"  # client: connection refused / DNS / HTTP 5xx
    INVALID_RESPONSE    = "INVALID_RESPONSE"     # client: body is not valid schema-1.0 JSON
    IMAGE_UNUSABLE      = "IMAGE_UNUSABLE"       # server: blurred, too dark, box not visible
    MODEL_ERROR         = "MODEL_ERROR"          # server: inference failed / out of memory


#: Well-known OCR keys read from the box label, with their UI labels.
OCR_FIELD_LABELS: dict[str, str] = {
    "box_code":    "Box Code",
    "supplier":    "Supplier / Packer",
    "packed_date": "Packed Date",
    "lot_number":  "Lot Number",
    "origin":      "Origin",
    "net_weight":  "Net Weight",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class VlmSchemaError(ValueError):
    """Raised when a VLM payload does not satisfy schema version 1.0."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VlmDefect:
    defect_class: str
    count:        int
    severity:     DefectSeverity
    confidence:   float                          # 0.0 – 1.0
    description:  str = ""
    region:       Optional[list[float]] = None   # [x, y, w, h], normalized 0 – 1


@dataclass
class OcrField:
    key:        str
    value:      str
    confidence: float                            # 0.0 – 1.0

    @property
    def label(self) -> str:
        return OCR_FIELD_LABELS.get(self.key, self.key.replace("_", " ").title())


@dataclass
class VlmOcrResult:
    readable: bool
    fields:   list[OcrField] = field(default_factory=list)
    raw_text: str = ""

    def value(self, key: str) -> Optional[str]:
        return next((f.value for f in self.fields if f.key == key), None)


@dataclass
class VlmUncertainty:
    level:   UncertaintyLevel
    score:   float                               # 0.0 (certain) – 1.0 (very uncertain)
    reasons: list[str] = field(default_factory=list)


@dataclass
class VlmError:
    code:      VlmErrorCode
    message:   str
    retryable: bool = True


@dataclass
class VlmAnalysis:
    """Parsed, validated deep-analysis result (schema 1.0)."""

    status:         VlmStatus
    request_id:     str = ""
    model:          str = ""
    latency_ms:     int = 0
    analyzed_at:    datetime = field(default_factory=datetime.now)
    defects:        list[VlmDefect] = field(default_factory=list)
    ocr:            Optional[VlmOcrResult] = None
    observations:   list[str] = field(default_factory=list)
    assessment:     str = ""
    uncertainty:    Optional[VlmUncertainty] = None
    suggestion:     str = ""
    warnings:       list[str] = field(default_factory=list)
    error:          Optional[VlmError] = None
    schema_version: str = SCHEMA_VERSION
    is_simulated:   bool = False                 # UI-shell flag, never sent by the server

    @property
    def is_error(self) -> bool:
        return self.status == VlmStatus.ERROR

    @classmethod
    def client_error(
        cls, code: VlmErrorCode, message: str, retryable: bool = True, request_id: str = ""
    ) -> "VlmAnalysis":
        """Build an ERROR result for failures detected on the desktop side."""
        return cls(
            status=VlmStatus.ERROR,
            request_id=request_id,
            error=VlmError(code, message, retryable),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize back to the schema-1.0 wire format (``is_simulated`` excluded)."""
        return {
            "schema_version": self.schema_version,
            "request_id":     self.request_id,
            "status":         self.status.value,
            "model":          self.model,
            "latency_ms":     self.latency_ms,
            "analyzed_at":    self.analyzed_at.isoformat(timespec="seconds"),
            "defects": [
                {
                    "defect_class": d.defect_class,
                    "count":        d.count,
                    "severity":     d.severity.value,
                    "confidence":   d.confidence,
                    "description":  d.description,
                    "region":       d.region,
                }
                for d in self.defects
            ],
            "ocr": None if self.ocr is None else {
                "readable": self.ocr.readable,
                "fields": [
                    {"key": f.key, "value": f.value, "confidence": f.confidence}
                    for f in self.ocr.fields
                ],
                "raw_text": self.ocr.raw_text,
            },
            "observations": list(self.observations),
            "assessment":   self.assessment,
            "uncertainty": None if self.uncertainty is None else {
                "level":   self.uncertainty.level.value,
                "score":   self.uncertainty.score,
                "reasons": list(self.uncertainty.reasons),
            },
            "suggestion": self.suggestion,
            "warnings":   list(self.warnings),
            "error": None if self.error is None else {
                "code":      self.error.code.value,
                "message":   self.error.message,
                "retryable": self.error.retryable,
            },
        }


# ---------------------------------------------------------------------------
# JSON Schema (draft 2020-12) — published to docs/api/vlm_analysis.schema.json
# ---------------------------------------------------------------------------

_UNIT = {"type": "number", "minimum": 0, "maximum": 1}

VLM_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://agroscan.local/schemas/vlm_analysis/1.0",
    "title": "AgroScan VLM Deep Analysis Result",
    "description": (
        "Response body of POST /api/v1/vlm/analyze (Qwen-VL service, D-017). "
        "Advisory only: never overrides YOLO counts or the rule-engine recommendation."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "request_id", "status", "model", "latency_ms", "analyzed_at"],
    "properties": {
        "schema_version": {"const": SCHEMA_VERSION},
        "request_id":     {"type": "string"},
        "status":         {"enum": [s.value for s in VlmStatus]},
        "model":          {"type": "string"},
        "latency_ms":     {"type": "integer", "minimum": 0},
        "analyzed_at":    {"type": "string", "format": "date-time"},
        "defects": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["defect_class", "count", "severity", "confidence"],
                "properties": {
                    "defect_class": {"type": "string", "minLength": 1},
                    "count":        {"type": "integer", "minimum": 0},
                    "severity":     {"enum": [s.value for s in DefectSeverity]},
                    "confidence":   _UNIT,
                    "description":  {"type": "string"},
                    "region": {
                        "type": ["array", "null"],
                        "items": _UNIT,
                        "minItems": 4,
                        "maxItems": 4,
                    },
                },
            },
        },
        "ocr": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["readable", "fields"],
            "properties": {
                "readable": {"type": "boolean"},
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["key", "value", "confidence"],
                        "properties": {
                            "key":        {"type": "string", "minLength": 1},
                            "value":      {"type": "string"},
                            "confidence": _UNIT,
                        },
                    },
                },
                "raw_text": {"type": "string"},
            },
        },
        "observations": {"type": "array", "items": {"type": "string"}},
        "assessment":   {"type": "string"},
        "uncertainty": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["level", "score"],
            "properties": {
                "level":   {"enum": [u.value for u in UncertaintyLevel]},
                "score":   _UNIT,
                "reasons": {"type": "array", "items": {"type": "string"}},
            },
        },
        "suggestion": {"type": "string"},
        "warnings":   {"type": "array", "items": {"type": "string"}},
        "error": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["code", "message", "retryable"],
            "properties": {
                "code":      {"enum": [c.value for c in VlmErrorCode]},
                "message":   {"type": "string"},
                "retryable": {"type": "boolean"},
            },
        },
    },
    "allOf": [
        {
            "if": {"properties": {"status": {"const": "error"}}},
            "then": {"required": ["error"], "properties": {"error": {"type": "object"}}},
            "else": {
                "required": ["uncertainty"],
                "properties": {"error": {"type": "null"}, "uncertainty": {"type": "object"}},
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# Parsing / validation
# ---------------------------------------------------------------------------


def _require(data: dict, key: str, kind: type | tuple[type, ...], path: str) -> Any:
    if key not in data:
        raise VlmSchemaError(f"{path}.{key} is required.")
    value = data[key]
    if isinstance(value, bool) and kind in (int, float, (int, float)):
        raise VlmSchemaError(f"{path}.{key} must be a number.")
    if not isinstance(value, kind):
        raise VlmSchemaError(f"{path}.{key} has the wrong type.")
    return value


def _optional(data: dict, key: str, kind: type | tuple[type, ...], default: Any, path: str) -> Any:
    if data.get(key) is None:
        return default
    return _require(data, key, kind, path)


def _unit(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise VlmSchemaError(f"{path} must be a number between 0 and 1.")
    return float(value)


def _enum(enum_cls: type[Enum], value: Any, path: str) -> Any:
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(str(e.value) for e in enum_cls)
        raise VlmSchemaError(f"{path} must be one of: {allowed}.") from None


def _strings(data: dict, key: str, path: str) -> list[str]:
    items = _optional(data, key, list, [], path)
    if not all(isinstance(i, str) for i in items):
        raise VlmSchemaError(f"{path}.{key} must contain only strings.")
    return list(items)


def _check_keys(data: dict, allowed: set[str], path: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise VlmSchemaError(f"{path} has unknown field(s): {', '.join(sorted(unknown))}.")


def _parse_defect(raw: Any, path: str) -> VlmDefect:
    if not isinstance(raw, dict):
        raise VlmSchemaError(f"{path} must be an object.")
    _check_keys(raw, set(VLM_JSON_SCHEMA["properties"]["defects"]["items"]["properties"]), path)
    defect_class = _require(raw, "defect_class", str, path).strip()
    if not defect_class:
        raise VlmSchemaError(f"{path}.defect_class must not be empty.")
    count = _require(raw, "count", int, path)
    if count < 0:
        raise VlmSchemaError(f"{path}.count must be >= 0.")
    region = raw.get("region")
    if region is not None:
        if not isinstance(region, list) or len(region) != 4:
            raise VlmSchemaError(f"{path}.region must be [x, y, w, h].")
        region = [_unit(v, f"{path}.region[{i}]") for i, v in enumerate(region)]
    return VlmDefect(
        defect_class=defect_class,
        count=count,
        severity=_enum(DefectSeverity, raw.get("severity"), f"{path}.severity"),
        confidence=_unit(raw.get("confidence"), f"{path}.confidence"),
        description=_optional(raw, "description", str, "", path),
        region=region,
    )


def _parse_ocr(raw: Any, path: str) -> Optional[VlmOcrResult]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise VlmSchemaError(f"{path} must be an object or null.")
    _check_keys(raw, {"readable", "fields", "raw_text"}, path)
    readable = _require(raw, "readable", bool, path)
    fields_raw = _require(raw, "fields", list, path)
    fields: list[OcrField] = []
    for i, item in enumerate(fields_raw):
        item_path = f"{path}.fields[{i}]"
        if not isinstance(item, dict):
            raise VlmSchemaError(f"{item_path} must be an object.")
        _check_keys(item, {"key", "value", "confidence"}, item_path)
        key = _require(item, "key", str, item_path).strip()
        if not key:
            raise VlmSchemaError(f"{item_path}.key must not be empty.")
        fields.append(OcrField(
            key=key,
            value=_require(item, "value", str, item_path),
            confidence=_unit(item.get("confidence"), f"{item_path}.confidence"),
        ))
    return VlmOcrResult(readable, fields, _optional(raw, "raw_text", str, "", path))


def _parse_uncertainty(raw: Any, path: str) -> Optional[VlmUncertainty]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise VlmSchemaError(f"{path} must be an object or null.")
    _check_keys(raw, {"level", "score", "reasons"}, path)
    return VlmUncertainty(
        level=_enum(UncertaintyLevel, raw.get("level"), f"{path}.level"),
        score=_unit(raw.get("score"), f"{path}.score"),
        reasons=_strings(raw, "reasons", path),
    )


def _parse_error(raw: Any, path: str) -> Optional[VlmError]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise VlmSchemaError(f"{path} must be an object or null.")
    _check_keys(raw, {"code", "message", "retryable"}, path)
    return VlmError(
        code=_enum(VlmErrorCode, raw.get("code"), f"{path}.code"),
        message=_require(raw, "message", str, path),
        retryable=_require(raw, "retryable", bool, path),
    )


def parse_vlm_response(payload: str | bytes | dict) -> VlmAnalysis:
    """Validate a schema-1.0 payload (JSON text or decoded dict).

    Raises:
        VlmSchemaError: The payload is not valid JSON or violates the schema.
    """
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise VlmSchemaError(f"Response is not valid JSON — {exc}.") from None
    if not isinstance(payload, dict):
        raise VlmSchemaError("Response root must be a JSON object.")

    root = "$"
    _check_keys(payload, set(VLM_JSON_SCHEMA["properties"]), root)
    version = _require(payload, "schema_version", str, root)
    if version != SCHEMA_VERSION:
        raise VlmSchemaError(f"Unsupported schema_version {version!r}; expected {SCHEMA_VERSION}.")

    status = _enum(VlmStatus, payload.get("status"), f"{root}.status")
    latency = _require(payload, "latency_ms", int, root)
    if latency < 0:
        raise VlmSchemaError(f"{root}.latency_ms must be >= 0.")
    analyzed_raw = _require(payload, "analyzed_at", str, root)
    try:
        analyzed_at = datetime.fromisoformat(analyzed_raw)
    except ValueError:
        raise VlmSchemaError(f"{root}.analyzed_at must be an ISO-8601 date-time.") from None

    defects_raw = _optional(payload, "defects", list, [], root)
    analysis = VlmAnalysis(
        status=status,
        request_id=_require(payload, "request_id", str, root),
        model=_require(payload, "model", str, root),
        latency_ms=latency,
        analyzed_at=analyzed_at,
        defects=[_parse_defect(d, f"{root}.defects[{i}]") for i, d in enumerate(defects_raw)],
        ocr=_parse_ocr(payload.get("ocr"), f"{root}.ocr"),
        observations=_strings(payload, "observations", root),
        assessment=_optional(payload, "assessment", str, "", root),
        uncertainty=_parse_uncertainty(payload.get("uncertainty"), f"{root}.uncertainty"),
        suggestion=_optional(payload, "suggestion", str, "", root),
        warnings=_strings(payload, "warnings", root),
        error=_parse_error(payload.get("error"), f"{root}.error"),
        schema_version=version,
    )

    # Cross-field rules (mirrors the ``allOf`` block of VLM_JSON_SCHEMA)
    if status == VlmStatus.ERROR and analysis.error is None:
        raise VlmSchemaError("status 'error' requires an 'error' object.")
    if status != VlmStatus.ERROR:
        if analysis.error is not None:
            raise VlmSchemaError(f"status '{status.value}' must not carry an 'error' object.")
        if analysis.uncertainty is None:
            raise VlmSchemaError(f"status '{status.value}' requires an 'uncertainty' object.")
    return analysis


if __name__ == "__main__":
    print(json.dumps(VLM_JSON_SCHEMA, indent=2, ensure_ascii=False))

