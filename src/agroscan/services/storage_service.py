"""Windows Share (SMB) & Local Fallback Storage Service for Evidence Images (T2.6, D-018, D-028).

Handles saving and resolving evidence images directly to a Windows SMB network share
(e.g. ``\\\\192.168.1.10\\AgroScan_Data`` or ``\\\\SERVER_IP\\AgroScan_Data``) while storing
only the POSIX relative path in PostgreSQL. Transparently falls back to local
``captures/`` storage when the network share is unconfigured or offline, and provides
a synchronization utility to push offline captures to the SMB share once reconnected.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Optional, Union

from agroscan.services.app_settings import AppSettings, ConnectionSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_CAPTURES_DIR = REPO_ROOT / "captures"

_PLACEHOLDER_PREFIXES = ("\\\\server_ip\\", "//server_ip/")


@dataclass(frozen=True)
class StorageProbeResult:
    ok: bool
    is_smb: bool
    resolved_path: str
    latency_ms: int
    message: str


def normalize_storage_path(raw_path: str) -> str:
    """Normalize slash direction for UNC / Windows paths while preserving UNC prefix."""
    cleaned = raw_path.strip()
    if not cleaned:
        return ""
    if cleaned.startswith("//"):
        return "\\\\" + cleaned[2:].replace("/", "\\")
    if cleaned.startswith("\\\\"):
        return "\\\\" + cleaned[2:].replace("/", "\\")
    return cleaned


def is_smb_unc_path(raw_path: str) -> bool:
    """Return True if ``raw_path`` is a Windows UNC share path (``\\\\HOST\\Share...``)."""
    norm = normalize_storage_path(raw_path)
    return norm.startswith("\\\\") and len(norm.strip("\\").split("\\")) >= 2


def is_placeholder_smb_path(raw_path: str) -> bool:
    """Return True if ``raw_path`` is empty or uses the unconfigured ``SERVER_IP`` placeholder."""
    norm = normalize_storage_path(raw_path).lower()
    if not norm:
        return True
    return any(norm.startswith(p.replace("/", "\\")) for p in _PLACEHOLDER_PREFIXES)


def probe_storage_access(path_or_settings: Union[str, Path, AppSettings, ConnectionSettings]) -> StorageProbeResult:
    """Verify whether the configured storage directory (SMB or local) is reachable and writable."""
    started = time.perf_counter()
    if isinstance(path_or_settings, AppSettings):
        raw = path_or_settings.load().storage_path
    elif isinstance(path_or_settings, ConnectionSettings):
        raw = path_or_settings.storage_path
    else:
        raw = str(path_or_settings)

    norm = normalize_storage_path(raw)
    smb = is_smb_unc_path(norm)
    if not norm:
        return StorageProbeResult(False, False, "", 0, "Storage path is empty.")
    if is_placeholder_smb_path(norm):
        return StorageProbeResult(
            False,
            smb,
            norm,
            0,
            "Storage path uses placeholder SERVER_IP. Enter a real LAN IP or local folder.",
        )

    target = Path(norm)
    try:
        target.mkdir(parents=True, exist_ok=True)
        if not target.is_dir():
            latency = max(1, int((time.perf_counter() - started) * 1000))
            return StorageProbeResult(
                False, smb, str(target), latency, f"Target is not a reachable folder: {target}"
            )
        with tempfile.NamedTemporaryFile(dir=target, prefix=".agroscan_smb_test_", delete=True) as tmp:
            tmp.write(b"agroscan-ok")
            tmp.flush()
        latency = max(1, int((time.perf_counter() - started) * 1000))
        kind = "SMB network share" if smb else "Local/Mapped folder"
        return StorageProbeResult(
            True,
            smb,
            str(target),
            latency,
            f"{kind} is reachable and writable ({latency} ms).",
        )
    except OSError as exc:
        latency = max(1, int((time.perf_counter() - started) * 1000))
        return StorageProbeResult(
            False,
            smb,
            norm,
            latency,
            f"Cannot write to {norm} — {exc}",
        )


class StorageService:
    """High-level SMB + local cache storage manager for evidence images."""

    def __init__(
        self,
        settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
        local_fallback_dir: Optional[Union[Path, str]] = None,
    ) -> None:
        self._settings = settings
        self._fallback_dir = (
            Path(local_fallback_dir) if local_fallback_dir is not None else LOCAL_CAPTURES_DIR
        )
        self._fallback_dir.mkdir(parents=True, exist_ok=True)

    def configured_path(self) -> str:
        env_override = os.environ.get("AGROSCAN_STORAGE_PATH", "").strip()
        if env_override and not is_placeholder_smb_path(env_override):
            return normalize_storage_path(env_override)
        if isinstance(self._settings, AppSettings):
            return normalize_storage_path(self._settings.load().storage_path)
        if isinstance(self._settings, ConnectionSettings):
            return normalize_storage_path(self._settings.storage_path)
        return ""

    def active_root(self) -> tuple[Path, bool]:
        """Return ``(active_directory, using_primary_configured_share)``."""
        cfg_path = self.configured_path()
        if cfg_path and not is_placeholder_smb_path(cfg_path):
            try:
                target = Path(cfg_path)
                target.mkdir(parents=True, exist_ok=True)
                return target, True
            except OSError:
                pass
        self._fallback_dir.mkdir(parents=True, exist_ok=True)
        return self._fallback_dir, False

    def save_bytes(
        self,
        raw_bytes: bytes,
        relative_path: Union[str, Path],
        mirror_to_local: bool = True,
    ) -> Path:
        """Write ``raw_bytes`` to the SMB share (or local fallback) without overwriting."""
        rel = Path(str(relative_path).lstrip("/\\"))
        root, is_primary = self.active_root()
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw_bytes)

        # Keep a local cache mirror when writing to a remote SMB share for fast LAN viewing
        if is_primary and mirror_to_local and root.resolve() != self._fallback_dir.resolve():
            try:
                local_copy = self._fallback_dir / rel
                local_copy.parent.mkdir(parents=True, exist_ok=True)
                if not local_copy.exists():
                    local_copy.write_bytes(raw_bytes)
            except OSError:
                pass
        return target

    def resolve_file(self, relative_path: Union[str, Path]) -> Optional[Path]:
        """Resolve a stored POSIX relative path against SMB primary root and local fallback."""
        rel_str = str(relative_path).strip()
        if not rel_str:
            return None
        direct = Path(rel_str)
        if direct.is_absolute() and direct.is_file():
            return direct

        rel = Path(rel_str.lstrip("/\\"))
        root, _ = self.active_root()
        primary_candidate = root / rel
        if primary_candidate.is_file():
            return primary_candidate

        fallback_candidate = self._fallback_dir / rel
        if fallback_candidate.is_file():
            return fallback_candidate
        return None

    def sync_local_to_primary(self) -> tuple[int, int]:
        """Copy any offline evidence files from local ``captures/`` to the configured SMB share.

        Returns:
            ``(copied_count, skipped_or_failed_count)``
        """
        cfg_path = self.configured_path()
        if not cfg_path or is_placeholder_smb_path(cfg_path):
            return 0, 0
        primary_root = Path(cfg_path)
        try:
            primary_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return 0, 0

        if primary_root.resolve() == self._fallback_dir.resolve():
            return 0, 0

        copied = 0
        skipped = 0
        for src_file in self._fallback_dir.rglob("*"):
            if not src_file.is_file() or src_file.name.startswith("."):
                continue
            rel = src_file.relative_to(self._fallback_dir)
            dst_file = primary_root / rel
            if dst_file.exists():
                skipped += 1
                continue
            try:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                copied += 1
            except OSError:
                skipped += 1
        return copied, skipped

