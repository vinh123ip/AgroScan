"""Comprehensive verification suite for Task 3.2.5.7 (Trello DoD + Real-World QA).

Covers:
1. Login Form, HMAC-signed Bearer Session/Token lifecycle, expiry, revocation,
   tamper detection, disabled account handling, and QSettings persistence.
2. Goods Category & Quality Criteria Editor: search + category filtering, live
   duplicate-criterion conflict detection, unsaved-navigation guard, and live sync.
3. QR/Barcode Scanner & Manual Order Code Lookup: ISO/IEC 18004 QR generation +
   mathematical Reed-Solomon/bitstream round-trip verification, QrLabelDialog
   simulation, USB scanner bounce debouncing, and Order Code search.
4. Order, Lot Size, Declared Category, Quality Criteria table, categorized scan
   errors (including accidental retail EAN-13 barcode scans), and D-021 duplicate
   open-session protection.
"""

import base64
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox  # noqa: E402

from agroscan.models.inspection_models import BoxCode, DefectCriterion  # noqa: E402
from agroscan.models.user_models import Role  # noqa: E402
from agroscan.services.app_settings import AppSettings  # noqa: E402
from agroscan.services.mock_auth import MockAuthService  # noqa: E402
from agroscan.services.mock_repository import MockRepository  # noqa: E402
from agroscan.services.qr_encoder import (  # noqa: E402
    _build_base_grid,
    _mask_bit,
    _zigzag_coords,
    encode_qr_matrix,
    format_bits,
    rs_syndromes,
)
from agroscan.ui.components.qr_label_dialog import QrLabelDialog  # noqa: E402
from agroscan.ui.main_window import MainWindow  # noqa: E402
from agroscan.ui.navigation import PageKey  # noqa: E402
from agroscan.ui.pages.login_dialog import LoginDialog  # noqa: E402
from agroscan.ui.theme import apply_theme  # noqa: E402

_APP: QApplication | None = None


def setUpModule() -> None:  # noqa: N802 — unittest hook
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


def _grid_texts(grid_widget) -> dict[str, str]:
    """Extract {KEY: value} pairs rendered inside a ``KeyValueGrid``."""
    pairs: dict[str, str] = {}
    layout = grid_widget._grid
    for i in range(layout.count()):
        cell = layout.itemAt(i).widget()
        if cell is None:
            continue
        labels = cell.findChildren(type(cell.layout().itemAt(0).widget()))
        if len(labels) >= 2:
            pairs[labels[0].text()] = labels[1].text()
    return pairs


