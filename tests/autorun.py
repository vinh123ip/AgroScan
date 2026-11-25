"""Pure Automated GUI Demo Runner for AgroScan (~3 minutes).

Automatically drives the PySide6 desktop application across all three roles
(Inspector -> Reviewer -> Admin) in 3m 00s (180s at 1.0x), with every idle
wait strictly under 5 seconds and no script/narration output in the terminal.

Usage:
    python tests/autorun.py                  # Default 3m 00s run (pure UI)
    python tests/autorun.py --speed 0.85     # Slower pace
    python tests/autorun.py --speed 1.5      # Faster pace
    python tests/autorun.py --banner         # Optional compact step counter badge
    python tests/autorun.py --headless-check # Fast automated verification

Hotkeys while running:
    F8       : Pause / Resume
    F10      : Stop automation & keep current window open for manual control
    F9       : Toggle compact step badge
    Ctrl + Q : Quit immediately (or close the window with [X])
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Auto-redirect to .venv python if launched with global python
if "--no-venv-redirect" not in sys.argv:
    if os.name == "nt":
        venv_python = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = ROOT_DIR / ".venv" / "bin" / "python"

    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        import subprocess

        sys.exit(
            subprocess.call(
                [str(venv_python), __file__, "--no-venv-redirect"] + sys.argv[1:]
            )
        )

if "--headless-check" in sys.argv:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
else:
    os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import (  # noqa: E402
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QRect,
    Qt,
    QThreadPool,
    QTimer,
)
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QWidget,
)

from agroscan.models.inspection_models import ReviewerDecision  # noqa: E402
from agroscan.services import mock_ai  # noqa: E402
from agroscan.services.app_settings import AppSettings  # noqa: E402
from agroscan.services.mock_auth import MockAuthService  # noqa: E402
from agroscan.services.mock_repository import MockRepository  # noqa: E402
from agroscan.ui.components.qr_label_dialog import QrLabelDialog  # noqa: E402
from agroscan.ui.main_window import MainWindow  # noqa: E402
from agroscan.ui.navigation import PageKey  # noqa: E402
from agroscan.ui.pages.login_dialog import LoginDialog  # noqa: E402
from agroscan.ui.pages.settings_page import SettingsPage  # noqa: E402
from agroscan.ui.theme import apply_theme  # noqa: E402

DEMO_BOX_CODE = "AGS:DH00124-01/08"


@dataclass
class AutoStep:
    """Single timed action in the automated sequence."""

    label: str
    duration_ms: int
    action: Callable[[], None]


class StepBadgeOverlay(QWidget):
    """Optional minimal step badge (hidden by default; toggleable via F9 or --banner)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedHeight(44)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 4, 20, 6)

        self.pill = QWidget(self)
        self.pill.setObjectName("AutorunStepPill")
        self.pill.setStyleSheet(
            """
            #AutorunStepPill {
                background-color: rgba(15, 23, 42, 220);
                border: 1px solid #2563EB;
                border-radius: 17px;
            }
            """
        )

        pill_layout = QHBoxLayout(self.pill)
        pill_layout.setContentsMargins(14, 4, 14, 4)
        pill_layout.setSpacing(8)

        self.badge_label = QLabel("01/18")
        self.badge_label.setStyleSheet(
            """
            background-color: #2563EB;
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 9px;
            """
        )
        pill_layout.addWidget(self.badge_label)

        self.text_label = QLabel("")
        self.text_label.setStyleSheet(
            "color: #F8FAFC; font-size: 12px; font-weight: 600; background: transparent;"
        )
        pill_layout.addWidget(self.text_label)

        shadow = QGraphicsDropShadowEffect(self.pill)
        shadow.setBlurRadius(14)
        shadow.setColor(QColor(15, 23, 42, 85))
        shadow.setOffset(0, 3)
        self.pill.setGraphicsEffect(shadow)

        outer.addStretch()
        outer.addWidget(self.pill)
        outer.addStretch()

    def update_state(
        self, step_no: int, total: int, label: str, paused: bool = False
    ) -> None:
        color = "#D97706" if paused else "#2563EB"
        prefix = "PAUSED " if paused else ""
        self.badge_label.setText(f"{prefix}{step_no:02d}/{total:02d}")
        self.badge_label.setStyleSheet(
            f"""
            background-color: {color};
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 9px;
            """
        )
        self.text_label.setText(label)
        self.sync_to_parent()

    def sync_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(0, max(8, parent.height() - 52), parent.width(), 44)
            self.raise_()


