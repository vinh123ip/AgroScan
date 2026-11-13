"""Evidence image capture, disk persistence, and SHA-256 hashing service (T1.6, D-008, D-018, D-026).

Responsibilities:
1. Encode raw captured frames (`QImage` or raw image bytes) into lossless PNG bytes
   BEFORE any detection bounding boxes or UI overlays are drawn.
2. Compute a 64-character lowercase hexadecimal SHA-256 digest on the exact raw bytes.
3. Persist the raw image file to the configured storage root (SMB share when reachable,
   falling back to the local ``captures/`` directory) without ever overwriting existing
   evidence files (D-008).
4. Return a populated ``EvidenceImage`` domain object (`relative_path`, `sha256`,
   `captured_at`, `is_auto_capture`) ready for PostgreSQL persistence.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
from typing import Optional, Union

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage

from agroscan.models.inspection_models import EvidenceImage
from agroscan.services.app_settings import AppSettings, ConnectionSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPTURES_DIR = REPO_ROOT / "captures"

_PLACEHOLDER_HOSTS = ("\\\\server_ip\\", "//server_ip/")
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9._-]+")

# Workstation settings used when a caller (e.g. a thumbnail widget) does not pass any.
_default_settings: Optional[Union[AppSettings, ConnectionSettings]] = None


def configure_evidence_storage(
    settings: Optional[Union[AppSettings, ConnectionSettings]],
) -> None:
    """Set (or clear with ``None``) the settings used to locate evidence files by default.

    ``MainWindow`` calls this so every page resolves ``relative_path`` against the
    storage path configured on the Settings screen (D-018, D-028).
    """
    global _default_settings
    _default_settings = settings


def compute_sha256(raw_bytes: bytes) -> str:
    """Return the 64-character lowercase hex SHA-256 digest of ``raw_bytes``."""
    if not isinstance(raw_bytes, (bytes, bytearray, memoryview)):
        raise TypeError("raw_bytes must be a bytes-like object.")
    return hashlib.sha256(raw_bytes).hexdigest()


def encode_qimage_bytes(image: QImage, image_format: str = "PNG") -> bytes:
    """Serialize a ``QImage`` into raw image file bytes (default: lossless PNG)."""
    if image.isNull():
        raise ValueError("Cannot encode a null QImage.")
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Failed to open QBuffer for encoding QImage.")
    try:
        ok = image.save(buffer, image_format)
    finally:
        buffer.close()
    if not ok or byte_array.isEmpty():
        raise RuntimeError(f"Failed to encode QImage as {image_format}.")
    return bytes(byte_array.data())


def _is_placeholder_storage_path(raw_path: str) -> bool:
    cleaned = raw_path.strip()
    if not cleaned:
        return True
    lowered = cleaned.lower().replace("/", "\\")
    return any(lowered.startswith(prefix.replace("/", "\\")) for prefix in _PLACEHOLDER_HOSTS)


def resolve_storage_root(
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
    storage_root: Optional[Union[Path, str]] = None,
    fallback_dir: Optional[Union[Path, str]] = None,
) -> Path:
    """Resolve the active directory where evidence images are stored.

    Priority:
    1. Explicit ``storage_root`` parameter if provided.
    2. ``AGROSCAN_STORAGE_PATH`` environment variable if set.
    3. ``storage_path`` from ``settings`` if it is not the default ``\\\\SERVER_IP\\...``
       placeholder and can be created/accessed.
    4. ``fallback_dir`` (defaults to ``<repo_root>/captures``).
    """
    if storage_root is not None and str(storage_root).strip():
        target = Path(storage_root)
        target.mkdir(parents=True, exist_ok=True)
        return target

    env_path = os.environ.get("AGROSCAN_STORAGE_PATH", "").strip()
    if env_path and not _is_placeholder_storage_path(env_path):
        try:
            target = Path(env_path)
            target.mkdir(parents=True, exist_ok=True)
            return target
        except OSError:
            pass

    configured = ""
    effective_settings = settings if settings is not None else _default_settings
    if isinstance(effective_settings, AppSettings):
        configured = effective_settings.load().storage_path
    elif isinstance(effective_settings, ConnectionSettings):
        configured = effective_settings.storage_path

    if configured and not _is_placeholder_storage_path(configured):
        try:
            target = Path(configured)
            target.mkdir(parents=True, exist_ok=True)
            return target
        except OSError:
            pass

    fallback = Path(fallback_dir) if fallback_dir is not None else DEFAULT_CAPTURES_DIR
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _sanitize_token(value: str) -> str:
    cleaned = _SAFE_TOKEN_RE.sub("_", value.strip())
    return cleaned.strip("_") or "session"


def capture_and_save_evidence(
    raw_image: Union[QImage, bytes, bytearray],
    session_id: str,
    sequence: int = 1,
    is_auto_capture: bool = False,
    captured_at: Optional[datetime] = None,
    storage_root: Optional[Union[Path, str]] = None,
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
    image_format: str = "PNG",
) -> EvidenceImage:
    """Hash raw image bytes with SHA-256 and write the unannotated file to disk.

    Args:
        raw_image: Original frame (`QImage` or raw encoded bytes) BEFORE drawing boxes.
        session_id: Active inspection session identifier (e.g. ``INS-20261114-0001``).
        sequence: 1-based capture index within the session.
        is_auto_capture: ``True`` if triggered automatically by steady-box detector.
        captured_at: Capture timestamp (defaults to ``datetime.now()``).
        storage_root: Optional explicit base directory override.
        settings: Optional ``AppSettings`` or ``ConnectionSettings`` for SMB path lookup.
        image_format: Image encoding format when ``raw_image`` is a ``QImage`` (default ``PNG``).

    Returns:
        ``EvidenceImage`` with ``relative_path`` (POSIX slashes) and 64-char ``sha256``.
    """
    timestamp = captured_at or datetime.now()
    if isinstance(raw_image, QImage):
        raw_bytes = encode_qimage_bytes(raw_image, image_format=image_format)
        ext = image_format.lower()
    elif isinstance(raw_image, (bytes, bytearray)):
        if len(raw_image) == 0:
            raise ValueError("Cannot save empty raw_image bytes.")
        raw_bytes = bytes(raw_image)
        ext = image_format.lower()
    else:
        raise TypeError("raw_image must be a QImage or bytes.")

    digest = compute_sha256(raw_bytes)
    root = resolve_storage_root(settings=settings, storage_root=storage_root)

    date_folder = timestamp.strftime("%Y-%m-%d")
    safe_session = _sanitize_token(session_id)
    time_token = timestamp.strftime("%H%M%S_%f")[:10]
    seq_num = max(1, int(sequence))

    rel_dir = Path(date_folder) / safe_session
    abs_dir = root / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    base_stem = f"ev_{seq_num:02d}_{time_token}_{digest[:8]}"
    candidate_name = f"{base_stem}.{ext}"
    abs_path = abs_dir / candidate_name

    # D-008: Never overwrite an existing evidence file
    collision_idx = 2
    while abs_path.exists():
        candidate_name = f"{base_stem}_{collision_idx}.{ext}"
        abs_path = abs_dir / candidate_name
        collision_idx += 1

    abs_path.write_bytes(raw_bytes)

    rel_posix = (rel_dir / candidate_name).as_posix()
    return EvidenceImage(
        captured_at=timestamp,
        is_auto_capture=is_auto_capture,
        relative_path=rel_posix,
        sha256=digest,
    )


def resolve_evidence_path(
    item: Union[EvidenceImage, str],
    storage_root: Optional[Union[Path, str]] = None,
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
) -> Optional[Path]:
    """Locate an evidence image file on disk from its relative path."""
    rel = item.relative_path if isinstance(item, EvidenceImage) else str(item)
    rel = rel.strip()
    if not rel:
        return None

    direct = Path(rel)
    if direct.is_absolute() and direct.is_file():
        return direct

    root = resolve_storage_root(settings=settings, storage_root=storage_root)
    candidate = root / Path(rel)
    if candidate.is_file():
        return candidate

    fallback_candidate = DEFAULT_CAPTURES_DIR / Path(rel)
    if fallback_candidate.is_file():
        return fallback_candidate

    return None


def verify_evidence_integrity(
    item: EvidenceImage,
    storage_root: Optional[Union[Path, str]] = None,
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
) -> bool:
    """Verify that the file on disk exists and matches ``item.sha256``."""
    if not item.sha256 or not item.relative_path:
        return False
    path = resolve_evidence_path(item, storage_root=storage_root, settings=settings)
    if path is None or not path.is_file():
        return False
    actual_sha256 = compute_sha256(path.read_bytes())
    return actual_sha256.lower() == item.sha256.strip().lower()


def load_evidence_qimage(
    item: Union[EvidenceImage, str],
    storage_root: Optional[Union[Path, str]] = None,
    settings: Optional[Union[AppSettings, ConnectionSettings]] = None,
) -> Optional[QImage]:
    """Load an ``EvidenceImage`` from disk as a ``QImage`` if present."""
    path = resolve_evidence_path(item, storage_root=storage_root, settings=settings)
    if path is None:
        return None
    img = QImage(str(path))
    return img if not img.isNull() else None

