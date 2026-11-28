"""Business-neutral normalization for order import headers and cells."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Optional

_NON_WORD = re.compile(r"[^a-z0-9]+")
_PLAIN_INT = re.compile(r"^[+-]?\d+$")
_GROUPED_INT = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+$")


def normalize_header(text: object) -> str:
    """Fold a header to snake_case ASCII, e.g. ``"Mã Lô"`` -> ``"ma_lo"``, ``"Lot Size"`` -> ``"lot_size"``."""
    folded = str(text or "").replace("đ", "d").replace("Đ", "D")
    ascii_text = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    return _NON_WORD.sub("_", ascii_text.lower()).strip("_")


def normalize_cell(value: object) -> str:
    """Convert a CSV/Excel cell value to trimmed text without changing its meaning."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ").strip()


def parse_int(text: str) -> Optional[int]:
    """Parse ``"12"`` or comma-grouped ``"1,250"``; return ``None`` for anything else."""
    value = text.strip()
    if _PLAIN_INT.match(value):
        return int(value)
    if _GROUPED_INT.match(value):
        return int(value.replace(",", ""))
    return None
