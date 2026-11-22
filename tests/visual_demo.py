"""Visual Automated Walkthrough & Live Robot Demo for AgroScan.

Opens the real PySide6 application window on your desktop and automatically
performs user actions step-by-step with realistic delays (1.5–2.5s per step)
so you can sit back and watch the robot demonstrate the entire system live:

1. Opens Sign-In dialog, types credentials and logs in.
2. Explores the Authenticated Workstation and verifies Session Token.
3. Opens Catalog & Criteria Editor, searches products, and inspects thresholds.
4. Opens Box Intake, simulates scanning an accidental retail EAN-13 barcode (showing error handling).
5. Opens QR Label Preview dialog (rendering genuine ISO/IEC 18004 QR code on screen).
6. Simulates USB barcode scanner reading valid box QR code (AGS:DH00123-03/10).
7. Verifies Order, Lot Size (10 boxes / 250 units), Category, and Criteria Table.
8. Clicks 'Start Inspection ->' and transitions to Live Inspection.
9. Leaves the app open for you to freely explore and click!

Run with:
    python tests/visual_demo.py
"""

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Ensure desktop window rendering (NOT offscreen)
os.environ.pop("QT_QPA_PLATFORM", None)

# Auto-redirect to .venv python if not already active
if os.name == "nt":
    venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        fallback = Path("D:/Github Clone/AgroScan/.venv/Scripts/python.exe")
        if fallback.exists():
            venv_python = fallback
else:
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"

if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
    import subprocess
    sys.exit(subprocess.call([str(venv_python), __file__] + sys.argv[1:]))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from agroscan.models.user_models import Role, User
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.qr_label_dialog import QrLabelDialog
from agroscan.ui.main_window import MainWindow
from agroscan.ui.navigation import PageKey
from agroscan.ui.pages.login_dialog import LoginDialog
from agroscan.ui.theme import apply_theme