class TestLoginAndBearerSessionToken(unittest.TestCase):
    """Trello #1 + Real-world session/token security & lifecycle."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ini_path = Path(self.tmp.name) / "agroscan_test.ini"
        self.settings = AppSettings(self.ini_path)
        self.auth = MockAuthService(session_ttl_seconds=3600)
        self.repo = MockRepository(seed=31)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_login_issues_signed_token_persists_safe_metadata_and_remembers_username(self) -> None:
        dialog = LoginDialog(self.auth, self.settings)
        self.assertEqual(dialog.password.echoMode(), QLineEdit.EchoMode.Password)
        dialog._toggle_password_visibility()
        self.assertEqual(dialog.password.echoMode(), QLineEdit.EchoMode.Normal)
        dialog._toggle_password_visibility()
        self.assertEqual(dialog.password.echoMode(), QLineEdit.EchoMode.Password)

        # Disabled account shows explicit disabled reason
        dialog.username.setText("inspector2")
        dialog.password.setText("inspector123")
        dialog._on_sign_in()
        self.assertIsNone(dialog.session)
        self.assertIn("disabled", dialog.error_label.text().lower())

        # Valid login with Remember Username checked
        dialog.chk_remember.setChecked(True)
        dialog.username.setText("admin")
        dialog.password.setText("admin123")
        dialog._on_sign_in()

        self.assertIsNotNone(dialog.session)
        assert dialog.session is not None
        self.assertEqual(dialog.session.user.role, Role.ADMIN)
        self.assertTrue(dialog.session.token.startswith("ags."))
        self.assertEqual(
            dialog.session.authorization_header,
            {"Authorization": f"Bearer {dialog.session.token}"},
        )

        # Verify raw password is NEVER written to INI file
        ini_text = self.ini_path.read_text(encoding="utf-8") if self.ini_path.exists() else ""
        self.assertNotIn("admin123", ini_text)
        state = self.settings.load_session_state()
        self.assertEqual(state.session_id, dialog.session.session_id)
        self.assertEqual(state.last_username, "admin")
        dialog.deleteLater()

        # Next LoginDialog pre-fills remembered username
        dialog2 = LoginDialog(self.auth, self.settings)
        self.assertEqual(dialog2.username.text(), "admin")
        dialog2.deleteLater()

    def test_token_tampering_expiry_revocation_and_mid_session_deactivation(self) -> None:
        t0 = datetime(2026, 11, 6, 8, 0, 0)
        session = self.auth.login(
            "inspector", "inspector123", station_name="STATION-02", ttl_seconds=600, now=t0
        )
        assert session is not None
        self.assertIsNotNone(self.auth.validate_token(session.token, now=t0 + timedelta(seconds=300)))

        # Tamper with role claim inside payload -> signature check must reject
        prefix, payload_b64, sig_b64 = session.token.split(".")
        pad = "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64 + pad).decode("utf-8"))
        claims["role"] = "Admin"
        forged_b64 = base64.urlsafe_b64encode(
            json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ).rstrip(b"=").decode("ascii")
        forged_token = f"{prefix}.{forged_b64}.{sig_b64}"
        self.assertIsNone(self.auth.validate_token(forged_token, now=t0 + timedelta(seconds=60)))

        # MainWindow expiry handling forces logout and revokes token
        win = MainWindow(session.user, self.auth, self.repo, self.settings, auth_session=session)
        self.assertEqual(win.session_badge.property("state"), "active")
        expired_notices: list[str] = []
        logged_out: list[bool] = []
        win.session_expired.connect(expired_notices.append)
        win.logout_requested.connect(lambda: logged_out.append(True))

        self.assertFalse(win.verify_auth_session(now=t0 + timedelta(seconds=601)))
        self.assertEqual(win.session_badge.property("state"), "expired")
        self.assertEqual(len(expired_notices), 1)
        self.assertEqual(logged_out, [True])
        self.assertIsNone(self.auth.validate_token(session.token, now=t0 + timedelta(seconds=10)))
        win.deleteLater()

        # Account deactivation immediately revokes active session
        s2 = self.auth.login("reviewer", "reviewer123", now=t0)
        assert s2 is not None
        self.auth.set_user_active("reviewer", False)
        self.assertIsNone(self.auth.validate_token(s2.token, now=t0))


class TestCatalogSearchConflictAndLiveSync(unittest.TestCase):
    """Trello #2 + Real-world catalog search, duplicate warning, and dirty guard."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = AppSettings(Path(self.tmp.name) / "settings.ini")
        self.auth = MockAuthService()
        self.repo = MockRepository(seed=41)
        session = self.auth.login("admin", "admin123")
        assert session is not None
        self.win = MainWindow(session.user, self.auth, self.repo, self.settings, auth_session=session)

    def tearDown(self) -> None:
        self.win.shutdown()
        self.win.deleteLater()
        self.tmp.cleanup()

    def test_search_duplicate_conflict_navigation_guard_and_intake_sync(self) -> None:
        catalog = self.win.catalog_page
        intake = self.win.box_intake_page
        assert catalog is not None and intake is not None

        # Load Banana box on Intake first
        self.assertTrue(intake.load_code("AGS:DH00123-02/10"))
        self.assertEqual(intake.criteria_table.item(0, 1).text(), "10.0%")

        # Navigate to Catalog, test live search filter
        self.assertTrue(self.win.navigate_to(PageKey.CATALOG))
        catalog.search_field.setText("mango")
        self.assertEqual(catalog.product_table.rowCount(), 1)
        self.assertEqual(catalog.code_field.text(), "MANGO")
        catalog.search_field.clear()
        self.assertEqual(catalog.product_table.rowCount(), 3)

        # Select BANANA, trigger live duplicate criterion warning
        catalog._select_row(0)
        self.assertEqual(catalog.code_field.text(), "BANANA")
        combo_row1 = catalog.criteria_table.cellWidget(1, catalog._COL_CLASS)
        combo_row1.setCurrentText("bruised")
        self.assertFalse(catalog.conflict_label.isHidden())
        self.assertIn("bruised", catalog.conflict_label.text())

        # Unsaved changes guard blocks accidental page switch when user clicks No
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            switched = self.win.navigate_to(PageKey.DASHBOARD)
        self.assertFalse(switched)
        self.assertEqual(self.win.current_page, PageKey.CATALOG)

        # Fix duplicate, update bruised threshold to 6.5%, save -> syncs live to Intake!
        combo_row1.setCurrentText("rotten")
        spin_row0 = catalog.criteria_table.cellWidget(0, catalog._COL_RATIO)
        spin_row0.setValue(6.5)
        self.assertTrue(catalog.conflict_label.isHidden())
        catalog._on_save()
        self.assertFalse(catalog.is_dirty)

        # BoxIntakePage automatically reflects 6.5% for the loaded Banana box
        self.assertEqual(intake.criteria_table.item(0, 1).text(), "6.5%")


