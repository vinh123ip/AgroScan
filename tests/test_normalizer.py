"""Unit tests for business-neutral order import normalization."""

from datetime import date, datetime
from pathlib import Path
import sys
import unittest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agroscan.services.order_import.normalizer import normalize_cell, normalize_header, parse_int


class TestOrderImportNormalizer(unittest.TestCase):
    def test_normalize_header_ascii_and_vietnamese(self) -> None:
        self.assertEqual(normalize_header("  Order Code  "), "order_code")
        self.assertEqual(normalize_header("Goods-Category"), "goods_category")
        self.assertEqual(normalize_header("Lot Size"), "lot_size")
        self.assertEqual(normalize_header("Mã Đơn Hàng"), "ma_don_hang")
        self.assertEqual(normalize_header("Đợt / Lô"), "dot_lo")
        self.assertEqual(normalize_header(None), "")

    def test_normalize_cell_preserves_meaning(self) -> None:
        self.assertEqual(normalize_cell(None), "")
        self.assertEqual(normalize_cell(True), "TRUE")
        self.assertEqual(normalize_cell(False), "FALSE")
        self.assertEqual(normalize_cell(12.0), "12")
        self.assertEqual(normalize_cell(12.5), "12.5")
        self.assertEqual(normalize_cell("  Mekong\u00a0Fresh  "), "Mekong Fresh")
        self.assertEqual(normalize_cell(date(2026, 11, 28)), "2026-11-28")
        self.assertEqual(normalize_cell(datetime(2026, 11, 28, 9, 30)), "2026-11-28 09:30:00")

    def test_parse_int_plain_grouped_and_invalid(self) -> None:
        self.assertEqual(parse_int("42"), 42)
        self.assertEqual(parse_int("  -10 "), -10)
        self.assertEqual(parse_int("1,250"), 1250)
        self.assertEqual(parse_int("1,250,000"), 1250000)
        for bad in ("", "12.5", "12,34", "1,250 000", "abc", "10,5"):
            self.assertIsNone(parse_int(bad), bad)


if __name__ == "__main__":
    unittest.main()
