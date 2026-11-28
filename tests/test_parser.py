"""Unit tests for Excel (.xlsx) and CSV (.csv) order import parsing."""

from pathlib import Path
import sys
import tempfile
import unittest

import openpyxl

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agroscan.services.order_import.parser import ImportFileError, parse_order_file


class TestOrderImportParser(unittest.TestCase):
    def test_parse_csv_bom_semicolon_quotes_and_row_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orders.csv"
            path.write_bytes(
                "\ufeffOrder Code;Batch;Product Code;Supplier;Lot Size;Expected Quantity\n"
                "\n"
                'DH001;LOT-A;BANANA;"Mekong; Fresh, Co.";12;300\n'
                'DH001;LOT-B;BANANA;"Mekong; Fresh, Co.";8;200\n'.encode("utf-8")
            )
            parsed = parse_order_file(path)
            self.assertEqual(
                parsed.headers,
                ("order_code", "batch", "product_code", "supplier", "lot_size", "expected_quantity"),
            )
            self.assertEqual([r.row_number for r in parsed.rows], [3, 4])
            self.assertEqual(parsed.rows[0].values["supplier"], "Mekong; Fresh, Co.")
            self.assertEqual(parsed.rows[1].values["batch"], "LOT-B")

    def test_parse_csv_quoted_comma_in_header_and_multiline_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quoted.csv"
            path.write_text(
                'Order Code,Supplier,Lot Size\n'
                'DH001,"Line 1\nLine 2",5\n'
                'DH002,"Acme, ""Best"" Co.",10\n',
                encoding="utf-8",
            )
            parsed = parse_order_file(path)
            self.assertEqual([r.row_number for r in parsed.rows], [2, 4])
            self.assertEqual(parsed.rows[0].values["supplier"], "Line 1\nLine 2")
            self.assertEqual(parsed.rows[1].values["supplier"], 'Acme, "Best" Co.')

    def test_parse_xlsx_skips_hidden_and_empty_sheets_and_keeps_row_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orders.xlsx"
            wb = openpyxl.Workbook()
            hidden = wb.active
            hidden.title = "Hidden"
            hidden.append(["order_code"])
            hidden.append(["IGNORE"])
            hidden.sheet_state = "hidden"

            empty = wb.create_sheet("Cover")
            empty.append([None, None])

            data = wb.create_sheet("Orders")
            data.append(["Order Code", "Batch", "Product Code", "Goods Category", "Supplier", "Lot Size", "Expected Quantity"])
            data.append([None, None, None, None, None, None, None])
            data.append(["DH002", "LOT-01", "APPLE", "Fruit", "Da Lat", 6.0, 120.0])
            wb.save(path)

            parsed = parse_order_file(path)
            self.assertEqual(len(parsed.rows), 1)
            self.assertEqual(parsed.rows[0].row_number, 3)
            self.assertEqual(parsed.rows[0].values["lot_size"], "6")
            self.assertEqual(parsed.rows[0].values["expected_quantity"], "120")

    def test_rejects_unsupported_empty_corrupted_invalid_encoding_and_duplicate_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            txt = root / "orders.txt"
            txt.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(ImportFileError):
                parse_order_file(txt)

            empty = root / "empty.csv"
            empty.write_bytes(b"")
            with self.assertRaises(ImportFileError):
                parse_order_file(empty)

            bad_utf8 = root / "latin1.csv"
            bad_utf8.write_bytes(b"order_code\n\xff\xfe\n")
            with self.assertRaises(ImportFileError):
                parse_order_file(bad_utf8)

            nul = root / "nul.csv"
            nul.write_bytes(b"order_code\nDH\x001\n")
            with self.assertRaises(ImportFileError):
                parse_order_file(nul)

            corrupt_xlsx = root / "corrupt.xlsx"
            corrupt_xlsx.write_bytes(b"not a zip archive")
            with self.assertRaises(ImportFileError):
                parse_order_file(corrupt_xlsx)

            dup = root / "dup.csv"
            dup.write_text("Order Code,order_code\nDH01,DH02\n", encoding="utf-8")
            with self.assertRaises(ImportFileError):
                parse_order_file(dup)

            extra = root / "extra.csv"
            extra.write_text("order_code,supplier\nDH01,Acme,unexpected\n", encoding="utf-8")
            with self.assertRaises(ImportFileError):
                parse_order_file(extra)


if __name__ == "__main__":
    unittest.main()
