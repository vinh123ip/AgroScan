"""Data Import Page — CSV & Excel (.xlsx) order/lot import with all-or-nothing commit (T3.4, D-029)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, Union

import openpyxl
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QWidget,
)

from agroscan.services.mock_repository import MockRepository
from agroscan.services.order_import import (
    DEFAULT_BATCH,
    TEMPLATE_HEADERS,
    ImportFileError,
    ImportIssue,
    ParsedRow,
    as_parsed_rows,
    check_headers,
    parse_order_file,
    validate_rows,
)
from agroscan.services.postgres_repository import PostgresRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard, make_hint
from agroscan.ui.formatting import fmt_datetime

# Same order, two batches (lots) — shows the order -> lots relationship.
# Categories default to Database Design v1.2 seed values ('agricultural').
SAMPLE_TEMPLATE_ROWS = [
    ["DH00201", "LOT-A", "BANANA", "agricultural", "Mekong Fresh Supply", "12", "300"],
    ["DH00201", "LOT-B", "BANANA", "agricultural", "Mekong Fresh Supply", "8", "200"],
    ["DH00202", "LOT-01", "APPLE", "agricultural", "Da Lat Orchard Co.", "8", "200"],
]


def _sample_rows_for(products=None) -> list[list[str]]:
    if not products:
        return [list(row) for row in SAMPLE_TEMPLATE_ROWS]
    by_code = {p.code.upper(): p.category for p in products}
    return [
        [row[0], row[1], row[2], by_code.get(row[2].upper(), row[3]), row[4], row[5], row[6]]
        for row in SAMPLE_TEMPLATE_ROWS
    ]


def write_order_template(output_path: Union[Path, str], *, products=None) -> Path:
    """Write a sample CSV or Excel (.xlsx) template file for order import."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = _sample_rows_for(products)
    if target.suffix.lower() == ".xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Orders"
        ws.append(list(TEMPLATE_HEADERS))
        for row in rows:
            ws.append(row)
        wb.save(str(target))
    else:
        with target.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TEMPLATE_HEADERS)
            writer.writerows(rows)
    return target


def parse_import_file(file_path: Union[Path, str]) -> list[dict[str, str]]:
    """Parse an order import CSV or Excel file into normalized row dicts."""
    return [row.values for row in as_parsed_rows(parse_order_file(file_path).rows)]


