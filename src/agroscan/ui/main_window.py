"""Main application window: dynamic role-based sidebar, header, and page registry.

Pages are addressed exclusively by ``PageKey`` (``navigation.py``, P-006). Each
page is instantiated only when the signed-in role has permission to access it
(D-032), ensuring restricted pages do not exist in memory for unauthorized roles.
"""

from typing import Callable, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import (
    BoxCode,
    InspectionRecord,
    InspectionSession,
    Order,
)
from agroscan.models.user_models import User
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.components.loading_screen import LoadingScreen
from agroscan.ui.navigation import (
    PAGE_SPECS,
    NavSection,
    PageKey,
    can_access,
    get_spec,
    sidebar_specs,
)
from agroscan.ui.pages.assessment_result_page import AssessmentResultPage
from agroscan.ui.pages.box_intake_page import BoxIntakePage
from agroscan.ui.pages.dashboard_page import DashboardPage
from agroscan.ui.pages.live_inspection_page import LiveInspectionPage
from agroscan.ui.pages.placeholder_page import PlaceholderPage
from agroscan.ui.pages.review_queue_page import ReviewQueuePage
from agroscan.ui.pages.settings_page import SettingsPage


_PLACEHOLDERS: dict[PageKey, tuple[str, list[str]]] = {
    PageKey.INSPECTION_HISTORY: (
        "Search past inspection sessions by box code, date, and product.",
        [
            "Search and filter by box code, order, product, status, and date range",
            "Session detail view with evidence images and reviewer decision",
            "Full re-inspection history per box",
        ],
    ),
    PageKey.REPORTS: (
        "Inspection statistics, order-level summaries, and exports.",
        [
            "Order-level aggregation, e.g. \"8/10 boxes passed, 1 pending, 1 failed\"",
            "Daily outcome charts and quality ratios",
            "PDF and Excel export using unified filter criteria",
        ],
    ),
    PageKey.DATA_IMPORT: (
        "Import orders, products, inspection criteria, and users.",
        [
            "Excel (.xlsx) and CSV import with downloadable templates",
            "Row-level validation report prior to database commit",
            "PDF data extraction via the Qwen-VL service",
        ],
    ),
    PageKey.CATALOG: (
        "Manage products, specialized YOLO models, and defect criteria.",
        [
            "Product catalog mapped to dedicated YOLO model files",
            "Configurable defect thresholds and critical defect classes per product",
        ],
    ),
    PageKey.USERS: (
        "Manage user accounts and role assignments.",
        [
            "Admin, Inspector, and Reviewer account management",
            "Account activation and status control",
        ],
    ),
}


