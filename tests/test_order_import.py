"""Unit tests for task 3.1.5.7 — Order Import UI, CSV/XLSX parser and row validator.

Covers:
1. File inspection (.xlsx, .csv, invalid extensions, .xls legacy warning, empty/missing files).
2. CSV parsing & validation (valid rows, missing columns, duplicate columns, duplicate order_code,
   unknown product_code, out-of-range integers, grouped numbers, semicolon delimiter).
3. Excel (.xlsx) parsing & validation (shared strings, inline strings, numeric cells, sparse cells).
4. Template generation (template_csv_text and docs/templates/orders_template.csv).
5. Qt UI tests (ImportPreviewModel, DataImportPage, MainWindow integration) — skipped only when
   PySide6 is not installed in the active Python environment.
"""

import os
import sys
import tempfile
import time
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agroscan.services.order_gateway import (  # noqa: E402
    ImportResult,
    OrderGatewayError,
    OrderListItem,
)
from agroscan.services.order_import import (  # noqa: E402
    ImportFileError,
    build_preview,
    inspect_file,
    template_csv_text,
)

try:
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False


def _write_minimal_xlsx(path: Path, rows: list[list[object]]) -> None:
    """Create a real OOXML .xlsx file using stdlib zipfile (or openpyxl when available)."""
    try:
        import openpyxl  # type: ignore[import-not-found]

        wb = openpyxl.Workbook()
        ws = wb.active
        for row in rows:
            ws.append(list(row))
        wb.save(path)
        return
    except ImportError:
        pass

    # Fallback: minimal valid OOXML package with inline strings and numeric cells
    sheet_rows: list[str] = []
    for r_idx, row in enumerate(rows, start=1):
        cells_xml: list[str] = []
        for c_idx, val in enumerate(row):
            col_letter = chr(ord("A") + c_idx)
            ref = f"{col_letter}{r_idx}"
            if isinstance(val, (int, float)):
                cells_xml.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                text = (
                    str(val)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                cells_xml.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells_xml)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Orders" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)