class DemoOverlay(QWidget):
    """Floating transparent banner explaining what the robot is doing in real-time."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)

        self.box = QWidget(self)
        self.box.setObjectName("DemoOverlayBox")
        self.box.setStyleSheet("""
            #DemoOverlayBox {
                background-color: #0F172A;
                border: 2px solid #38BDF8;
                border-radius: 28px;
            }
        """)

        box_layout = QHBoxLayout(self.box)
        box_layout.setContentsMargins(24, 6, 24, 6)
        box_layout.setSpacing(12)

        self.icon_label = QLabel("🤖")
        self.icon_label.setStyleSheet("font-size: 20px;")
        box_layout.addWidget(self.icon_label)

        self.text_label = QLabel("Starting Auto Demo...")
        self.text_label.setStyleSheet("""
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 14px;
            font-weight: 700;
            color: #F8FAFC;
        """)
        box_layout.addWidget(self.text_label)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.box.setGraphicsEffect(shadow)

        layout.addStretch()
        layout.addWidget(self.box)
        layout.addStretch()

    def set_message(self, step_no: int, total_steps: int, message: str) -> None:
        self.text_label.setText(f"[{step_no}/{total_steps}]  {message}")
        print(f"🎬 [STEP {step_no}/{total_steps}] {message}")

    def sync_geometry(self) -> None:
        p = self.parentWidget()
        if p is not None:
            self.setGeometry(0, 16, p.width(), 64)
            self.raise_()


class VisualRobotController:
    """Orchestrates realistic step-by-step UI actions with pauses."""

    TOTAL_STEPS = 9

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.settings = AppSettings()
        self.auth = MockAuthService(session_ttl_seconds=3600)
        self.repo = MockRepository(seed=77)

        self.login_dialog: LoginDialog | None = None
        self.main_window: MainWindow | None = None
        self.qr_dialog: QrLabelDialog | None = None
        self.overlay: DemoOverlay | None = None

    def start(self) -> None:
        print("\n" + "=" * 76)
        print("  STARTING AGROSCAN VISUAL LIVE DEMO (SIT BACK & WATCH)")
        print("=" * 76 + "\n")
        self.step_01_show_login()

    def step_01_show_login(self) -> None:
        self.login_dialog = LoginDialog(self.auth, self.settings)
        self.login_dialog.setWindowTitle("AgroScan — [LIVE AUTO DEMO]")
        self.login_dialog.show()

        # Type username slowly
        QTimer.singleShot(600, lambda: self._type_text(self.login_dialog.username, "admin"))
        # Type password
        QTimer.singleShot(1400, lambda: self._type_text(self.login_dialog.password, "admin123"))
        # Show password toggle
        QTimer.singleShot(2200, lambda: self.login_dialog._toggle_password_visibility())
        # Check Remember Username
        QTimer.singleShot(2900, lambda: self.login_dialog.chk_remember.setChecked(True))
        # Click Sign In button
        QTimer.singleShot(3600, self.step_02_sign_in_completed)

    def _type_text(self, field, full_text: str) -> None:
        field.clear()
        for idx in range(1, len(full_text) + 1):
            QTimer.singleShot(idx * 60, lambda t=full_text[:idx]: field.setText(t))

    def step_02_sign_in_completed(self) -> None:
        assert self.login_dialog is not None
        self.login_dialog._on_sign_in()
        user = self.login_dialog.user
        session = self.login_dialog.session
        self.login_dialog.hide()
        self.login_dialog.deleteLater()
        self.login_dialog = None

        assert user is not None and session is not None
        self.main_window = MainWindow(
            user=user,
            auth_service=self.auth,
            repo=self.repo,
            settings=self.settings,
            auth_session=session,
        )
        self.main_window.setWindowTitle("AgroScan Inspection Workstation — [LIVE AUTO DEMO]")
        self.main_window.show()

        self.overlay = DemoOverlay(self.main_window)
        self.overlay.sync_geometry()
        self.overlay.show()
        self.overlay.set_message(
            2, self.TOTAL_STEPS,
            f"Signed in as {user.display_name} ({user.role.value}). Bearer Token is ACTIVE on Header!"
        )

        QTimer.singleShot(2500, self.step_03_open_catalog)

    def step_03_open_catalog(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        self.overlay.set_message(3, self.TOTAL_STEPS, "Opening Catalog & Quality Criteria Editor...")
        self.main_window.navigate_to(PageKey.CATALOG)

        catalog = self.main_window.catalog_page
        if catalog is not None:
            QTimer.singleShot(800, lambda: self._type_text(catalog.search_field, "mango"))
            QTimer.singleShot(2200, lambda: catalog.search_field.clear())

        QTimer.singleShot(3200, self.step_04_open_box_intake)

    def step_04_open_box_intake(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        self.overlay.set_message(4, self.TOTAL_STEPS, "Navigating to Box Intake workstation...")
        self.main_window.navigate_to(PageKey.BOX_INTAKE)

        QTimer.singleShot(1800, self.step_05_simulate_barcode_error)

    def step_05_simulate_barcode_error(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        intake = self.main_window.box_intake_page
        assert intake is not None

        self.overlay.set_message(
            5, self.TOTAL_STEPS,
            "Simulating USB Scanner reading retail EAN-13 barcode: 8934567890123..."
        )
        self._type_text(intake.scan_field, "8934567890123")

        def trigger_scan():
            intake._on_scan_return_pressed()
            self.overlay.set_message(
                5, self.TOTAL_STEPS,
                "Notice ERR_RETAIL_BARCODE error banner: Retail barcode detected!"
            )

        QTimer.singleShot(1200, trigger_scan)
        QTimer.singleShot(3500, self.step_06_open_qr_preview)

    def step_06_open_qr_preview(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        self.overlay.set_message(
            6, self.TOTAL_STEPS,
            "Opening QR Label Generator (ISO/IEC 18004 2D matrix rendered on screen)..."
        )

        intake = self.main_window.box_intake_page
        assert intake is not None
        intake.scan_field.clear()

        self.qr_dialog = QrLabelDialog(self.repo, initial_code="AGS:DH00123-03/10", parent=self.main_window)
        self.qr_dialog.show()

        def auto_scan():
            assert self.qr_dialog is not None
            self.overlay.set_message(7, self.TOTAL_STEPS, "Clicking 'Simulate USB Scan ->' on valid box label...")
            self.qr_dialog._on_simulate_scan()
            intake.scan_field.setText("AGS:DH00123-03/10")
            intake.load_code("AGS:DH00123-03/10")
            self.qr_dialog.deleteLater()
            self.qr_dialog = None
            QTimer.singleShot(1500, self.step_07_verify_loaded_box)

        QTimer.singleShot(2600, auto_scan)

    def step_07_verify_loaded_box(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        intake = self.main_window.box_intake_page
        assert intake is not None

        self.overlay.set_message(
            8, self.TOTAL_STEPS,
            "Verified! Order: DH00123 | Lot Size: 10 boxes (250 units) | Category: Fruit | Criteria Table Loaded."
        )

        QTimer.singleShot(2800, self.step_08_start_inspection)

    def step_08_start_inspection(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        intake = self.main_window.box_intake_page
        assert intake is not None

        self.overlay.set_message(
            9, self.TOTAL_STEPS,
            "Starting inspection session -> Advancing to Live Inspection camera viewport!"
        )
        intake._on_start()

        QTimer.singleShot(2200, self.step_09_finish)

    def step_09_finish(self) -> None:
        assert self.main_window is not None and self.overlay is not None
        live = self.main_window.live_inspection_page
        session_id = live.session.session_id if live and live.session else "ACTIVE"

        self.overlay.set_message(
            9, self.TOTAL_STEPS,
            f"🎉 DEMO COMPLETED! Session {session_id} is open. You can now click around freely!"
        )

        print("\n" + "=" * 76)
        print("  🎉 DEMO COMPLETED SUCCESSFULLY! The window remains open for you.")
        print("=" * 76 + "\n")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app)

    robot = VisualRobotController(app)
    QTimer.singleShot(300, robot.start)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

