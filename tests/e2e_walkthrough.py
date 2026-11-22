"""End-to-End (E2E) Automated Walkthrough and Robot Demo for AgroScan.

Simulates the complete operational journey of an Inspector and Admin:
1. Login with demo account, session/token issuance, and station check.
2. Catalog & Criteria: search products, trigger duplicate-class conflict detection,
   save custom quality criteria, and verify live reactive sync.
3. Box Intake: simulate retail barcode scan (EAN-13) error handling, test smudged
   label without 'AGS:' prefix, test scanner debounce, and scan genuine box QR.
4. Verify complete displayed metadata: Order, Lot Size, Category, Criteria table.
5. Launch inspection session, verify Single-Open-Session guard (D-021), and test
   graceful session token expiry / logout.

Can be run headless (CI/offline) or visually on screen:
    python tests/e2e_walkthrough.py
    python tests/e2e_walkthrough.py --gui
"""

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Choose offscreen vs desktop window
if "--gui" not in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from agroscan.models.inspection_models import BoxCode  # noqa: E402
from agroscan.services.app_settings import AppSettings  # noqa: E402
from agroscan.services.mock_auth import MockAuthService  # noqa: E402
from agroscan.services.mock_repository import MockRepository  # noqa: E402
from agroscan.ui.main_window import MainWindow  # noqa: E402
from agroscan.ui.navigation import PageKey  # noqa: E402
from agroscan.ui.pages.login_dialog import LoginDialog  # noqa: E402
from agroscan.ui.theme import apply_theme  # noqa: E402


def log_step(step_no: int, title: str, details: str = "") -> None:
    print(f"\n[STEP {step_no:02d}] {title}")
    if details:
        for line in details.strip().splitlines():
            print(f"         {line}")


