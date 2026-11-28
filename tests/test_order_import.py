"""Unit tests for order import validation, repository APIs, transaction rollback and DataImportPage."""

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import psycopg2

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtWidgets import QApplication

from agroscan.services.database import DbConfig
from agroscan.services.mock_repository import MockRepository
from agroscan.services.order_import import (
    DEFAULT_BATCH,
    TEMPLATE_HEADERS,
    ImportIssue,
    ParsedRow,
    check_headers,
    parse_order_file,
    validate_rows,
)
from agroscan.services.postgres_repository import PostgresRepository
from agroscan.ui.pages.data_import_page import DataImportPage, write_order_template
from agroscan.ui.theme import apply_theme

_APP: QApplication | None = None


def setUpModule() -> None:  # noqa: N802
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


class _FakeCursor:
    def __init__(self, conn) -> None:
        self._conn = conn
        self._result = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql: str, params=None) -> None:
        self._conn.executed.append((sql.strip(), params))
        if self._conn.fail_on and self._conn.fail_on in sql:
            self._conn.fail_calls += 1
            if self._conn.fail_calls >= self._conn.fail_after:
                raise psycopg2.IntegrityError("duplicate key value violates unique constraint")
        if "FROM agroscan.users" in sql:
            self._result = [(1,)]
        elif "FROM agroscan.products" in sql:
            self._result = [("BANANA", 10, "Fruit"), ("APPLE", 11, "Fruit")]
        elif "FROM agroscan.orders WHERE" in sql:
            self._result = []
        elif "INSERT INTO agroscan.orders" in sql:
            self._conn.next_id += 1
            self._result = [(self._conn.next_id,)]
        elif "INSERT INTO agroscan.lots" in sql:
            self._conn.next_id += 1
            self._result = [(self._conn.next_id,)]
        else:
            self._result = []

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