class MainWindow(QMainWindow):
    """Primary workstation window displayed after authentication."""

    logout_requested = Signal()

    _NOTICE_MS = 4500
    _LOADING_TRANSITION_MS = 280
    _LOADING_ESTIMATE_MS = 2000

    def __init__(
        self,
        user: User,
        auth_service: MockAuthService,
        repo: MockRepository,
        settings: Optional[AppSettings] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._user = user
        self._auth = auth_service
        self._repo = repo
        self._settings = settings or AppSettings()

        self.setWindowTitle(f"AgroScan — {user.display_name} ({user.role.value})")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        self._pages: dict[PageKey, QWidget] = {}
        self._nav_items: dict[PageKey, QListWidgetItem] = {}
        self._current_key: Optional[PageKey] = None
        self._pending_key: Optional[PageKey] = None
        self._is_loading = False
        self._assessment_record: Optional[InspectionRecord] = None

        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)

        self._init_ui()
        self._connect_signals()
        self.navigate_to(PageKey.DASHBOARD)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def user(self) -> User:
        return self._user

    @property
    def current_page(self) -> Optional[PageKey]:
        return self._current_key

    def page(self, key: PageKey) -> Optional[QWidget]:
        """Return the widget for ``key``, or ``None`` if inaccessible to the current role."""
        return self._pages.get(key)

    def navigate_to(self, key: PageKey) -> bool:
        """Switch to ``key`` if permitted for the signed-in role."""
        if key not in self._pages:
            return False

        if self._is_loading:
            if key == self._pending_key:
                return True
            self._cancel_loading()

        if key == self._current_key and self.page_stack.currentWidget() is self._pages[key]:
            self._sync_sidebar(key)
            return True

        if get_spec(key).is_heavy:
            self._start_loading(key)
        else:
            self._show_page(key)
        return True

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content_area(), 1)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(12)

        brand = QLabel("AgroScan")
        brand.setObjectName("Brand")
        brand_subtitle = QLabel("INSPECTION WORKSTATION")
        brand_subtitle.setObjectName("BrandSubtitle")
        layout.addWidget(brand)
        layout.addWidget(brand_subtitle)
        layout.addSpacing(20)

        self.navigation = QListWidget()
        self.navigation.setObjectName("Navigation")
        self.navigation.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.navigation.setCursor(Qt.CursorShape.PointingHandCursor)
        self.navigation.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._populate_sidebar()
        layout.addWidget(self.navigation, 1)

        demo_badge = QLabel("DEMO MODE")
        demo_badge.setObjectName("DemoBadge")
        demo_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(demo_badge)
        return sidebar

    def _populate_sidebar(self) -> None:
        """Build sidebar items from ``sidebar_specs(role)``; unauthorized items are omitted (D-032)."""
        self.navigation.clear()
        self._nav_items.clear()
        current_section: Optional[NavSection] = None
        for spec in sidebar_specs(self._user.role):
            if spec.section != current_section:
                current_section = spec.section
                header = QListWidgetItem(current_section.value)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setSizeHint(QSize(0, 34))
                self.navigation.addItem(header)
            item = QListWidgetItem(spec.label)
            item.setData(Qt.ItemDataRole.UserRole, spec.key)
            item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.navigation.addItem(item)
            self._nav_items[spec.key] = item

    def _build_content_area(self) -> QWidget:
        content = QWidget()
        content.setObjectName("Content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_page_stack(), 1)
        return content

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(72)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(32, 0, 32, 0)
        layout.setSpacing(12)

        self.breadcrumb = QLabel("AgroScan")
        self.breadcrumb.setObjectName("Breadcrumb")
        layout.addWidget(self.breadcrumb)
        layout.addStretch()

        self.notice_label = QLabel("")
        self.notice_label.setObjectName("HeaderNotice")
        self.notice_label.setVisible(False)
        layout.addWidget(self.notice_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addSpacing(8)

        self.user_label = QLabel(self._user.display_name)
        self.user_label.setObjectName("UserLabel")
        self.user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.user_label.setToolTip(f"Signed in as {self._user.username}")

        self.role_badge = QLabel(self._user.role.value.upper())
        self.role_badge.setObjectName("RoleBadge")
        self.role_badge.setProperty("role", self._user.role.name.lower())
        self.role_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_logout = QPushButton("Logout")
        self.btn_logout.setObjectName("LogoutButton")
        self.btn_logout.setFixedHeight(36)
        self.btn_logout.setCursor(Qt.CursorShape.PointingHandCursor)

        for widget in (self.user_label, self.role_badge, self.btn_logout):
            layout.addWidget(widget, alignment=Qt.AlignmentFlag.AlignVCenter)
        return header

    def _build_page_stack(self) -> QStackedWidget:
        self.page_stack = QStackedWidget()
        self.loading_screen = LoadingScreen()
        self.page_stack.addWidget(self.loading_screen)

        for spec in PAGE_SPECS:
            if not can_access(self._user.role, spec.key):
                continue
            page = self._create_page(spec.key)
            self._pages[spec.key] = page
            self.page_stack.addWidget(page)
        return self.page_stack

    def _create_page(self, key: PageKey) -> QWidget:
        if key == PageKey.DASHBOARD:
            return DashboardPage(self._repo)
        if key == PageKey.BOX_INTAKE:
            return BoxIntakePage(self._repo)
        if key == PageKey.LIVE_INSPECTION:
            return LiveInspectionPage(self._settings)
        if key == PageKey.ASSESSMENT_RESULT:
            return AssessmentResultPage()
        if key == PageKey.REVIEW_QUEUE:
            return ReviewQueuePage(self._repo, self._user)
        if key == PageKey.SETTINGS:
            return SettingsPage(self._settings)
        description, planned = _PLACEHOLDERS.get(key, ("This module is not built yet.", []))
        return PlaceholderPage(get_spec(key).label, description, planned)

    # Typed accessors for workflow pages (None when the role lacks access)

    @property
    def box_intake_page(self) -> Optional[BoxIntakePage]:
        return self._pages.get(PageKey.BOX_INTAKE)  # type: ignore[return-value]

    @property
    def live_inspection_page(self) -> Optional[LiveInspectionPage]:
        return self._pages.get(PageKey.LIVE_INSPECTION)  # type: ignore[return-value]

    @property
    def assessment_result_page(self) -> Optional[AssessmentResultPage]:
        return self._pages.get(PageKey.ASSESSMENT_RESULT)  # type: ignore[return-value]

    @property
    def review_queue_page(self) -> Optional[ReviewQueuePage]:
        return self._pages.get(PageKey.REVIEW_QUEUE)  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.navigation.itemClicked.connect(self._on_nav_item_clicked)
        self.btn_logout.clicked.connect(self._on_logout_clicked)
        self._notice_timer.timeout.connect(lambda: self.notice_label.setVisible(False))

        review_queue = self.review_queue_page
        if review_queue is not None:
            review_queue.review_submitted.connect(self._on_review_submitted)

        intake = self.box_intake_page
        live = self.live_inspection_page
        result = self.assessment_result_page
        if intake is None or live is None or result is None:
            return

        intake.session_requested.connect(self._on_session_requested)
        intake.resume_requested.connect(lambda: self.navigate_to(PageKey.LIVE_INSPECTION))

        live.inspection_finished.connect(self._on_inspection_finished)
        live.next_box_scanned.connect(lambda text: self._on_next_box(text, live.show_error))
        live.session_discarded.connect(self._on_session_discarded)

        result.submit_requested.connect(self._on_submit_requested)
        result.back_requested.connect(self._on_back_to_live)
        result.next_box_scanned.connect(lambda text: self._on_next_box(text, result.show_error))

    def _on_nav_item_clicked(self, item: QListWidgetItem) -> None:
        key = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(key, PageKey):
            self.navigate_to(key)

    def _on_review_submitted(self, record: InspectionRecord) -> None:
        if record.review is not None:
            self._show_notice(
                f"✔  Box {record.session.box_code} marked as {record.review.decision.value}"
            )

    # ------------------------------------------------------------------
    # Inspection workflow: Box Intake -> Live Inspection -> Assessment Result
    # ------------------------------------------------------------------

    def _on_session_requested(self, box_code: BoxCode, order: Order, notes: str) -> None:
        def warn(message: str) -> None:
            QMessageBox.warning(self, "Session In Progress", message)

        if self._release_active_session(box_code, warn):
            self._open_session(box_code, order, notes)

    def _on_next_box(self, text: str, on_error: Callable[[str], None]) -> None:
        """Handle continuous scanning (D-020): submit current session and open the next box."""
        try:
            box_code, order = self._repo.resolve_box(text)
        except ValueError as exc:
            on_error(str(exc))
            return
        if self._release_active_session(box_code, on_error):
            self._open_session(box_code, order, "")

    def _release_active_session(
        self, next_box: BoxCode, on_error: Callable[[str], None]
    ) -> bool:
        """Ensure the current session can be closed before opening ``next_box``."""
        live = self.live_inspection_page
        current = live.session if live else None
        if current is None:
            return True
        if current.box_code == next_box:
            on_error(
                f"Box {next_box} is already open in session {current.session_id}. "
                "Only one session per box can be open at a time."
            )
            return False

        record = self._assessment_record
        if record is None or record.session is not current:
            record = live.finalize()
        if record is None:
            on_error(
                f"Box {current.box_code} has no evidence image yet. Capture evidence "
                "or discard that session before opening another box."
            )
            return False
        self._submit_record(record)
        return True

    def _open_session(self, box_code: BoxCode, order: Order, notes: str) -> None:
        station = self._settings.load().station_name
        session = self._repo.create_session(box_code, order, self._user.username, station)
        session.notes = notes
        self._assessment_record = None
        self.live_inspection_page.start_session(session)
        self.box_intake_page.reset_form()
        self.box_intake_page.set_active_session(session)
        self.navigate_to(PageKey.LIVE_INSPECTION)

    def _submit_record(self, record: InspectionRecord) -> None:
        """Persist AI recommendation and transition the session to Pending Review (D-020)."""
        self._repo.submit_for_review(record)
        self._assessment_record = None
        self.live_inspection_page.clear_session()
        self.box_intake_page.set_active_session(None)
        self._show_notice(f"✔  Box {record.session.box_code} submitted for review")

    def _on_inspection_finished(self, record: InspectionRecord) -> None:
        self._assessment_record = record
        self.assessment_result_page.show_record(
            record, self.live_inspection_page.captured_images
        )
        self.navigate_to(PageKey.ASSESSMENT_RESULT)

    def _on_back_to_live(self) -> None:
        # Recompute assessment on next Finish in case new captures were taken
        self._assessment_record = None
        self.navigate_to(PageKey.LIVE_INSPECTION)

    def _on_submit_requested(self, record: InspectionRecord) -> None:
        self._submit_record(record)
        self.box_intake_page.reset_form()
        self.navigate_to(PageKey.BOX_INTAKE)

    def _on_session_discarded(self) -> None:
        self._assessment_record = None
        self.box_intake_page.set_active_session(None)
        self.navigate_to(PageKey.BOX_INTAKE)

    def _active_session(self) -> Optional[InspectionSession]:
        live = self.live_inspection_page
        return live.session if live else None

    # ------------------------------------------------------------------
    # Page switching
    # ------------------------------------------------------------------

    def _start_loading(self, key: PageKey) -> None:
        label = get_spec(key).label
        self._pending_key = key
        self._is_loading = True
        self.breadcrumb.setText(f"AgroScan  /  Loading {label}…")
        self._sync_sidebar(key)
        self.page_stack.setCurrentWidget(self.loading_screen)
        self.loading_screen.start(
            page_name=label,
            on_complete=lambda: self._on_loading_complete(key),
            estimated_ms=self._LOADING_ESTIMATE_MS,
            transition_ms=self._LOADING_TRANSITION_MS,
        )

    def _on_loading_complete(self, key: PageKey) -> None:
        if not self._is_loading or key != self._pending_key:
            return
        self._is_loading = False
        self._pending_key = None
        self._show_page(key)

    def _cancel_loading(self) -> None:
        self.loading_screen.stop()
        self._is_loading = False
        self._pending_key = None
        if self._current_key is not None:
            self.page_stack.setCurrentWidget(self._pages[self._current_key])
            self._update_breadcrumb(self._current_key)
            self._sync_sidebar(self._current_key)

    def _show_page(self, key: PageKey) -> None:
        if key == PageKey.BOX_INTAKE and self.box_intake_page is not None:
            self.box_intake_page.set_active_session(self._active_session())
        self._current_key = key
        self._update_breadcrumb(key)
        self._sync_sidebar(key)
        self._fade_to(self._pages[key])

    def _update_breadcrumb(self, key: PageKey) -> None:
        spec = get_spec(key)
        parts = ["AgroScan"]
        if spec.parent is not None:
            parts.append(get_spec(spec.parent).label)
        parts.append(spec.label)
        session = self._active_session()
        text = "  /  ".join(parts)
        if spec.parent is not None and session is not None:
            text += f"   ·   {session.session_id}"
        self.breadcrumb.setText(text)

    def _sync_sidebar(self, key: PageKey) -> None:
        """Highlight the corresponding sidebar item (or parent item for workflow steps)."""
        spec = get_spec(key)
        item = self._nav_items.get(spec.parent or key)
        self.navigation.blockSignals(True)
        if item is not None:
            self.navigation.setCurrentItem(item)
        else:
            self.navigation.clearSelection()
        self.navigation.blockSignals(False)

    def _fade_to(self, target: QWidget) -> None:
        self.page_stack.setCurrentWidget(target)
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(240)
        anim.setStartValue(0.15)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: target.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._page_transition_anim = anim

    def _show_notice(self, text: str) -> None:
        self.notice_label.setText(text)
        self.notice_label.setVisible(True)
        self._notice_timer.start(self._NOTICE_MS)

    # ------------------------------------------------------------------
    # Logout & shutdown
    # ------------------------------------------------------------------

    def _confirm_discard_active_session(self, action: str) -> bool:
        session = self._active_session()
        if session is None:
            return True
        answer = QMessageBox.question(
            self, action,
            f"Session {session.session_id} for box {session.box_code} has not been "
            f"submitted and will be discarded. {action} anyway?",
        )
        return answer == QMessageBox.StandardButton.Yes

    def shutdown(self) -> None:
        """Release camera, loading animation, and active timers prior to teardown."""
        self.loading_screen.stop()
        self._notice_timer.stop()
        if self.live_inspection_page is not None:
            self.live_inspection_page.clear_session()

    def _on_logout_clicked(self) -> None:
        if not self._confirm_discard_active_session("Log Out"):
            return
        self.shutdown()
        self.logout_requested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        if not self._confirm_discard_active_session("Exit"):
            event.ignore()
            return
        self.shutdown()
        super().closeEvent(event)