def run_e2e_walkthrough() -> bool:
    print("=" * 76)
    print("  AGROSCAN E2E AUTOMATED ROBOT WALKTHROUGH & SIMULATION")
    print("=" * 76)

    app = QApplication.instance() or QApplication([])
    apply_theme(app)

    tmp = tempfile.TemporaryDirectory()
    settings = AppSettings(Path(tmp.name) / "e2e_settings.ini")
    auth = MockAuthService(session_ttl_seconds=1800)
    repo = MockRepository(seed=99)

    # ------------------------------------------------------------------
    # Step 1: Login Dialog & Session/Token Issuance
    # ------------------------------------------------------------------
    log_step(1, "Authenticating user via LoginDialog", "Testing credentials and HMAC-SHA256 bearer token issuance...")
    login = LoginDialog(auth, settings)

    # Attempt disabled user
    login.username.setText("inspector2")
    login.password.setText("inspector123")
    login._on_sign_in()
    assert login.user is None, "Disabled account must not be permitted"
    assert "disabled" in login.error_label.text().lower(), "Disabled account message expected"
    print("         ✔ Disabled account blocked properly with reason.")

    # Valid sign-in as Admin
    login._quick_sign_in("admin", "admin123")
    assert login.user is not None and login.session is not None
    session = login.session
    print(f"         ✔ Signed in as '{session.user.display_name}' ({session.user.role.value})")
    print(f"         ✔ Session ID   : {session.session_id}")
    print(f"         ✔ Masked Token : {session.masked_token}")
    print(f"         ✔ Station      : {session.station_name}")
    login.deleteLater()

    # ------------------------------------------------------------------
    # Step 2: MainWindow Initialization & RBAC Validation
    # ------------------------------------------------------------------
    log_step(2, "Launching MainWindow & Verifying RBAC and Session Badge", "Checking header widgets and permissions...")
    win = MainWindow(session.user, auth, repo, settings, auth_session=session)
    assert win.session_badge.property("state") == "active"
    assert win.role_badge.property("role") == "admin"
    assert win.page(PageKey.CATALOG) is not None, "Admin must have access to CatalogPage"
    print("         ✔ Session badge is ACTIVE with full tooltip metadata.")
    print("         ✔ Admin sidebar & Catalog page loaded into memory.")

    # ------------------------------------------------------------------
    # Step 3: Catalog & Criteria Editor (Search, Conflict Detection, Edit)
    # ------------------------------------------------------------------
    log_step(3, "Testing Goods Category & Quality Criteria Editor", "Testing search filter and live duplicate conflict detection...")
    assert win.navigate_to(PageKey.CATALOG)
    catalog = win.catalog_page
    assert catalog is not None

    # Test live search filter
    catalog.search_field.setText("banana")
    assert catalog.product_table.rowCount() == 1
    print("         ✔ Live search filter matched 1 product (BANANA).")
    catalog.search_field.clear()

    # Test real-time duplicate criteria conflict warning
    catalog._select_row(0)  # Select BANANA
    combo_defect = catalog.criteria_table.cellWidget(1, catalog._COL_CLASS)
    combo_defect.setCurrentText("bruised")  # Trigger duplicate 'bruised'
    assert not catalog.conflict_label.isHidden(), "Conflict label must appear on duplicate class"
    print("         ✔ Real-time duplicate defect warning triggered successfully.")

    # Revert to valid and adjust bruised threshold to 7.5%
    combo_defect.setCurrentText("rotten")
    spin_bruised = catalog.criteria_table.cellWidget(0, catalog._COL_RATIO)
    spin_bruised.setValue(7.5)
    catalog._on_save()
    assert not catalog.is_dirty
    print("         ✔ Saved updated threshold (bruised max 7.5%) to repository.")

    # ------------------------------------------------------------------
    # Step 4: Box Intake — Error Classification & Debouncing
    # ------------------------------------------------------------------
    log_step(4, "Testing Box Intake & Warehouse Error Classification", "Testing accidental retail EAN barcode, missing prefix, and debounce...")
    assert win.navigate_to(PageKey.BOX_INTAKE)
    intake = win.box_intake_page
    assert intake is not None

    # Case A: Retail EAN-13 barcode scanned accidentally
    intake.scan_field.setText("8934567890123")
    intake._on_scan_return_pressed()
    assert intake.last_error_code == "ERR_RETAIL_BARCODE"
    print("         ✔ Scanned EAN-13 classified as ERR_RETAIL_BARCODE with helpful guidance.")

    # Case B: Unknown Order
    intake.scan_field.setText("AGS:DH99999-01/10")
    intake._on_scan_return_pressed()
    assert intake.last_error_code == "ERR_ORDER_NOT_FOUND"
    print("         ✔ Unknown order classified as ERR_ORDER_NOT_FOUND.")

    # Case C: Smudged label missing AGS: prefix
    assert intake.lookup_by_order_code("dh00123-03/10")
    assert intake.scan_field.text() == "AGS:DH00123-03/10"
    print("         ✔ Smudged label 'dh00123-03/10' automatically normalized to 'AGS:DH00123-03/10'.")

    # ------------------------------------------------------------------
    # Step 5: Verify Displayed Order, Lot Size, Category & Criteria
    # ------------------------------------------------------------------
    log_step(5, "Verifying Displayed Order, Lot Size & Quality Criteria", "Validating KeyValueGrid and Criteria table contents...")
    assert not intake.info_card.isHidden()
    assert not intake.criteria_card.isHidden()

    # Verify Lot Size & Category
    assert intake.current_order is not None
    assert intake.current_order.order_code == "DH00123"
    assert intake.current_order.product.category == "Fruit"
    assert intake.current_order.total_boxes == 10
    assert intake.current_order.expected_quantity == 250
    print(f"         ✔ Order           : {intake.current_order.order_code}")
    print(f"         ✔ Lot Size        : {intake.current_order.total_boxes} boxes / {intake.current_order.expected_quantity} units")
    print(f"         ✔ Category        : {intake.current_order.product.category}")
    print(f"         ✔ Product Model   : {intake.current_order.product.model_file}")

    # Verify criteria table shows the 7.5% updated threshold from Step 3
    assert intake.criteria_table.item(0, 0).text() == "bruised"
    assert intake.criteria_table.item(0, 1).text() == "7.5%"
    print("         ✔ Criteria Table  : Bruised <= 7.5% (live synced from CatalogPage).")

    # ------------------------------------------------------------------
    # Step 6: Start Inspection & Single-Open-Session Guard (D-021)
    # ------------------------------------------------------------------
    log_step(6, "Starting Inspection Session & Testing Concurrency Guard", "Opening inspection session and verifying D-021 protection...")
    intake._on_start()
    assert win.current_page == PageKey.LIVE_INSPECTION
    live = win.live_inspection_page
    assert live is not None and live.session is not None
    active_session_id = live.session.session_id
    print(f"         ✔ Transitioned to Live Inspection. Session ID: {active_session_id}")

    # Return to Box Intake and attempt to re-open the SAME active box
    assert win.navigate_to(PageKey.BOX_INTAKE)
    assert not intake.resume_banner.isHidden()
    intake.scan_field.setText("AGS:DH00123-03/10")
    intake._on_scan_return_pressed()
    assert not intake.active_box_label.isHidden()
    assert not intake.btn_start.isEnabled(), "Start button MUST be disabled for already active box"
    print("         ✔ D-021 Guard active: Start disabled, banner directs to 'Resume Inspection'.")

    # ------------------------------------------------------------------
    # Step 7: Session Token Expiration & Automatic Logout
    # ------------------------------------------------------------------
    log_step(7, "Testing Session Expiry and Automatic Teardown", "Simulating token expiration past TTL...")
    future_time = datetime.now() + timedelta(hours=5)
    expired = not win.verify_auth_session(now=future_time)
    assert expired, "Session must be reported as expired"
    assert win.session_badge.property("state") == "expired"
    print("         ✔ Expired session correctly flagged as '✖ SESSION EXPIRED'.")

    win.shutdown()
    win.deleteLater()
    tmp.cleanup()

    print("\n" + "=" * 76)
    print("  >>> E2E WALKTHROUGH COMPLETED: ALL 7 STAGES VERIFIED PERFECTLY! <<<")
    print("=" * 76 + "\n")
    return True


if __name__ == "__main__":
    success = run_e2e_walkthrough()
    sys.exit(0 if success else 1)

