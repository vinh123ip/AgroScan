"""Contract between the Data Import page and the order backend.

Task 3.1.5.7 was approved as *UI + validation only* (option C, 06/11/2026):
the Order Import API and List Orders API (tasks 3.1.5.2 / 3.1.5.6) do not exist
in the repository yet, and PostgreSQL access is not integrated (D-014).

The Data Import page depends only on this protocol. It receives
``gateway=None`` until a real implementation (HTTP client or PostgreSQL
repository) is approved and written; while ``None`` the Import action stays
disabled and the order list shows a "not connected" state. Do **not** add a
fake implementation that pretends imports succeed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from agroscan.services.order_import import OrderImportRow


class OrderGatewayError(Exception):
    """Backend rejected the request or could not be reached; message is shown to the user."""


@dataclass(frozen=True)
class ImportResult:
    imported_count: int
    order_codes:    tuple[str, ...]
    message:        str = ""


@dataclass(frozen=True)
class OrderListItem:
    order_code:        str
    product_code:      str
    supplier:          str
    total_boxes:       int
    expected_quantity: int
    created_at:        Optional[datetime] = None


class OrderGateway(Protocol):
    """Blocking calls — the UI always runs them on a worker thread."""

    def import_orders(self, rows: Sequence[OrderImportRow]) -> ImportResult:
        """Persist all rows in one transaction (all-or-nothing).

        Raises:
            OrderGatewayError: Nothing was imported.
        """
        ...

    def list_orders(self, limit: int = 50) -> list[OrderListItem]:
        """Most recent orders first.

        Raises:
            OrderGatewayError: The list could not be loaded.
        """
        ...