def render_synthetic_capture(
    box_code: str, product_name: str, supplier: str, capture_index: int
) -> QImage:
    """Create a fallback sample frame when no physical webcam is available."""
    width, height = 960, 600
    img = QImage(width, height, QImage.Format.Format_RGB32)

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    bg = QLinearGradient(0, 0, width, height)
    bg.setColorAt(0.0, QColor("#1E293B"))
    bg.setColorAt(1.0, QColor("#0F172A"))
    painter.fillRect(0, 0, width, height, bg)

    crate_rect = QRect(90, 82, width - 180, height - 164)
    painter.setPen(QPen(QColor("#64748B"), 3))
    painter.setBrush(QColor("#334155"))
    painter.drawRoundedRect(crate_rect, 18, 18)

    inner_rect = crate_rect.adjusted(22, 22, -22, -22)
    painter.setPen(QPen(QColor("#475569"), 2))
    painter.setBrush(QColor("#1E293B"))
    painter.drawRoundedRect(inner_rect, 12, 12)

    cols, rows = 5, 3
    cell_w = (inner_rect.width() - 60) // cols
    cell_h = (inner_rect.height() - 70) // rows
    for r in range(rows):
        for c in range(cols):
            cx = inner_rect.left() + 30 + c * cell_w + 10
            cy = inner_rect.top() + 24 + r * cell_h + 8
            is_bruised = (r == 1 and c == 3) or (capture_index == 2 and r == 0 and c == 1)
            fill = QColor("#D97706") if is_bruised else QColor("#F59E0B")
            border = QColor("#EF4444") if is_bruised else QColor("#22C55E")

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawEllipse(cx + 8, cy + 6, cell_w - 32, cell_h - 24)

            if is_bruised:
                painter.setBrush(QColor("#78350F"))
                painter.drawEllipse(cx + 26, cy + 18, 18, 12)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(border, 2, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(cx + 4, cy + 2, cell_w - 24, cell_h - 16, 6, 6)

    sticker = QRect(inner_rect.right() - 275, inner_rect.bottom() - 84, 255, 68)
    painter.setPen(QPen(QColor("#CBD5E1"), 1))
    painter.setBrush(QColor("#F8FAFC"))
    painter.drawRoundedRect(sticker, 6, 6)

    painter.setPen(QColor("#0F172A"))
    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    painter.drawText(sticker.adjusted(12, 8, -10, -34), Qt.AlignmentFlag.AlignLeft, box_code)
    painter.setFont(QFont("Segoe UI", 8))
    painter.setPen(QColor("#334155"))
    painter.drawText(
        sticker.adjusted(12, 28, -10, -6),
        Qt.AlignmentFlag.AlignLeft,
        f"{product_name}  |  {supplier}\nCapture #{capture_index}  •  {datetime.now():%H:%M:%S}",
    )

    painter.setPen(QColor("#E2E8F0"))
    painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
    painter.drawText(
        28,
        38,
        f"SAMPLE FRAME #{capture_index}  —  SIMULATED CAMERA INPUT",
    )

    painter.end()
    return img


class AutorunController(QObject):
    """Drives the automated ~5-minute AgroScan walkthrough silently."""

    def __init__(
        self,
        app: QApplication,
        speed: float = 1.0,
        show_banner: bool = False,
        headless_check: bool = False,
    ) -> None:
        super().__init__()
        self.app = app
        self.speed = max(0.25, speed)
        self.banner_visible = show_banner
        self.headless_check = headless_check

        self._tmp_dir = tempfile.TemporaryDirectory()
        self.settings = AppSettings(Path(self._tmp_dir.name) / "autorun_settings.ini")
        if headless_check:
            cfg = self.settings.load()
            cfg.ai_timeout_s = 1
            self.settings.save(cfg)
        self.auth = MockAuthService(session_ttl_seconds=8 * 3600)
        self.repo = MockRepository(seed=42)

        self.login_dialog: Optional[LoginDialog] = None
        self.qr_dialog: Optional[QrLabelDialog] = None
        self.main_window: Optional[MainWindow] = None
        self.hud: Optional[StepBadgeOverlay] = None

        self._active_anims: list[QPropertyAnimation] = []
        self._scheduled_actions: list[tuple[int, Callable[[], None]]] = []
        self._step_index = -1
        self._paused = False
        self._stopped_auto = False
        self._internal_closing = False
        self._quitting = False
        self._elapsed_ms = 0
        self._remaining_ms = 0
        self._tick_interval_ms = 20 if headless_check else 50

        if headless_check:
            MainWindow._LOADING_TRANSITION_MS = 20

        self._step_timer = QTimer(self)
        self._step_timer.setInterval(self._tick_interval_ms)
        self._step_timer.timeout.connect(self._on_step_tick)

        self.steps: list[AutoStep] = self._build_steps()
        self.app.installEventFilter(self)

    # ------------------------------------------------------------------
    # Timing & UI animation helpers
    # ------------------------------------------------------------------

    def _ms(self, base_ms: int) -> int:
        if self.headless_check:
            return max(20, int(base_ms / 36.0))
        return max(100, int(base_ms / self.speed))

    def _later(self, delay_ms: int, callback: Callable[[], None]) -> None:
        if self._stopped_auto or self._quitting:
            return
        self._scheduled_actions.append((self._elapsed_ms + self._ms(delay_ms), callback))

    def _clear_sub_timers(self) -> None:
        self._scheduled_actions.clear()
        for anim in self._active_anims:
            try:
                anim.stop()
            except RuntimeError:
                pass
        self._active_anims.clear()

    def _type_into(self, field, text: str, start_ms: int = 0, char_ms: int = 60) -> None:
        if self.headless_check:
            self._later(start_ms, lambda: field.setText(text))
            return
        self._later(start_ms, field.clear)
        for i in range(1, len(text) + 1):
            partial = text[:i]
            self._later(start_ms + i * char_ms, lambda t=partial: field.setText(t))

    def _smooth_scroll(
        self, scroll_area: Optional[QScrollArea], ratio: float, duration_ms: int = 900
    ) -> None:
        if scroll_area is None:
            return
        bar = scroll_area.verticalScrollBar()
        if bar is None or bar.maximum() <= 0:
            return
        target = int(bar.maximum() * max(0.0, min(1.0, ratio)))
        if self.headless_check:
            bar.setValue(target)
            return
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(max(200, int(duration_ms / self.speed)))
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.start()
        self._active_anims.append(anim)

    def _detach_hud(self) -> None:
        hud, self.hud = self.hud, None
        if hud is not None:
            try:
                hud.hide()
                hud.setParent(None)
                hud.deleteLater()
            except RuntimeError:
                pass

    def _attach_hud(self, host: QWidget) -> None:
        self._detach_hud()
        self.hud = StepBadgeOverlay(host)
        self.hud.sync_to_parent()
        self.hud.setVisible(self.banner_visible and not self.headless_check)
        if 0 <= self._step_index < len(self.steps):
            step = self.steps[self._step_index]
            self.hud.update_state(
                self._step_index + 1, len(self.steps), step.label, self._paused
            )

    # ------------------------------------------------------------------
    # Hotkeys & Window Close handling
    # ------------------------------------------------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Resize and self.hud is not None:
            try:
                if watched is self.hud.parentWidget():
                    self.hud.sync_to_parent()
            except RuntimeError:
                self.hud = None
        elif event.type() == QEvent.Type.Close:
            if not self._internal_closing and not self._quitting and (
                watched is self.main_window or watched is self.login_dialog
            ):
                if self.main_window is not None:
                    if (
                        self.main_window.catalog_page is not None
                        and self.main_window.catalog_page.is_dirty
                    ):
                        self.main_window.catalog_page._on_revert()
                    self.main_window.shutdown()
                QTimer.singleShot(0, self.stop_and_quit)
        elif event.type() == QEvent.Type.KeyPress:
            key_event = event  # type: ignore[assignment]
            if isinstance(key_event, QKeyEvent):
                if (
                    key_event.key() == Qt.Key.Key_Q
                    and key_event.modifiers() & Qt.KeyboardModifier.ControlModifier
                ):
                    self.stop_and_quit()
                    return True
                if key_event.key() == Qt.Key.Key_F8:
                    self.toggle_pause()
                    return True
                if key_event.key() == Qt.Key.Key_F10:
                    self.stop_autorun()
                    return True
                if key_event.key() == Qt.Key.Key_F9:
                    self.toggle_banner()
                    return True
        return super().eventFilter(watched, event)

    def toggle_pause(self) -> None:
        if self._stopped_auto:
            return
        self._paused = not self._paused
        if self.hud is not None and 0 <= self._step_index < len(self.steps):
            self.hud.update_state(
                self._step_index + 1,
                len(self.steps),
                self.steps[self._step_index].label,
                paused=self._paused,
            )

    def stop_autorun(self) -> None:
        if self._stopped_auto or self._quitting:
            return
        self._stopped_auto = True
        self._paused = False
        self._step_timer.stop()
        self._clear_sub_timers()
        self.app.setQuitOnLastWindowClosed(True)
        if self.hud is not None:
            self.hud.hide()

    def stop_and_quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._stopped_auto = True
        self._step_timer.stop()
        self._teardown_all()
        self.app.quit()

    def toggle_banner(self) -> None:
        self.banner_visible = not self.banner_visible
        if self.hud is not None:
            self.hud.setVisible(self.banner_visible and not self.headless_check)

    # ------------------------------------------------------------------
    # Sequence runner (no terminal narration output)
    # ------------------------------------------------------------------

    def start(self) -> None:
        total_sec = sum(self._ms(s.duration_ms) for s in self.steps) / 1000.0
        mins, secs = divmod(int(round(total_sec)), 60)
        print(
            f"AgroScan Auto-Run started ({mins}m {secs:02d}s at {self.speed:.2f}x)  |  "
            "F8: Pause/Resume  |  F10: Stop Auto  |  F9: Badge  |  Ctrl+Q / [X]: Quit"
        )
        self.app.setQuitOnLastWindowClosed(False)
        self._advance_step()

    def _on_step_tick(self) -> None:
        if self._paused or self._stopped_auto or self._quitting:
            return
        self._elapsed_ms += self._tick_interval_ms
        self._remaining_ms -= self._tick_interval_ms

        if self._scheduled_actions:
            due = [item for item in self._scheduled_actions if item[0] <= self._elapsed_ms]
            if due:
                self._scheduled_actions = [
                    item for item in self._scheduled_actions if item[0] > self._elapsed_ms
                ]
                for _, fn in due:
                    if self._stopped_auto or self._quitting:
                        return
                    fn()

        if self._remaining_ms <= 0:
            self._step_timer.stop()
            self._advance_step()

    def _advance_step(self) -> None:
        if self._stopped_auto or self._quitting:
            return
        self._clear_sub_timers()
        self._step_index += 1
        if self._step_index >= len(self.steps):
            self._on_demo_completed()
            return

        step = self.steps[self._step_index]
        self._elapsed_ms = 0
        self._remaining_ms = self._ms(step.duration_ms)

        step.action()

        if self.hud is not None:
            try:
                self.hud.update_state(
                    self._step_index + 1, len(self.steps), step.label, self._paused
                )
            except RuntimeError:
                self.hud = None

        self._step_timer.start()

    def _on_demo_completed(self) -> None:
        self._stopped_auto = True
        if self.headless_check:
            try:
                matched = [
                    r for r in self.repo.records if r.session.box_code.text == DEMO_BOX_CODE
                ]
                assert matched, f"Expected submitted record for {DEMO_BOX_CODE}"
                rec = matched[-1]
                assert rec.deep_analysis is not None, "Expected Qwen-VL deep analysis on record"
                assert (
                    rec.review is not None and rec.review.decision == ReviewerDecision.PASS
                ), "Expected Reviewer PASS decision on submitted record"
                banana = self.repo.find_product("BANANA")
                assert banana is not None and abs(banana.criteria[0].max_ratio - 0.085) < 1e-4, (
                    "Expected Admin Catalog edit (8.5%) to persist in MockRepository"
                )
                print("AgroScan Auto-Run headless check passed.")
            except Exception:
                self._teardown_all()
                self.app.exit(1)
                raise
            self._teardown_all()
            self.app.quit()
        else:
            print("AgroScan Auto-Run completed.")
            if self.hud is not None:
                self.hud.hide()
            self.app.setQuitOnLastWindowClosed(True)

    def _teardown_all(self) -> None:
        self._internal_closing = True
        try:
            self._clear_sub_timers()
            self._detach_hud()
            QThreadPool.globalInstance().waitForDone(2500)
            for dlg in (self.qr_dialog, self.login_dialog):
                if dlg is not None:
                    dlg.close()
                    dlg.deleteLater()
            self.qr_dialog = self.login_dialog = None
            if self.main_window is not None:
                if (
                    self.main_window.catalog_page is not None
                    and self.main_window.catalog_page.is_dirty
                ):
                    self.main_window.catalog_page._on_revert()
                self.main_window.shutdown()
                self.main_window.close()
                self.main_window.deleteLater()
                self.main_window = None
            self._tmp_dir.cleanup()
        finally:
            self._internal_closing = False

    # ------------------------------------------------------------------
    # Window transition helpers
    # ------------------------------------------------------------------

    def _open_login_dialog(self, notice: str = "") -> LoginDialog:
        self._internal_closing = True
        try:
            self._detach_hud()
            if self.main_window is not None:
                if (
                    self.main_window.catalog_page is not None
                    and self.main_window.catalog_page.is_dirty
                ):
                    self.main_window.catalog_page._on_revert()
                self.main_window.shutdown()
                self.auth.logout(self.main_window.auth_session.token)
                self.main_window.hide()
                self.main_window.deleteLater()
                self.main_window = None

            if self.login_dialog is not None:
                self.login_dialog.hide()
                self.login_dialog.deleteLater()
        finally:
            self._internal_closing = False

        dlg = LoginDialog(self.auth, self.settings, notice=notice)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self.login_dialog = dlg
        return dlg

    def _complete_login_into_main_window(self, username: str, password: str) -> None:
        dlg = self.login_dialog or self._open_login_dialog()
        self._internal_closing = True
        try:
            dlg._quick_sign_in(username, password)
            assert dlg.user is not None and dlg.session is not None, f"Login failed for {username}"
            user, session = dlg.user, dlg.session
            dlg.hide()
            dlg.deleteLater()
            self.login_dialog = None
        finally:
            self._internal_closing = False

        win = MainWindow(
            user=user,
            auth_service=self.auth,
            repo=self.repo,
            settings=self.settings,
            auth_session=session,
        )
        win.show()
        win.raise_()
        win.activateWindow()
        self.main_window = win
        self._attach_hud(win)

    # ------------------------------------------------------------------
    # 18-Step Timeline (Total: 180,000 ms = 3m 00s at 1.0x; max wait < 5s)
    # ------------------------------------------------------------------

    def _build_steps(self) -> list[AutoStep]:
        return [
            # Phase 1: Sign-In & Connection Setup (28s)
            AutoStep("Sign In",                     4_000, self._act_01_open_login),
            AutoStep("Disabled Account Guard",      8_000, self._act_03_test_disabled_account),
            AutoStep("Inspector Session",           7_000, self._act_04_login_inspector),
            # Phase 2: Inspector Dashboard & Box Intake (37s)
            AutoStep("Inspector Dashboard & RBAC",  8_000, self._act_05_inspector_dashboard_rbac),
            AutoStep("Switch EN / VI",              9_000, self._preview_language_switch),
            AutoStep("Box Intake — Barcode Check",  8_000, self._act_06_box_intake_barcode_error),
            AutoStep("QR Label Generator",          9_000, self._act_07_qr_dialog_and_scan),
            AutoStep("Order & Defect Criteria",    12_000, self._act_08_verify_criteria_and_start),
            # Phase 3: Live Inspection & Assessment (38s)
            AutoStep("Live Inspection Capture",    11_000, self._act_09_live_capture_evidence),
            AutoStep("Deep Analysis (Qwen-VL)",    14_000, self._act_10_run_deep_analysis),
            AutoStep("Assessment Result",          13_000, self._act_11_finish_and_submit_assessment),
            # Phase 4: Reviewer Maker-Checker Queue (23s)
            AutoStep("Switch to Reviewer",          7_500, self._act_12_switch_to_reviewer),
            AutoStep("Review Queue Decision",      15_500, self._act_13_review_submitted_box),
            # Phase 5: Admin Catalog, Settings, Placeholders & Summary (54s)
            AutoStep("Switch to Admin",             7_500, self._act_14_switch_to_admin),
            AutoStep("Catalog & Criteria Editor",  16_500, self._act_15_admin_catalog_editor),
            AutoStep("Workstation Settings",       12_000, self._act_16_admin_settings_test_all),
            AutoStep("Planned Modules",             9_000, self._act_17_show_placeholders),
            AutoStep("Final Dashboard Overview",    9_000, self._act_18_final_dashboard_summary),
        ]

    # ------------------------------------------------------------------
    # Step Actions (every screen pause strictly < 5s)
    # ------------------------------------------------------------------

    def _act_01_open_login(self) -> None:
        dlg = self._open_login_dialog()
        dlg.setWindowTitle("AgroScan — Sign In")

    def _preview_language_switch(self) -> None:
        if self.main_window is not None:
            self._later(500, self.main_window.language_button.click)
            self._later(6_000, self.main_window.language_button.click)

    def _act_03_test_disabled_account(self) -> None:
        dlg = self.login_dialog
        if dlg is None:
            return
        self._type_into(dlg.username, "inspector2", start_ms=300, char_ms=50)
        self._type_into(dlg.password, "inspector123", start_ms=1_300, char_ms=45)
        self._later(2_500, dlg._toggle_password_visibility)
        self._later(3_600, dlg._on_sign_in)

    def _act_04_login_inspector(self) -> None:
        dlg = self.login_dialog
        if dlg is None:
            return
        self._type_into(dlg.username, "inspector", start_ms=300, char_ms=50)
        self._type_into(dlg.password, "inspector123", start_ms=1_200, char_ms=45)
        self._later(2_400, lambda: dlg.chk_remember.setChecked(True))
        self._later(
            3_400, lambda: self._complete_login_into_main_window("inspector", "inspector123")
        )

    def _act_05_inspector_dashboard_rbac(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.DASHBOARD)
        dash = self.main_window.page(PageKey.DASHBOARD)
        scroll = dash.findChild(QScrollArea, "PageScrollArea") if dash else None
        self._later(800, lambda: self._smooth_scroll(scroll, 0.65, 800))
        self._later(4_500, lambda: self._smooth_scroll(scroll, 0.0, 700))

    def _act_06_box_intake_barcode_error(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.BOX_INTAKE)
        intake = self.main_window.box_intake_page
        if intake is None:
            return
        self._type_into(intake.scan_field, "8934567890123", start_ms=1_600, char_ms=50)
        self._later(3_400, intake._on_scan_return_pressed)

    def _act_07_qr_dialog_and_scan(self) -> None:
        if self.main_window is None or self.main_window.box_intake_page is None:
            return
        intake = self.main_window.box_intake_page
        intake.scan_field.clear()
        intake._hide_error()

        def open_qr() -> None:
            if self.main_window is None:
                return
            self.qr_dialog = QrLabelDialog(
                self.repo, initial_code=DEMO_BOX_CODE, parent=self.main_window
            )
            self.qr_dialog.code_scanned.connect(intake._on_simulated_qr_scan)
            self.qr_dialog.show()
            self.qr_dialog.raise_()

        def copy_qr_code() -> None:
            if self.qr_dialog is not None:
                self.qr_dialog._on_copy()

        def trigger_qr_scan() -> None:
            if self.qr_dialog is not None:
                self.qr_dialog._on_simulate_scan()
                self.qr_dialog.deleteLater()
                self.qr_dialog = None

        self._later(300, open_qr)
        self._later(4_000, copy_qr_code)
        self._later(7_200, trigger_qr_scan)

    def _act_08_verify_criteria_and_start(self) -> None:
        if self.main_window is None or self.main_window.box_intake_page is None:
            return
        intake = self.main_window.box_intake_page
        if intake.current_box_code is None:
            intake.load_code(DEMO_BOX_CODE)

        scroll = intake.findChild(QScrollArea, "PageScrollArea")
        self._later(
            2_000,
            lambda: intake.notes_field.setPlainText(
                "Intact outer carton, top layer dry — standard random sample inspection."
            ),
        )
        self._later(5_200, lambda: self._smooth_scroll(scroll, 1.0, 900))
        self._later(10_200, intake._on_start)

    def _act_09_live_capture_evidence(self) -> None:
        if self.main_window is None or self.main_window.live_inspection_page is None:
            return
        live = self.main_window.live_inspection_page

        def capture_frame(index: int) -> None:
            if live.session is None:
                return
            before_count = len(live.captured_images)
            if (
                not self.headless_check
                and live._camera_active()
                and live._image_capture.isReadyForCapture()
            ):
                live._on_capture()

            def ensure_captured() -> None:
                if live.session is None or len(live.captured_images) > before_count:
                    return
                sample = render_synthetic_capture(
                    box_code=live.session.box_code.text,
                    product_name=live.session.product.name,
                    supplier=live.session.order.supplier,
                    capture_index=index,
                )
                live._capture_evidence(sample, "imported_image", True)
                if not live._camera_active() and live._detection is not None:
                    total = live._detection.total_objects
                    live.realtime_total.setText(f"{total}")
                    for cls, lbl in live._realtime_labels.items():
                        cnt = live._detection.class_counts.get(cls, 0)
                        share = cnt / total if total else 0.0
                        lbl.setText(f"{cnt}   ({share:.0%})")
                    live.camera_label.setText(
                        "Camera: not attached (using simulated sample frames)"
                    )

            self._later(600, ensure_captured)

        self._later(2_200, lambda: capture_frame(1))
        self._later(6_800, lambda: capture_frame(2))

    def _act_10_run_deep_analysis(self) -> None:
        if self.main_window is None or self.main_window.live_inspection_page is None:
            return
        live = self.main_window.live_inspection_page
        side_scroll = live.findChild(QScrollArea, "PageScrollArea")

        for idx in range(live.scenario_combo.count()):
            if live.scenario_combo.itemData(idx) == mock_ai.VlmScenario.NORMAL:
                live.scenario_combo.setCurrentIndex(idx)
                break

        self._later(800, live._on_deep_analysis)
        self._later(6_200, lambda: self._smooth_scroll(side_scroll, 0.55, 800))
        self._later(10_400, lambda: self._smooth_scroll(side_scroll, 0.95, 800))

    def _act_11_finish_and_submit_assessment(self) -> None:
        if self.main_window is None or self.main_window.live_inspection_page is None:
            return
        live = self.main_window.live_inspection_page
        if live._is_analyzing:
            # The accelerated walkthrough still waits for the bounded demo request.
            from PySide6.QtTest import QTest
            for _ in range(250):
                if not live._is_analyzing:
                    break
                QTest.qWait(20)
        live._on_finish()

        result_page = self.main_window.assessment_result_page
        if result_page is None:
            return
        scroll = result_page.findChild(QScrollArea, "PageScrollArea")
        self._later(3_800, lambda: self._smooth_scroll(scroll, 0.55, 800))
        self._later(7_800, lambda: self._smooth_scroll(scroll, 1.0, 800))
        def submit_demo_box():
            def confirm_coverage():
                dialog = self.app.activeModalWidget()
                if isinstance(dialog, QMessageBox) and dialog.windowTitle() == "Confirm whole-box coverage":
                    dialog.button(QMessageBox.StandardButton.Yes).click()

            QTimer.singleShot(0, confirm_coverage)
            result_page._on_submit()

        self._later(11_200, submit_demo_box)

    def _act_12_switch_to_reviewer(self) -> None:
        dlg = self._open_login_dialog()
        self._type_into(dlg.username, "reviewer", start_ms=900, char_ms=50)
        self._type_into(dlg.password, "reviewer123", start_ms=1_900, char_ms=45)
        self._later(
            3_800, lambda: self._complete_login_into_main_window("reviewer", "reviewer123")
        )

    def _act_13_review_submitted_box(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.REVIEW_QUEUE)
        review_page = self.main_window.review_queue_page
        if review_page is None:
            return

        def focus_demo_box() -> None:
            if self.main_window is None:
                return
            if self.main_window.current_page != PageKey.REVIEW_QUEUE:
                self._later(600, focus_demo_box)
                return
            review_page.refresh()
            target_row = 0
            for row in range(review_page.queue_table.rowCount()):
                item = review_page.queue_table.item(row, 0)
                if item is not None and item.text() == DEMO_BOX_CODE:
                    target_row = row
                    break
            review_page.queue_table.selectRow(target_row)

        def approve_demo_box() -> None:
            focus_demo_box()
            review_page.notes_field.setPlainText(
                "Evidence images and OCR label verified against order DH00124 — approved."
            )
            review_page._on_decide(ReviewerDecision.PASS)

        self._later(1_400, focus_demo_box)

        detail_scroll = review_page.findChild(QScrollArea, "PageScrollArea")
        self._later(5_200, lambda: self._smooth_scroll(detail_scroll, 0.55, 800))
        self._later(
            9_000,
            lambda: (
                self._smooth_scroll(detail_scroll, 1.0, 750),
                review_page.notes_field.setPlainText(
                    "Evidence images and OCR label verified against order DH00124 — approved."
                ),
            ),
        )
        self._later(12_800, approve_demo_box)

    def _act_14_switch_to_admin(self) -> None:
        dlg = self._open_login_dialog()
        self._type_into(dlg.username, "admin", start_ms=900, char_ms=55)
        self._type_into(dlg.password, "admin123", start_ms=1_800, char_ms=50)
        self._later(
            3_600, lambda: self._complete_login_into_main_window("admin", "admin123")
        )

    def _act_15_admin_catalog_editor(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.CATALOG)
        catalog = self.main_window.catalog_page
        if catalog is None:
            return

        editor_scroll = catalog.findChild(QScrollArea, "PageScrollArea")
        self._type_into(catalog.search_field, "mango", start_ms=1_800, char_ms=65)
        self._later(4_600, catalog.search_field.clear)

        def trigger_duplicate_warning() -> None:
            catalog._select_row(0)  # BANANA
            self._smooth_scroll(editor_scroll, 0.75, 750)
            if catalog.criteria_table.rowCount() >= 2:
                combo = catalog.criteria_table.cellWidget(1, catalog._COL_CLASS)
                if isinstance(combo, QComboBox):
                    combo.setCurrentText("bruised")

        def fix_and_save() -> None:
            if catalog.criteria_table.rowCount() >= 2:
                combo = catalog.criteria_table.cellWidget(1, catalog._COL_CLASS)
                if isinstance(combo, QComboBox):
                    combo.setCurrentText("rotten")
            if catalog.criteria_table.rowCount() >= 1:
                spin = catalog.criteria_table.cellWidget(0, catalog._COL_RATIO)
                if isinstance(spin, QDoubleSpinBox):
                    spin.setValue(8.5)
            self._smooth_scroll(editor_scroll, 1.0, 750)
            catalog._on_save()

        self._later(6_200, trigger_duplicate_warning)
        self._later(10_400, fix_and_save)

    def _act_16_admin_settings_test_all(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.SETTINGS)
        settings_page = self.main_window.page(PageKey.SETTINGS)
        if not isinstance(settings_page, SettingsPage):
            return
        scroll = settings_page.findChild(QScrollArea, "PageScrollArea")
        self._later(1_800, settings_page.form._on_test_all)
        self._later(5_200, lambda: self._smooth_scroll(scroll, 0.85, 850))
        self._later(9_200, lambda: self._smooth_scroll(scroll, 0.0, 750))

    def _act_17_show_placeholders(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.REPORTS)
        self._later(
            4_500,
            lambda: self.main_window.navigate_to(PageKey.DATA_IMPORT)
            if self.main_window is not None
            else None,
        )

    def _act_18_final_dashboard_summary(self) -> None:
        if self.main_window is None:
            return
        self.main_window.navigate_to(PageKey.DASHBOARD)
        dash = self.main_window.page(PageKey.DASHBOARD)
        scroll = dash.findChild(QScrollArea, "PageScrollArea") if dash else None
        self._later(3_800, lambda: self._smooth_scroll(scroll, 0.55, 800))
        self._later(7_200, lambda: self._smooth_scroll(scroll, 0.0, 700))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated 3-minute GUI demo runner for AgroScan."
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed multiplier (default: 1.0 = 3m 00s).",
    )
    parser.add_argument(
        "--banner",
        action="store_true",
        help="Show minimal step counter badge at the bottom (can also toggle with F9).",
    )
    parser.add_argument(
        "--headless-check",
        action="store_true",
        help="Run all steps offscreen at high speed and exit to verify zero errors.",
    )
    parser.add_argument(
        "--no-venv-redirect",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AgroScan")
    apply_theme(app)

    controller = AutorunController(
        app=app,
        speed=args.speed,
        show_banner=args.banner,
        headless_check=args.headless_check,
    )
    signal.signal(signal.SIGINT, lambda *_: controller.stop_and_quit())
    QTimer.singleShot(250, controller.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
