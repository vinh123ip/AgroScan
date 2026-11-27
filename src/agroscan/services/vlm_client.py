"""HTTP REST client for the Qwen-VL Deep Analysis service (T2.5, D-017).

Supports:
1. AgroScan Qwen-VL REST Server (``POST <ai_url>/api/v1/vlm/analyze``)
2. Direct LM Studio OpenAI-compatible Server (``POST <ai_url>/v1/chat/completions``)
3. Automatic fallback to ``mock_ai.simulate_deep_analysis`` when running in offline
   demo mode and the remote server is not started.
"""

from __future__ import annotations

import base64
import json
import socket
import time
from typing import Any, Optional, Union
import urllib.error
import urllib.request
import uuid

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from agroscan.models.inspection_models import DetectionResult, InspectionSession
from agroscan.models.vlm_models import (
    SCHEMA_VERSION,
    model_analysis,
    VlmAnalysis,
    VlmErrorCode,
    VlmSchemaError,
    parse_vlm_response,
)
from agroscan.services import mock_ai
from agroscan.services.app_settings import AppSettings, ConnectionSettings
from agroscan.services.evidence_service import encode_qimage_bytes


def _extract_json_block(text: str) -> Optional[dict[str, Any]]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _encode_image_base64(image: Optional[Union[QImage, bytes, bytearray]]) -> str:
    if image is None:
        return ""
    if isinstance(image, QImage):
        if image.isNull():
            return ""
        raw = encode_qimage_bytes(image, "PNG")
    elif isinstance(image, (bytes, bytearray)):
        raw = bytes(image)
    else:
        return ""
    return base64.b64encode(raw).decode("ascii")


def _build_analyze_url(base_url: str) -> tuple[str, bool]:
    """Return ``(endpoint_url, is_direct_openai_chat)`` from user-configured ``ai_url``."""
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        cleaned = "http://127.0.0.1:8000"
    if cleaned.endswith("/v1/chat/completions"):
        return cleaned, True
    if cleaned.endswith("/v1"):
        return f"{cleaned}/chat/completions", True
    if cleaned.endswith("/api/v1/vlm/analyze"):
        return cleaned, False
    # Port 1234 is LM Studio's default local server port
    if ":1234" in cleaned and "/api/" not in cleaned:
        return f"{cleaned}/v1/chat/completions", True
    return f"{cleaned}/api/v1/vlm/analyze", False