class DataImportPage(ScrollPage):
    """CSV / Excel order import page with row-level validation preview and atomic DB commit."""

    orders_imported = Signal(int)  # number of imported lots

    def __init__(self, repo: MockRepository | PostgresRepository,
                 parent: Optional[QWidget] = None, *, actor: str = "") -> None:
        super().__init__("DataImportPage", parent)
        self._repo = repo
        self._actor = actor
        self._source_file = ""
        self._staged_rows: list[ParsedRow] = []
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        self.body.addWidget(
            PageHeader(
                "Data Import",
                "Download CSV/Excel templates, preview row-level validation, and import purchase orders into the database.",
                is_mock=False,
            )
        )

        action_card = SectionCard("1. Template & File Selection")
        action_card.body.addWidget(
            make_hint(
                "Required columns: order_code, product_code, supplier, lot_size (boxes in the lot), "
                "expected_quantity. Optional: batch (default LOT-01), goods_category (checked against "
                "the product). One row per batch; rows with the same order_code form one order. "
                "Any invalid row rejects the whole file. Supports .csv (UTF-8) and .xlsx."
            )
        )
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_template_csv = QPushButton("⬇  Save CSV Template")
        self.btn_template_csv.setObjectName("SecondaryButton")
        self.btn_template_xlsx = QPushButton("⬇  Save Excel Template")
        self.btn_template_xlsx.setObjectName("SecondaryButton")
        self.btn_load_file = QPushButton("📂  Load CSV / Excel File…")
        self.btn_load_file.setObjectName("SecondaryButton")
        self.btn_commit = QPushButton("✔  Import File to DB")
        self.btn_commit.setObjectName("PrimaryButton")
        self.btn_commit.setEnabled(False)

        for btn in (
            self.btn_template_csv,
            self.btn_template_xlsx,
            self.btn_load_file,
            self.btn_commit,
        ):
            btn.setFixedHeight(42)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_row.addWidget(self.btn_template_csv)
        btn_row.addWidget(self.btn_template_xlsx)
        btn_row.addWidget(self.btn_load_file)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_commit)
        action_card.body.addLayout(btn_row)

        self.status_label = QLabel("No file loaded yet.")
        self.status_label.setObjectName("HintLabel")
        self.status_label.setWordWrap(True)
        action_card.body.addWidget(self.status_label)
        self.body.addWidget(action_card)

        preview_card = SectionCard("2. Staged Import Preview & Row Validation")
        self.preview_table = DataTable(
            [
                "Row",
                "Order Code",
                "Batch",
                "Product Code",
                "Goods Category",
                "Supplier",
                "Lot Size",
                "Expected Qty",
                "Validation Status",
            ]
        )
        self.preview_table.setMinimumHeight(210)
        preview_card.body.addWidget(self.preview_table)
        self.body.addWidget(preview_card)

        orders_card = SectionCard("3. Existing Orders in Database")
        self.orders_table = DataTable(
            ["Order Code", "Lot", "Product", "Supplier", "Total Boxes",
             "Expected Qty", "Lot Decision", "Created At"]
        )
        self.orders_table.setMinimumHeight(240)
        orders_card.body.addWidget(self.orders_table)
        self.body.addWidget(orders_card)
        self.body.addStretch()

        self.btn_template_csv.clicked.connect(lambda: self._on_save_template(".csv"))
        self.btn_template_xlsx.clicked.connect(lambda: self._on_save_template(".xlsx"))
        self.btn_load_file.clicked.connect(self._on_browse_file)
        self.btn_commit.clicked.connect(self.commit_staged_orders)

    def _validate(self, rows: list[ParsedRow]) -> list[ImportIssue]:
        if isinstance(self._repo, PostgresRepository):
            return self._repo.validate_orders(rows)[1]
        products = {p.code: p.category for p in self._repo.products}
        existing = {k.split(":", 1)[0].upper() for k in self._repo.orders}
        return validate_rows(rows, products, existing)[1]

    def load_file(self, file_path: Union[Path, str]) -> list[ImportIssue]:
        """Parse and validate ``file_path`` into the preview; return all issues found.

        Raises:
            ImportFileError: The file cannot be read as an import table.
        """
        parsed = parse_order_file(file_path)
        rows = as_parsed_rows(parsed.rows)
        issues = check_headers(parsed.headers) or self._validate(rows)
        self._staged_rows = [] if issues else rows
        self._source_file = Path(file_path).name

        by_row: dict[int, list[ImportIssue]] = {}
        for issue in issues:
            by_row.setdefault(issue.row, []).append(issue)
        preview_rows = []
        for row in rows:
            v = row.values
            problems = by_row.get(row.row_number, [])
            status = ("✖ " + "; ".join(f"{i.field}: {i.message}" for i in problems)) if problems else "✔ Ready"
            preview_rows.append([
                str(row.row_number), v.get("order_code", "").upper(),
                v.get("batch", "").upper() or DEFAULT_BATCH,
                v.get("product_code", "").upper(), v.get("goods_category", ""), v.get("supplier", ""),
                v.get("lot_size", ""), v.get("expected_quantity", ""), status,
            ])
        self.preview_table.set_rows(preview_rows, rows)
        self.btn_commit.setEnabled(not issues and bool(rows))

        name = Path(file_path).name
        if issues:
            file_issues = by_row.get(None, [])
            first = str(file_issues[0]) if file_issues else str(issues[0])
            self.status_label.setText(
                f"✖ {name}: {len(issues)} issue(s) in {len(rows)} row(s); the file will not be imported. {first}"
            )
        else:
            self.status_label.setText(f"Loaded {len(rows)} row(s) from {name}: all valid, ready to import.")
        return issues

    def commit_staged_orders(self) -> tuple[int, list]:
        """Import the staged file atomically; nothing is stored if any row fails."""
        if not self._staged_rows:
            return 0, ["No rows staged."]
        if isinstance(self._repo, PostgresRepository):
            imported, errors = self._repo.import_orders(
                self._staged_rows, actor=self._actor, source_file=self._source_file,
            )
        else:
            imported, errors = self._repo.import_orders(self._staged_rows)
        self._staged_rows = []
        self.preview_table.set_rows([])
        self.btn_commit.setEnabled(False)
        self.refresh()
        if errors:
            self.status_label.setText(f"✖ Import rejected, nothing was stored. {errors[0]}")
        else:
            self.status_label.setText(f"✔  Successfully imported {imported} lot row(s) into database.")
        if imported > 0:
            self.orders_imported.emit(imported)
        return imported, errors

    def refresh(self) -> None:
        orders = list(self._repo.orders.values())
        self.orders_table.set_rows(
            [
                [
                    o.order_code,
                    o.lot_code or "—",
                    f"{o.product.name} ({o.product.code})",
                    o.supplier,
                    str(o.total_boxes),
                    str(o.expected_quantity) if o.expected_quantity is not None else "—",
                    o.lot_outcome or "—",
                    fmt_datetime(o.created_at),
                ]
                for o in orders
            ],
            orders,
        )

    def _on_save_template(self, ext: str) -> None:
        default_name = f"agroscan_orders_template{ext}"
        flt = "Excel Workbook (*.xlsx)" if ext == ".xlsx" else "CSV Files (*.csv)"
        path, _ = QFileDialog.getSaveFileName(self, "Save Order Import Template", default_name, flt)
        if not path:
            return
        try:
            out = write_order_template(path, products=self._repo.products)
            self.status_label.setText(f"✔  Saved template to {out}")
        except Exception as exc:
            QMessageBox.critical(self, "Template Error", f"Could not write template:\n{exc}")

    def _on_browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Order CSV or Excel File",
            "",
            "Spreadsheets (*.csv *.xlsx);;CSV Files (*.csv);;Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            self.load_file(path)
        except ImportFileError as exc:
            self._staged_rows = []
            self.preview_table.set_rows([])
            self.btn_commit.setEnabled(False)
            self.status_label.setText(f"✖ Could not read file: {exc}")
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", f"Could not read file:\n{exc}")

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)