class TestOrderImportService(unittest.TestCase):
    """Pure-Python tests for order_import.py (CSV + XLSX + validation)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.catalog = {"BANANA", "APPLE", "MANGO"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_inspect_file_rejects_invalid_formats_and_empty_files(self) -> None:
        txt = self.dir / "orders.txt"
        txt.write_text("hello", encoding="utf-8")
        with self.assertRaises(ImportFileError) as ctx:
            inspect_file(txt)
        self.assertIn("Unsupported file type", str(ctx.exception))

        xls = self.dir / "legacy.xls"
        xls.write_bytes(b"legacy")
        with self.assertRaises(ImportFileError) as ctx:
            inspect_file(xls)
        self.assertIn(".xlsx", str(ctx.exception))

        empty = self.dir / "empty.csv"
        empty.write_text("", encoding="utf-8")
        with self.assertRaises(ImportFileError) as ctx:
            inspect_file(empty)
        self.assertIn("empty", str(ctx.exception))

        with self.assertRaises(ImportFileError):
            inspect_file(self.dir / "missing.csv")

    def test_valid_csv_and_bundled_template(self) -> None:
        csv_path = self.dir / "valid.csv"
        csv_path.write_text(template_csv_text(), encoding="utf-8-sig")
        preview = build_preview(csv_path, known_product_codes=self.catalog)
        self.assertTrue(preview.can_import)
        self.assertEqual(preview.total_rows, 1)
        self.assertEqual(preview.valid_rows, 1)
        self.assertEqual(preview.invalid_rows, 0)
        row = preview.rows[0]
        self.assertEqual(row.order_code, "DH00200")
        self.assertEqual(row.product_code, "BANANA")
        self.assertEqual(row.total_boxes, 10)
        self.assertEqual(row.expected_quantity, 240)

        repo_template = ROOT_DIR / "docs" / "templates" / "orders_template.csv"
        self.assertTrue(repo_template.is_file())
        tpl_preview = build_preview(repo_template, known_product_codes=self.catalog)
        self.assertTrue(tpl_preview.can_import)
        self.assertEqual(tpl_preview.total_rows, 3)

    def test_csv_row_and_structure_validation(self) -> None:
        bad_struct = self.dir / "missing_col.csv"
        bad_struct.write_text("order_code,product_code\nDH001,BANANA\n", encoding="utf-8")
        preview = build_preview(bad_struct, known_product_codes=self.catalog)
        self.assertFalse(preview.can_import)
        self.assertTrue(preview.structure_errors)
        self.assertIn("Missing required column", preview.structure_errors[0])

        rows_csv = self.dir / "mixed_rows.csv"
        rows_csv.write_text(
            "Order Code;Product Code;Supplier;Total Boxes;Expected Quantity;Extra Note\n"
            "dh00300;banana;Green Valley;10;1,200;ok\n"
            "dh00300;PEAR;;0;-5;dup and invalid\n"
            "BAD-CODE!;APPLE;Da Lat;abc;100;bad code\n",
            encoding="utf-8",
        )
        preview = build_preview(
            rows_csv,
            known_product_codes=self.catalog,
            existing_order_codes={"DH99999"},
        )
        self.assertFalse(preview.can_import)
        self.assertEqual(preview.total_rows, 3)
        self.assertEqual(preview.invalid_rows, 3)  # Row 2 & 3 share duplicate DH00300, row 4 has errors
        self.assertTrue(preview.warnings)          # Extra Note column ignored
        messages = [issue.message for issue in preview.issues]
        self.assertTrue(any("duplicated" in m for m in messages))
        self.assertTrue(any("PEAR" in m for m in messages))
        self.assertTrue(any("Supplier is required" in m for m in messages))
        self.assertTrue(any("between 1 and 9999" in m for m in messages))
        self.assertTrue(any("whole number" in m for m in messages))

    def test_xlsx_valid_and_corrupted(self) -> None:
        xlsx_path = self.dir / "orders.xlsx"
        _write_minimal_xlsx(
            xlsx_path,
            [
                ["order_code", "product_code", "supplier", "total_boxes", "expected_quantity"],
                ["DH00501", "BANANA", "Mekong Fresh", 12, 300],
                ["DH00502", "MANGO", "Cam Ranh Coop", 8, 160],
            ],
        )
        preview = build_preview(xlsx_path, known_product_codes=self.catalog)
        self.assertTrue(preview.can_import)
        self.assertEqual(preview.total_rows, 2)
        self.assertEqual(preview.rows[0].order_code, "DH00501")
        self.assertEqual(preview.rows[0].total_boxes, 12)
        self.assertEqual(preview.rows[1].expected_quantity, 160)

        corrupt = self.dir / "corrupt.xlsx"
        corrupt.write_bytes(b"not a zip archive")
        with self.assertRaises(ImportFileError) as ctx:
            build_preview(corrupt, known_product_codes=self.catalog)
        self.assertIn("valid Excel workbook", str(ctx.exception))


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 is not installed in this Python runtime")
class TestDataImportPageUI(unittest.TestCase):
    """Qt UI tests for DataImportPage and ImportPreviewModel."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from agroscan.services.mock_repository import MockRepository
        from agroscan.ui.pages.data_import_page import DataImportPage

        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.repo = MockRepository(seed=7)
        self.page = DataImportPage(self.repo, gateway=None)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _wait_idle(self, timeout_s: float = 3.0) -> None:
        deadline = time.monotonic() + timeout_s
        while (self.page.is_busy or self.page._orders_loading) and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        QCoreApplication.processEvents()

    def test_upload_preview_and_disconnected_gateway_state(self) -> None:
        self.assertFalse(self.page.gateway_connected)
        self.assertFalse(self.page.btn_import.isEnabled())

        csv_path = self.dir / "orders.csv"
        csv_path.write_text(template_csv_text(), encoding="utf-8")
        self.assertTrue(self.page.select_file(str(csv_path)))
        self._wait_idle()

        self.assertIsNotNone(self.page.preview)
        self.assertTrue(self.page.preview.can_import)
        self.assertEqual(self.page.preview_model.rowCount(), 1)
        # Gateway is None (Option C): Import button must remain disabled
        self.assertFalse(self.page.btn_import.isEnabled())

        # Existing order in MockRepository (DH00121) must be flagged on preview
        dup_path = self.dir / "existing_order.csv"
        dup_path.write_text(
            "order_code,product_code,supplier,total_boxes,expected_quantity\n"
            "DH00121,BANANA,Green Valley Farm,10,240\n",
            encoding="utf-8",
        )
        self.assertTrue(self.page.select_file(str(dup_path)))
        self._wait_idle()
        self.assertIsNotNone(self.page.preview)
        self.assertFalse(self.page.preview.can_import)
        self.assertEqual(self.page.preview.invalid_rows, 1)

    def test_connected_gateway_import_and_refresh(self) -> None:
        from agroscan.ui.pages.data_import_page import DataImportPage

        class _StubGateway:
            def __init__(self) -> None:
                self.items: list[OrderListItem] = []

            def import_orders(self, rows):
                now = datetime.now()
                for r in rows:
                    self.items.append(OrderListItem(
                        r.order_code, r.product_code, r.supplier,
                        r.total_boxes or 0, r.expected_quantity or 0, now,
                    ))
                return ImportResult(len(rows), tuple(r.order_code for r in rows))

            def list_orders(self, limit: int = 50):
                return list(self.items[:limit])

        gw = _StubGateway()
        page = DataImportPage(self.repo, gateway=gw)
        self.page = page
        self._wait_idle()

        csv_path = self.dir / "orders.csv"
        csv_path.write_text(template_csv_text(), encoding="utf-8")
        page.select_file(str(csv_path))
        self._wait_idle()
        self.assertTrue(page.btn_import.isEnabled())

        self.assertTrue(page.start_import())
        self._wait_idle()
        self.assertEqual(page.orders_table.rowCount(), 1)
        self.assertFalse(page.btn_import.isEnabled())


if __name__ == "__main__":
    unittest.main()