class _FakeConnection:
    def __init__(self, *, fail_on: str = "", fail_after: int = 1) -> None:
        self.fail_on = fail_on
        self.fail_after = fail_after
        self.fail_calls = 0
        self.next_id = 100
        self.executed: list[tuple[str, object]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return _FakeCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True
        return False

    def close(self) -> None:
        self.closed = True


class TestOrderImportValidator(unittest.TestCase):
    PRODUCTS = {"BANANA": "Fruit", "APPLE": "Fruit", "SHRIMP": "Seafood"}

    def test_check_headers_supports_template_and_legacy_alias(self) -> None:
        self.assertEqual(check_headers(TEMPLATE_HEADERS), [])
        self.assertEqual(
            check_headers(["order_code", "product_code", "supplier", "total_boxes", "expected_quantity"]),
            [],
        )
        missing = check_headers(["order_code", "product_code"])
        self.assertEqual({i.field for i in missing}, {"Supplier", "Lot Size", "Expected Quantity"})

        conflict = check_headers(list(TEMPLATE_HEADERS) + ["total_boxes"])
        self.assertEqual(len(conflict), 1)
        self.assertEqual(conflict[0].field, "Lot Size")

    def test_validate_rows_multi_batch_and_legacy_alias(self) -> None:
        rows = [
            ParsedRow(2, {
                "order_code": " dh00201 ", "batch": " lot-a ", "product_code": "banana",
                "goods_category": "fruit", "supplier": "Mekong Fresh",
                "lot_size": "12", "expected_quantity": "1,200",
            }),
            ParsedRow(3, {
                "order_code": "DH00201", "batch": "LOT-B", "product_code": "BANANA",
                "goods_category": "Fruit", "supplier": "Mekong Fresh",
                "lot_size": "8", "expected_quantity": "800",
            }),
            ParsedRow(4, {
                "order_code": "DH00202", "product_code": "APPLE",
                "supplier": "Da Lat", "total_boxes": "5", "expected_quantity": "100",
            }),
        ]
        lots, issues = validate_rows(rows, self.PRODUCTS)
        self.assertEqual(issues, [])
        self.assertEqual(len(lots), 3)
        self.assertEqual((lots[0].order_code, lots[0].batch, lots[0].expected_quantity), ("DH00201", "LOT-A", 1200))
        self.assertEqual(lots[0].goods_category, "Fruit")
        self.assertEqual((lots[2].batch, lots[2].lot_size, lots[2].goods_category), (DEFAULT_BATCH, 5, "Fruit"))

    def test_validate_rows_reports_detailed_field_errors(self) -> None:
        rows = [
            ParsedRow(2, {
                "order_code": "DH00301", "batch": "LOT-A", "product_code": "BANANA",
                "goods_category": "Seafood", "supplier": "Mekong",
                "lot_size": "-5", "expected_quantity": "0",
            }),
            ParsedRow(3, {
                "order_code": "DH00301", "batch": "LOT-A", "product_code": "UNKNOWN",
                "goods_category": "Fruit", "supplier": "Other Supplier",
                "lot_size": "10000", "expected_quantity": "abc",
            }),
            ParsedRow(4, {
                "order_code": "EXISTING-01", "batch": "BAD BATCH", "product_code": "APPLE",
                "goods_category": "Fruit", "supplier": "Da Lat",
                "lot_size": "4", "expected_quantity": "40",
            }),
        ]
        lots, issues = validate_rows(rows, self.PRODUCTS, existing_orders=["EXISTING-01"])
        self.assertEqual(lots, [])
        by_key = {(i.row, i.field): i for i in issues}
        self.assertIn((2, "Goods Category"), by_key)
        self.assertEqual(by_key[(2, "Goods Category")].to_dict()["value"], "Seafood")
        self.assertIn("Fruit", by_key[(2, "Goods Category")].message)
        self.assertIn((2, "Lot Size"), by_key)
        self.assertIn((2, "Expected Quantity"), by_key)
        self.assertIn((3, "Product Code"), by_key)
        self.assertIn((3, "Supplier"), by_key)
        self.assertIn((3, "Batch"), by_key)
        self.assertIn((4, "Order Code"), by_key)
        self.assertIn((4, "Batch"), by_key)


class TestOrderImportRepositoryAndUI(unittest.TestCase):
    def test_template_roundtrip_and_mock_repository_list_get_import(self) -> None:
        repo = MockRepository()
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in (".csv", ".xlsx"):
                path = write_order_template(Path(tmp) / f"orders{suffix}", products=repo.products)
                parsed = parse_order_file(path)
                self.assertEqual(parsed.headers, TEMPLATE_HEADERS)
                self.assertEqual(check_headers(parsed.headers), [])

            csv_path = Path(tmp) / "orders.csv"
            imported, issues = repo.import_order_file(csv_path)
            self.assertEqual(issues, [])
            self.assertEqual(imported, 3)

            dh201 = repo.get_order("dh00201")
            self.assertEqual([o.lot_code for o in dh201], ["LOT-A", "LOT-B"])
            self.assertEqual([o.order_code for o in dh201], ["DH00201:LOT-A", "DH00201:LOT-B"])
            self.assertEqual(len(repo.get_order("DH00201:LOT-A")), 1)
            self.assertEqual(repo.get_order(""), [])
            self.assertIn("DH00202", {o.order_code for o in repo.list_orders()})

            # Re-importing the same file fails all-or-nothing without duplicates
            count_before = len(repo.orders)
            imported2, issues2 = repo.import_order_file(csv_path)
            self.assertEqual(imported2, 0)
            self.assertTrue(issues2)
            self.assertEqual(len(repo.orders), count_before)

    def test_data_import_page_rejects_partial_file_and_commits_valid_file(self) -> None:
        repo = MockRepository()
        page = DataImportPage(repo, actor="admin")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                bad_csv = Path(tmp) / "bad.csv"
                bad_csv.write_text(
                    "order_code,batch,product_code,goods_category,supplier,lot_size,expected_quantity\n"
                    "DH00901,LOT-01,BANANA,Fruit,Mekong,5,50\n"
                    "DH00902,LOT-01,APPLE,Seafood,Da Lat,4,40\n",
                    encoding="utf-8",
                )
                issues = page.load_file(bad_csv)
                self.assertEqual(len(issues), 1)
                self.assertEqual((issues[0].row, issues[0].field), (3, "Goods Category"))
                self.assertFalse(page.btn_commit.isEnabled())

                good_xlsx = write_order_template(Path(tmp) / "good.xlsx", products=repo.products)
                self.assertEqual(page.load_file(good_xlsx), [])
                self.assertTrue(page.btn_commit.isEnabled())
                imported, errors = page.commit_staged_orders()
                self.assertEqual((imported, errors), (3, []))
                self.assertEqual(len(repo.get_order("DH00201")), 2)
        finally:
            page.close()
            page.deleteLater()
            QApplication.processEvents()

    def test_postgres_repository_rolls_back_transaction_on_mid_batch_error(self) -> None:
        repo = PostgresRepository(db_config=DbConfig("127.0.0.1", 5432, "agroscan", "postgres", ""))
        fake_conn = _FakeConnection(fail_on="INSERT INTO agroscan.lots", fail_after=2)
        rows = [
            {
                "order_code": "DH00501", "batch": "LOT-A", "product_code": "BANANA",
                "goods_category": "Fruit", "supplier": "Mekong", "lot_size": 4, "expected_quantity": 40,
            },
            {
                "order_code": "DH00501", "batch": "LOT-B", "product_code": "APPLE",
                "goods_category": "Fruit", "supplier": "Mekong", "lot_size": 3, "expected_quantity": 30,
            },
        ]
        with patch("agroscan.services.postgres_repository.get_connection", return_value=fake_conn):
            imported, issues = repo.import_orders(rows, actor="admin", source_file="batch.csv")

        self.assertEqual(imported, 0)
        self.assertEqual(len(issues), 1)
        self.assertIn("Database error, nothing was imported", issues[0].message)
        self.assertTrue(fake_conn.rolled_back)
        self.assertFalse(fake_conn.committed)
        self.assertTrue(fake_conn.closed)

    def test_postgres_repository_get_order_handles_empty_code_without_db_call(self) -> None:
        repo = PostgresRepository(db_config=DbConfig("127.0.0.1", 5432, "agroscan", "postgres", ""))
        with patch("agroscan.services.postgres_repository.get_connection") as connect_mock:
            self.assertEqual(repo.get_order(""), [])
            self.assertEqual(repo.get_order("   "), [])
            connect_mock.assert_not_called()

    def test_postgres_repository_reports_connection_errors_cleanly(self) -> None:
        repo = PostgresRepository(db_config=DbConfig("127.0.0.1", 5432, "agroscan", "postgres", ""))
        with patch(
            "agroscan.services.postgres_repository.get_connection",
            side_effect=psycopg2.OperationalError("connection refused"),
        ):
            imported, issues = repo.import_orders(
                [{"order_code": "DH1", "product_code": "APPLE", "supplier": "S", "lot_size": 1, "expected_quantity": 10}],
                actor="admin",
                source_file="f.csv",
            )
            self.assertEqual(imported, 0)
            self.assertEqual(len(issues), 1)
            self.assertIn("connection refused", issues[0].message)


if __name__ == "__main__":
    unittest.main()
