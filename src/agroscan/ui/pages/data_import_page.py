"""Data Import Page — CSV & Excel (.xlsx) order batch import with templates (T3.4, D-029)."""

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
from agroscan.services.postgres_repository import PostgresRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard, make_hint
from agroscan.ui.formatting import fmt_datetime

TEMPLATE_HEADERS = [
    "order_code",
    "product_code",
    "supplier",
    "total_boxes",
    "expected_quantity",
]

SAMPLE_TEMPLATE_ROWS = [
    ["DH00201", "BANANA", "Mekong Fresh Supply", "12", "300"],
    ["DH00202", "APPLE", "Da Lat Orchard Co.", "8", "200"],
]


def write_order_template(output_path: Union[Path, str]) -> Path:
    """Write a sample CSV or Excel (.xlsx) template file for order import."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".xlsx":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Orders"
        ws.append(TEMPLATE_HEADERS)
        for row in SAMPLE_TEMPLATE_ROWS:
            ws.append(row)
        wb.save(str(target))
    else:
        with target.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TEMPLATE_HEADERS)
            writer.writerows(SAMPLE_TEMPLATE_ROWS)
    return target


def parse_import_file(file_path: Union[Path, str]) -> list[dict[str, str]]:
    """Parse an order import CSV or Excel (.xlsx) file into a list of row dicts."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Import file not found: {path}")

    if path.suffix.lower() == ".xlsx":
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows_iter:
            return []
        headers = [str(h or "").strip().lower() for h in rows_iter[0]]
        result: list[dict[str, str]] = []
        for raw_row in rows_iter[1:]:
            if not raw_row or all(cell is None or str(cell).strip() == "" for cell in raw_row):
                continue
            row_dict = {
                headers[i]: str(raw_row[i] if raw_row[i] is not None else "").strip()
                for i in range(min(len(headers), len(raw_row)))
                if headers[i]
            }
            result.append(row_dict)
        return result

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for raw in reader:
            cleaned = {
                (k or "").strip().lower(): (v or "").strip()
                for k, v in raw.items()
                if k is not None
            }
            if any(cleaned.values()):
                rows.append(cleaned)
        return rows


class DataImportPage(ScrollPage):
    """Minimal CSV / Excel order import page with validation preview and DB commit."""

    orders_imported = Signal(int)  # number of imported orders

    def __init__(self, repo: MockRepository | PostgresRepository,
                 parent: Optional[QWidget] = None, *, actor: str = "") -> None:
        super().__init__("DataImportPage", parent)
        self._repo = repo
        self._actor = actor
        self._source_file = ""
        self._staged_rows: list[dict[str, str]] = []
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

        # Toolbar card
        action_card = SectionCard("1. Template & File Selection")
        action_card.body.addWidget(
            make_hint(
                "Required columns: order_code, product_code, supplier, total_boxes, expected_quantity. "
                "Supports both .csv (UTF-8) and .xlsx (Excel)."
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
        self.btn_commit = QPushButton("✔  Import Valid Orders to DB")
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
        action_card.body.addWidget(self.status_label)
        self.body.addWidget(action_card)

        # Preview table
        preview_card = SectionCard("2. Staged Import Preview & Row Validation")
        self.preview_table = DataTable(
            [
                "Row",
                "Order Code",
                "Product Code",
                "Supplier",
                "Total Boxes",
                "Expected Qty",
                "Validation Status",
            ]
        )
        self.preview_table.setMinimumHeight(210)
        preview_card.body.addWidget(self.preview_table)
        self.body.addWidget(preview_card)

        # Current Orders in DB
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

    def _validate_row(self, row: dict[str, str]) -> tuple[bool, str]:
        order_code = (row.get("order_code") or "").strip().upper()
        product_code = (row.get("product_code") or "").strip().upper()
        supplier = (row.get("supplier") or "").strip()
        if not order_code or not product_code or not supplier:
            return False, "✖ Missing required field(s)"
        if self._repo.find_product(product_code) is None:
            return False, f"✖ Unknown product '{product_code}'"
        try:
            boxes = int((row.get("total_boxes") or "0").strip())
            qty = int((row.get("expected_quantity") or "0").strip())
            if boxes < 1 or qty < 1:
                return False, "✖ Boxes & Qty must be >= 1"
        except ValueError:
            return False, "✖ Invalid integer in Boxes/Qty"
        exists = order_code in self._repo.orders
        if exists and isinstance(self._repo, PostgresRepository):
            return False, "Order already exists"
        action = "Update existing" if exists else "New order"
        return True, f"✔ Ready ({action})"

    def load_file(self, file_path: Union[Path, str]) -> int:
        """Load and validate rows from ``file_path`` into the preview table."""
        rows = parse_import_file(file_path)
        self._staged_rows = rows
        self._source_file = Path(file_path).name
        preview_rows: list[list[str]] = []
        valid_count = 0
        for idx, row in enumerate(rows, start=1):
            ok, msg = self._validate_row(row)
            if ok:
                valid_count += 1
            preview_rows.append(
                [
                    str(idx),
                    (row.get("order_code") or "").upper(),
                    (row.get("product_code") or "").upper(),
                    row.get("supplier") or "",
                    row.get("total_boxes") or "",
                    row.get("expected_quantity") or "",
                    msg,
                ]
            )
        self.preview_table.set_rows(preview_rows, rows)
        self.btn_commit.setEnabled(valid_count > 0)
        self.status_label.setText(
            f"Loaded {len(rows)} row(s) from {Path(file_path).name}: "
            f"{valid_count} valid, {len(rows) - valid_count} invalid."
        )
        return valid_count

    def commit_staged_orders(self) -> tuple[int, list[str]]:
        """Commit valid staged rows into the repository."""
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
            self.status_label.setText(
                f"Imported {imported} order(s), skipped {len(errors)}. {errors[0]}"
            )
        else:
            self.status_label.setText(f"✔  Successfully imported {imported} order(s) into database.")
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
            out = write_order_template(path)
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
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", f"Could not read file:\n{exc}")

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)