class TestQrEncoderScannerLookupAndDisplay(unittest.TestCase):
    """Trello #3 & #4 + ISO QR verification, debounce, errors, and duplicate guard."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = AppSettings(Path(self.tmp.name) / "settings.ini")
        self.auth = MockAuthService()
        self.repo = MockRepository(seed=53)
        session = self.auth.login("admin", "admin123")
        assert session is not None
        self.win = MainWindow(session.user, self.auth, self.repo, self.settings, auth_session=session)

    def tearDown(self) -> None:
        self.win.shutdown()
        self.win.deleteLater()
        self.tmp.cleanup()

    def test_iso_qr_encoder_roundtrip_reed_solomon_and_format_bits(self) -> None:
        payload = "AGS:DH00123-03/10"
        matrix = encode_qr_matrix(payload)
        self.assertEqual(len(matrix), 25)  # Version 2-M = 25x25

        # Extract 15-bit top-left format word and find matching mask_id (ECC M = 0b00)
        tl_cols = (0, 1, 2, 3, 4, 5, 7, 8)
        tl_rows = (7, 5, 4, 3, 2, 1, 0)
        fmt = 0
        for col in tl_cols:
            fmt = (fmt << 1) | int(matrix[8][col])
        for row in tl_rows:
            fmt = (fmt << 1) | int(matrix[row][8])

        matched_masks = [m for m in range(8) if format_bits(0b00, m) == fmt]
        self.assertEqual(len(matched_masks), 1)
        mask_id = matched_masks[0]

        # Unmask data modules and verify Reed-Solomon syndromes == all zeros
        _, is_func = _build_base_grid(version=2)
        coords = _zigzag_coords(25, is_func)
        bits = [
            int(matrix[r][c] ^ _mask_bit(mask_id, r, c))
            for r, c in coords[:44 * 8]
        ]
        codewords = [
            sum(bits[i + k] << (7 - k) for k in range(8))
            for i in range(0, len(bits), 8)
        ]
        self.assertEqual(rs_syndromes(codewords, 16), [0] * 16)

        # Decode Byte-mode header & payload bytes
        mode = sum(bits[k] << (3 - k) for k in range(4))
        length = sum(bits[4 + k] << (7 - k) for k in range(8))
        self.assertEqual(mode, 0b0100)
        self.assertEqual(length, len(payload))
        decoded = bytes(
            sum(bits[12 + b * 8 + k] << (7 - k) for k in range(8))
            for b in range(length)
        ).decode("utf-8")
        self.assertEqual(decoded, payload)

    def test_intake_displays_order_lot_size_category_criteria_and_categorized_errors(self) -> None:
        intake = self.win.box_intake_page
        assert intake is not None

        # Verify all 7 categorized error cases
        cases = [
            ("   ",                 "ERR_EMPTY_CODE"),
            ("8934567890123",       "ERR_RETAIL_BARCODE"),
            ("DH00123-03/10",       "ERR_MISSING_PREFIX"),
            ("NOT-A-QR",            "ERR_INVALID_FORMAT"),
            ("AGS:DH00123-15/10",   "ERR_BOX_OUT_OF_RANGE"),
            ("AGS:DH99999-01/10",   "ERR_ORDER_NOT_FOUND"),
            ("AGS:DH00123-03/12",   "ERR_LOT_MISMATCH"),
        ]
        for bad_input, expected_code in cases:
            self.assertFalse(intake.load_code(bad_input), f"Expected failure for {bad_input!r}")
            self.assertEqual(intake.last_error_code, expected_code)
            self.assertFalse(intake.error_label.isHidden())
            self.assertTrue(intake.info_card.isHidden())
            self.assertTrue(intake.criteria_card.isHidden())

        # Manual lookup accepts a smudged box label missing the AGS: prefix
        self.assertTrue(intake.lookup_by_order_code("dh00123-03/10"))
        self.assertEqual(intake.scan_field.text(), "AGS:DH00123-03/10")

        # Manual lookup by unknown order code
        self.assertFalse(intake.lookup_by_order_code("DH99999"))
        self.assertEqual(intake.last_error_code, "ERR_ORDER_NOT_FOUND")

        # Manual lookup by valid order code (lowercase + spaces handled)
        self.assertTrue(intake.lookup_by_order_code("  dh00124  ", box_number=3))
        self.assertEqual(intake.scan_field.text(), "AGS:DH00124-03/08")
        self.assertFalse(intake.info_card.isHidden())
        self.assertFalse(intake.criteria_card.isHidden())

        fields_map = _grid_texts(intake.info_grid)
        self.assertEqual(fields_map["ORDER"], "DH00124")
        self.assertIn("8 boxes", fields_map["LOT SIZE"])
        self.assertIn("180 units", fields_map["LOT SIZE"])
        self.assertEqual(fields_map["DECLARED CATEGORY"], "Fruit")
        self.assertIn("Mango", fields_map["DECLARED PRODUCT"])
        self.assertEqual(fields_map["YOLO MODEL"], "mango_defect.onnx")

        # Criteria table shows Mango's bruised (12.0%) and rotten (Critical) rules
        self.assertEqual(intake.criteria_table.rowCount(), 2)
        self.assertEqual(intake.criteria_table.item(0, 0).text(), "bruised")
        self.assertEqual(intake.criteria_table.item(0, 1).text(), "12.0%")
        self.assertEqual(intake.criteria_table.item(1, 0).text(), "rotten")
        self.assertIn("Critical", intake.criteria_table.item(1, 2).text())

    def test_scanner_debounce_qr_dialog_simulation_and_duplicate_session_guard(self) -> None:
        intake = self.win.box_intake_page
        assert intake is not None

        # QrLabelDialog simulate scan loads directly into BoxIntakePage
        qr_dialog = QrLabelDialog(self.repo, initial_code="AGS:DH00124-01/08")
        self.assertGreater(qr_dialog.qr_widget.to_image().width(), 100)
        qr_dialog.code_scanned.connect(intake._on_simulated_qr_scan)
        qr_dialog._on_simulate_scan()
        qr_dialog.deleteLater()
        self.assertEqual(intake.scan_field.text(), "AGS:DH00124-01/08")

        # Hardware scanner double-trigger within 350 ms is debounced
        intake.scan_field.setText("AGS:DH00124-02/08")
        with patch("agroscan.ui.pages.box_intake_page.time.monotonic", side_effect=[100.0, 100.12, 101.0]):
            intake._on_scan_return_pressed()  # t = 100.00s -> accepted
            intake._on_scan_return_pressed()  # t = 100.12s -> bounce suppressed!
            self.assertEqual(intake.suppressed_scan_bounces, 1)
            intake._on_scan_return_pressed()  # t = 101.00s -> accepted (> 350ms)
            self.assertEqual(intake.suppressed_scan_bounces, 1)

        # Open session for DH00124-02/08, then return to Box Intake and scan SAME box -> D-021 guard!
        intake._on_start()
        self.assertEqual(self.win.current_page, PageKey.LIVE_INSPECTION)
        self.assertTrue(self.win.navigate_to(PageKey.BOX_INTAKE))
        self.assertFalse(intake.resume_banner.isHidden())

        self.assertTrue(intake.load_code("AGS:DH00124-02/08"))
        self.assertFalse(intake.active_box_label.isHidden())
        self.assertFalse(intake.btn_start.isEnabled())


if __name__ == "__main__":
    unittest.main()
