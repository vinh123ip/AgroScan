"""Qwen-VL REST API Service & LM Studio Bridge (T2.5, D-017).

Runs a lightweight multithreaded HTTP REST server on the PC/workstation
(default: ``http://0.0.0.0:8000``) that exposes:
  - ``GET  /health``              : health & upstream LM Studio check
  - ``POST /api/v1/vlm/analyze``  : accepts base64 evidence image + inspection context,
                                    queries upstream LM Studio (OpenAI Vision API at
                                    ``http://127.0.0.1:1234/v1/chat/completions``) when
                                    online, and returns a structured error when inference is unavailable.

Every response strictly conforms to ``agroscan.models.vlm_models.VLM_JSON_SCHEMA`` (v1.0).
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agroscan.models.vlm_models import (  # noqa: E402
    SCHEMA_VERSION,
    VlmAnalysis,
    model_analysis,
    VlmErrorCode,
    VlmSchemaError,
)

DEFAULT_HOST = os.environ.get("AGROSCAN_VLM_HOST", "0.0.0.0")
DEFAULT_PORT = int(os.environ.get("AGROSCAN_VLM_PORT", "8000"))
DEFAULT_LM_STUDIO_URL = os.environ.get(
    "AGROSCAN_LM_STUDIO_URL", "http://127.0.0.1:1234/v1/chat/completions"
)
DEFAULT_MODEL_NAME = os.environ.get("AGROSCAN_VLM_MODEL", "Qwen2.5-VL-7B-Instruct")

SYSTEM_PROMPT = (
    "You are AgroScan Qwen-VL, an agricultural quality inspection assistant. "
    "Analyze the provided fruit box image and return ONLY a valid JSON object with fields: "
    "defects (list of {defect_class, count, severity: minor|major|critical, confidence: 0..1, description}), "
    "ocr ({readable: bool, fields: [{key, value, confidence}], raw_text}), "
    "observations (list of strings), assessment (string), "
    "uncertainty ({level: low|medium|high, score: 0..1, reasons: list of strings}), "
    "and suggestion (string)."
)


def _extract_json_block(text: str) -> dict[str, Any] | None:
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


def _call_lm_studio(
    image_b64: str,
    context: dict[str, Any],
    lm_studio_url: str,
    model_name: str,
    timeout_s: float = 8.0,
) -> dict[str, Any] | None:
    """Query LM Studio's OpenAI-compatible `/v1/chat/completions` vision endpoint."""
    if not image_b64 or not lm_studio_url:
        return None
    user_prompt = (
        f"Box Code: {context.get('box_code', 'UNKNOWN')}\n"
        f"Product: {context.get('product_name', 'Fruit')}\n"
        f"Supplier: {context.get('supplier', 'Unknown')}\n"
        f"YOLO Detection Counts: {json.dumps(context.get('class_counts', {}))}\n"
        "Inspect surface defects (bruised, rotten, mold, discoloration) and box label text."
    )
    payload = {
        "model": model_name,
        "temperature": 0.2,
        "max_tokens": 600,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                ],
            },
        ],
    }
    req = urllib.request.Request(
        lm_studio_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = (
            body.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return _extract_json_block(content)
    except Exception:
        return None


def build_vlm_response(
    request_data: dict[str, Any],
    lm_studio_url: str = DEFAULT_LM_STUDIO_URL,
    model_name: str = DEFAULT_MODEL_NAME,
) -> dict[str, Any]:
    """Produce a validated schema-1.0 VLM JSON response dict."""
    started = time.perf_counter()
    req_id = str(request_data.get("request_id") or f"vlm-{uuid.uuid4().hex[:10]}")
    image_b64 = str(request_data.get("image_base64") or "").strip()
    box_code = str(request_data.get("box_code") or "AGS:DH00123-01/10")
    product_name = str(request_data.get("product_name") or "Banana")
    supplier = str(request_data.get("supplier") or "AgroScan Supplier")
    detection = request_data.get("detection") or {}
    if not isinstance(detection, dict):
        detection = {}
    class_counts: dict[str, int] = {
        str(k): int(v) for k, v in dict(detection.get("class_counts") or {}).items()
    }

    # Check if caller explicitly asked to simulate a server error code
    force_error = request_data.get("force_error")
    if force_error in (VlmErrorCode.IMAGE_UNUSABLE.value, VlmErrorCode.MODEL_ERROR.value):
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return {
            "schema_version": SCHEMA_VERSION,
            "request_id": req_id,
            "status": "error",
            "model": model_name,
            "latency_ms": latency_ms,
            "analyzed_at": datetime.now().isoformat(timespec="seconds"),
            "defects": [],
            "ocr": None,
            "observations": [],
            "assessment": "",
            "uncertainty": None,
            "suggestion": "",
            "warnings": [],
            "error": {
                "code": force_error,
                "message": f"Qwen-VL server reported {force_error}.",
                "retryable": force_error != VlmErrorCode.IMAGE_UNUSABLE.value,
            },
        }

    if not image_b64:
        return VlmAnalysis.client_error(VlmErrorCode.IMAGE_UNUSABLE, "An original image is required.",
                                        retryable=False, request_id=req_id).to_dict()
    # Verify image bytes before contacting the model.
    if image_b64:
        try:
            raw_bytes = base64.b64decode(image_b64, validate=True)
            if len(raw_bytes) < 32:
                raise ValueError("Image payload too small")
        except Exception as exc:
            latency_ms = max(1, int((time.perf_counter() - started) * 1000))
            return {
                "schema_version": SCHEMA_VERSION,
                "request_id": req_id,
                "status": "error",
                "model": model_name,
                "latency_ms": latency_ms,
                "analyzed_at": datetime.now().isoformat(timespec="seconds"),
                "defects": [],
                "ocr": None,
                "observations": [],
                "assessment": "",
                "uncertainty": None,
                "suggestion": "",
                "warnings": [],
                "error": {
                    "code": VlmErrorCode.IMAGE_UNUSABLE.value,
                    "message": f"Invalid or corrupted image payload: {exc}",
                    "retryable": False,
                },
            }

    # 1. Try upstream LM Studio if reachable
    lm_raw = _call_lm_studio(
        image_b64=image_b64,
        context={
            "box_code": box_code,
            "product_name": product_name,
            "supplier": supplier,
            "class_counts": class_counts,
        },
        lm_studio_url=lm_studio_url,
        model_name=model_name,
    )

    if lm_raw is None:
        return VlmAnalysis.client_error(
            VlmErrorCode.MODEL_ERROR, "The vision model returned no usable analysis.",
            retryable=True, request_id=req_id,
        ).to_dict()
    try:
        return model_analysis(lm_raw, req_id, model_name,
                              max(1, int((time.perf_counter() - started) * 1000))).to_dict()
    except VlmSchemaError as exc:
        return VlmAnalysis.client_error(VlmErrorCode.INVALID_RESPONSE, str(exc),
                                        retryable=True, request_id=req_id).to_dict()


class QwenVlmRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler for AgroScan Qwen-VL REST API."""

    lm_studio_url: str = DEFAULT_LM_STUDIO_URL
    model_name: str = DEFAULT_MODEL_NAME

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep logs concise
        sys.stderr.write(f"[Qwen-VL REST] {self.address_string()} - {fmt % args}\n")

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.partition("?")[0] in ("/", "/health", "/api/v1/health"):
            self._send_json(
                200,
                {
                    "status": "ok",
                    "service": "AgroScan Qwen-VL REST Service",
                    "schema_version": SCHEMA_VERSION,
                    "model": self.model_name,
                    "lm_studio_url": self.lm_studio_url,
                },
            )
            return
        self._send_json(404, {"error": "Not Found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self.path.startswith(("/api/v1/vlm/analyze", "/v1/chat/completions")):
            self._send_json(404, {"error": f"Unsupported endpoint: {self.path}"})
            return

        content_len = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            data = json.loads(raw_body.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("JSON root must be an object")
        except Exception as exc:
            self._send_json(400, {"error": f"Malformed JSON request: {exc}"})
            return

        try:
            result = build_vlm_response(
                data,
                lm_studio_url=self.lm_studio_url,
                model_name=self.model_name,
            )
            self._send_json(200, result)
        except VlmSchemaError as exc:
            self._send_json(500, {"error": f"Schema validation error: {exc}"})
        except Exception as exc:
            self._send_json(500, {"error": f"Internal VLM service error: {exc}"})


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    lm_studio_url: str = DEFAULT_LM_STUDIO_URL,
    model_name: str = DEFAULT_MODEL_NAME,
) -> ThreadingHTTPServer:
    """Create and configure a ThreadingHTTPServer instance (useful for both CLI and tests)."""

    class _ConfiguredHandler(QwenVlmRequestHandler):
        pass

    _ConfiguredHandler.lm_studio_url = lm_studio_url
    _ConfiguredHandler.model_name = model_name
    return ThreadingHTTPServer((host, port), _ConfiguredHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="AgroScan Qwen-VL REST API Server (D-017)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port (default: 8000)")
    parser.add_argument(
        "--lm-studio-url",
        default=DEFAULT_LM_STUDIO_URL,
        help="Upstream LM Studio OpenAI endpoint",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME, help="VLM model identifier")
    args = parser.parse_args()

    server = create_server(
        host=args.host,
        port=args.port,
        lm_studio_url=args.lm_studio_url,
        model_name=args.model,
    )
    print(
        f"AgroScan Qwen-VL REST Server listening on http://{args.host}:{args.port} "
        f"(Upstream LM Studio: {args.lm_studio_url})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Qwen-VL server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