def request_deep_analysis(
    session: InspectionSession,
    detection: DetectionResult,
    image: Optional[Union[QImage, bytes, bytearray]] = None,
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
    scenario: Optional[mock_ai.VlmScenario] = None,
    timeout_s: Optional[float] = None,
    fallback_to_mock: bool = True,
) -> VlmAnalysis:
    """Send an evidence image and detection context to Qwen-VL over HTTP POST."""
    # If the user explicitly selected an error simulation scenario in the UI combo box,
    # honor it directly so all 5 error states remain testable in Demo Mode.
    if scenario is not None and scenario != mock_ai.VlmScenario.NORMAL:
        return mock_ai.simulate_deep_analysis(
            session=session,
            detection=detection,
            scenario=scenario,
            timeout_s=int(timeout_s or 10),
        )

    cfg = (
        settings.load()
        if isinstance(settings, AppSettings)
        else (settings or ConnectionSettings())
    )
    effective_timeout = float(timeout_s if timeout_s is not None else cfg.ai_timeout_s)
    endpoint_url, is_openai_chat = _build_analyze_url(cfg.ai_url)
    req_id = f"req-{session.session_id.lower()}-{uuid.uuid4().hex[:6]}"
    image_b64 = _encode_image_base64(image)

    started = time.perf_counter()
    if is_openai_chat:
        # Direct call to LM Studio /v1/chat/completions
        prompt = (
            "Return ONLY a JSON object with fields: defects (list),observations (list of str), "
            "assessment (str), suggestion (str), ocr ({readable, fields, raw_text}), "
            "uncertainty ({level, score, reasons}). Use English and report only visible evidence. "
            f"Context: Box={session.box_code.text}, Product={session.product.name}, "
            f"Supplier={session.order.supplier}, Counts={detection.class_counts}."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if image_b64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                }
            )
        payload: dict[str, Any] = {
            "model": "qwen2.5-vl",
            "temperature": 0.2,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": content}],
        }
    else:
        payload = {
            "request_id": req_id,
            "session_id": session.session_id,
            "box_code": session.box_code.text,
            "product_code": session.product.code,
            "product_name": session.product.name,
            "supplier": session.order.supplier,
            "detection": {
                "total_objects": detection.total_objects,
                "class_counts": detection.class_counts,
                "mean_confidence": detection.mean_confidence,
            },
            "image_base64": image_b64,
        }

    req = urllib.request.Request(
        endpoint_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
            raw_text = resp.read().decode("utf-8")
            decoded = json.loads(raw_text)
    except (socket.timeout, TimeoutError):
        if fallback_to_mock:
            return mock_ai.simulate_deep_analysis(
                session, detection, scenario=mock_ai.VlmScenario.NORMAL, timeout_s=int(effective_timeout)
            )
        return VlmAnalysis.client_error(
            VlmErrorCode.TIMEOUT,
            f"Qwen-VL server did not respond within {effective_timeout:.0f}s.",
            retryable=True,
            request_id=req_id,
        )
    except (urllib.error.URLError, OSError) as exc:
        if fallback_to_mock:
            return mock_ai.simulate_deep_analysis(
                session, detection, scenario=mock_ai.VlmScenario.NORMAL, timeout_s=int(effective_timeout)
            )
        return VlmAnalysis.client_error(
            VlmErrorCode.SERVICE_UNAVAILABLE,
            f"Cannot reach Qwen-VL service at {endpoint_url} — {exc}",
            retryable=True,
            request_id=req_id,
        )
    except json.JSONDecodeError as exc:
        return VlmAnalysis.client_error(
            VlmErrorCode.INVALID_RESPONSE,
            f"Qwen-VL service returned non-JSON response: {exc}",
            retryable=True,
            request_id=req_id,
        )

    try:
        if is_openai_chat:
            try:
                content = decoded["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise TypeError("Model content must be a JSON string.")
                findings = _extract_json_block(content)
                if findings is None:
                    raise ValueError("No valid JSON object in model reply.")
            except (KeyError, IndexError, TypeError, ValueError):
                raise VlmSchemaError("Missing or invalid model JSON.") from None
            analysis = model_analysis(findings, req_id, str(decoded.get("model") or "Qwen-VL"),
                                      max(1, int((time.perf_counter() - started) * 1000)))
        else:
            analysis = parse_vlm_response(decoded)
            if (
                analysis.is_error
                and fallback_to_mock
                and (scenario is None or scenario == mock_ai.VlmScenario.NORMAL)
                and analysis.error is not None
                and analysis.error.code in (
                    VlmErrorCode.MODEL_ERROR,
                    VlmErrorCode.SERVICE_UNAVAILABLE,
                    VlmErrorCode.TIMEOUT,
                )
            ):
                return mock_ai.simulate_deep_analysis(
                    session,
                    detection,
                    scenario=mock_ai.VlmScenario.NORMAL,
                    timeout_s=int(effective_timeout),
                )
        analysis.is_simulated = False
        return analysis
    except VlmSchemaError as exc:
        return VlmAnalysis.client_error(
            VlmErrorCode.INVALID_RESPONSE,
            f"VLM response violated schema {SCHEMA_VERSION}: {exc}",
            retryable=False,
            request_id=req_id,
        )


class VlmAnalysisThread(QThread):
    """Background worker so HTTP calls to Qwen-VL never freeze the PySide6 UI."""

    analysis_completed = Signal(int, object)  # (token, VlmAnalysis)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._token: int = 0
        self._session: Optional[InspectionSession] = None
        self._detection: Optional[DetectionResult] = None
        self._image: Optional[QImage] = None
        self._settings: Optional[ConnectionSettings] = None
        self._fallback_to_mock = False
        self._scenario: Optional[mock_ai.VlmScenario] = None

    def start_request(
        self,
        token: int,
        session: InspectionSession,
        detection: DetectionResult,
        image: Optional[QImage],
        settings: AppSettings,
        scenario: Optional[mock_ai.VlmScenario] = None,
        *, fallback_to_mock: bool = True,
    ) -> None:
        if self.isRunning():
            raise RuntimeError("An analysis request is already running.")
        self._token = token
        self._session = session
        self._detection = detection
        self._image = image.copy() if image is not None and not image.isNull() else None
        self._settings = settings.load()
        self._fallback_to_mock = fallback_to_mock
        self._scenario = scenario
        self.start()

    def run(self) -> None:
        if self._session is None or self._detection is None or self._settings is None:
            return
        result = request_deep_analysis(
            session=self._session,
            detection=self._detection,
            image=self._image,
            settings=self._settings,
            scenario=self._scenario,
            timeout_s=min(5.0, self._settings.ai_timeout_s) if self._fallback_to_mock else self._settings.ai_timeout_s,
            fallback_to_mock=self._fallback_to_mock,
        )
        self.analysis_completed.emit(self._token, result)
