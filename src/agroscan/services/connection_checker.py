"""Connectivity checks for the Settings "Test Connection" buttons (D-028).

Standard library only. These are blocking calls — run them off the UI thread.

- Database: TCP reachability of ``host:port`` only. It does not authenticate
  against PostgreSQL; that needs a database driver (not yet approved).
- AI service: any HTTP response means the server is reachable.
- Storage: the folder exists and a temporary file can be written to it.
"""

import socket
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class CheckResult:
    ok:      bool
    message: str


def check_database(host: str, port: int, timeout_s: float = 3.0) -> CheckResult:
    if not host.strip():
        return CheckResult(False, "Host is empty.")
    try:
        with socket.create_connection((host.strip(), port), timeout=timeout_s):
            return CheckResult(True, f"Port {port} on {host} is reachable (credentials not verified).")
    except OSError as exc:
        return CheckResult(False, f"Cannot reach {host}:{port} — {exc}")


def check_ai_service(url: str, timeout_s: float = 5.0) -> CheckResult:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return CheckResult(False, "URL must start with http:// or https://")
    try:
        with urllib.request.urlopen(url.strip(), timeout=timeout_s) as response:
            return CheckResult(True, f"Service responded (HTTP {response.status}).")
    except urllib.error.HTTPError as exc:
        return CheckResult(True, f"Service reachable (HTTP {exc.code}).")
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        return CheckResult(False, f"No response from service — {reason}")


def check_storage(path: str) -> CheckResult:
    folder = Path(path.strip())
    if not path.strip():
        return CheckResult(False, "Path is empty.")
    try:
        if not folder.is_dir():
            return CheckResult(False, "Folder does not exist or is not reachable.")
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".agroscan_write_test_"):
            pass
        return CheckResult(True, "Folder is reachable and writable.")
    except OSError as exc:
        return CheckResult(False, f"Folder is not writable — {exc}")
