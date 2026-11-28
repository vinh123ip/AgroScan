"""Order import template and row validation for Database Design v1.2 (orders -> lots).

Each row is one lot (Batch) of an order. Rows sharing an Order Code become one
``orders`` record with several ``lots``; Lot Size is ``lots.declared_boxes``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Union

from agroscan.services.order_import.normalizer import normalize_cell, normalize_header, parse_int
from agroscan.services.order_import.parser import ParsedRow

TEMPLATE_HEADERS = (
    "order_code", "batch", "product_code", "goods_category",
    "supplier", "lot_size", "expected_quantity",
)
REQUIRED_HEADERS = ("order_code", "product_code", "supplier", "lot_size", "expected_quantity")
LEGACY_ALIASES = {"total_boxes": "lot_size"}
DEFAULT_BATCH = "LOT-01"  # lot code used by imports before the Batch column existed
MAX_LOT_SIZE = 9999  # AGS box QR codes carry at most four box digits
MAX_QUANTITY = 2_147_483_647
FIELD_LABELS = {
    "order_code": "Order Code",
    "batch": "Batch",
    "product_code": "Product Code",
    "goods_category": "Goods Category",
    "supplier": "Supplier",
    "lot_size": "Lot Size",
    "expected_quantity": "Expected Quantity",
}
_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")


@dataclass(frozen=True)
class ImportIssue:
    """One validation or database problem; ``row`` is ``None`` for file-level issues."""

    row: Optional[int]
    field: Optional[str]
    value: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"row": self.row, "field": self.field, "value": self.value, "message": self.message}

    def __str__(self) -> str:
        where = f"Row {self.row}" if self.row else "File"
        column = f", {self.field}" if self.field else ""
        value = f" '{self.value}'" if self.value else ""
        return f"{where}{column}{value}: {self.message}"


@dataclass(frozen=True)
class LotRow:
    """A validated, normalized row ready to be stored as one lot."""

    row_number: int
    order_code: str
    batch: str
    product_code: str
    goods_category: str
    supplier: str
    lot_size: int
    expected_quantity: int


RowInput = Union[ParsedRow, Mapping[str, object]]


def check_headers(headers: Iterable[str]) -> list[ImportIssue]:
    """Report missing required columns and conflicting legacy aliases."""
    present = set(headers)
    issues = []
    for old, new in LEGACY_ALIASES.items():
        if old in present and new in present:
            issues.append(ImportIssue(None, FIELD_LABELS[new], "", f"Use either {new} or the legacy {old} column, not both."))
        if old in present:
            present.add(new)
    issues += [
        ImportIssue(None, FIELD_LABELS[key], "", "Required column is missing.")
        for key in REQUIRED_HEADERS if key not in present
    ]
    return issues


def as_parsed_rows(rows: Iterable[RowInput]) -> list[ParsedRow]:
    """Accept parsed rows or plain dicts (numbered from 1) and apply legacy aliases."""
    result = []
    for index, row in enumerate(rows, start=1):
        number, values = (row.row_number, row.values) if isinstance(row, ParsedRow) else (index, row)
        clean = {normalize_header(k): normalize_cell(v) for k, v in values.items()}
        for old, new in LEGACY_ALIASES.items():
            if old in clean:
                legacy = clean.pop(old)
                if not clean.get(new):
                    clean[new] = legacy
        result.append(ParsedRow(number, clean))
    return result


def order_codes(rows: Iterable[ParsedRow]) -> set[str]:
    return {row.values.get("order_code", "").upper() for row in rows} - {""}


def validate_rows(
    rows: Iterable[RowInput],
    products: Mapping[str, str],
    existing_orders: Iterable[str] = (),
) -> tuple[list[LotRow], list[ImportIssue]]:
    """Validate every row and return ``(valid_lots, issues)``.

    Args:
        products: Importable product code -> ``products.category``.
        existing_orders: Order codes already stored in the database.
    """
    parsed = as_parsed_rows(rows)
    if not parsed:
        return [], [ImportIssue(None, None, "", "The file has no order rows.")]
    categories = {code.upper(): category for code, category in products.items()}
    existing = {code.strip().upper() for code in existing_orders}
    first_supplier: dict[str, tuple[int, str]] = {}
    first_batch: dict[tuple[str, str], int] = {}
    lots: list[LotRow] = []
    issues: list[ImportIssue] = []

    for row in parsed:
        values, number = row.values, row.row_number
        row_issues: list[ImportIssue] = []

        def flag(key: str, message: str) -> None:
            row_issues.append(ImportIssue(number, FIELD_LABELS[key], values.get(key, ""), message))

        for key in REQUIRED_HEADERS:
            if not values.get(key):
                flag(key, f"{FIELD_LABELS[key]} is required.")
        order = values.get("order_code", "").upper()
        batch = (values.get("batch") or DEFAULT_BATCH).upper()
        product = values.get("product_code", "").upper()
        category = values.get("goods_category", "")
        supplier = values.get("supplier", "")

        if order and not _CODE.match(order):
            flag("order_code", "Use letters, digits, '-' or '_' only.")
        elif order in existing:
            flag("order_code", "Order Code already exists in the database.")
        if not _CODE.match(batch):
            flag("batch", "Use letters, digits, '-' or '_' only.")
        if product and product not in categories:
            flag("product_code", "Unknown product or product without an approved, active inspection profile.")
        elif product and category and category.casefold() != categories[product].casefold():
            flag("goods_category", f"Does not match category '{categories[product]}' of product {product}.")

        lot_size = _bounded_int(values.get("lot_size", ""), MAX_LOT_SIZE)
        if values.get("lot_size") and lot_size is None:
            flag("lot_size", f"Lot Size must be a whole number from 1 to {MAX_LOT_SIZE}.")
        quantity = _bounded_int(values.get("expected_quantity", ""), MAX_QUANTITY)
        if values.get("expected_quantity") and quantity is None:
            flag("expected_quantity", "Expected Quantity must be a positive whole number.")

        if order and supplier:
            first_row, first_name = first_supplier.setdefault(order, (number, supplier))
            if first_name != supplier:
                flag("supplier", f"Must match '{first_name}' on row {first_row} for Order Code {order}.")
        if order:
            seen_at = first_batch.setdefault((order, batch), number)
            if seen_at != number:
                flag("batch", f"Duplicate Batch {batch} for Order Code {order} (first on row {seen_at}).")

        if row_issues:
            issues += row_issues
        else:
            resolved_category = categories[product]
            lots.append(LotRow(number, order, batch, product, resolved_category, supplier, lot_size, quantity))
    return lots, issues


def _bounded_int(text: str, maximum: int) -> Optional[int]:
    value = parse_int(text) if text else None
    return value if value is not None and 1 <= value <= maximum else None
