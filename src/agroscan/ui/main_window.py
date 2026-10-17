"""Main application window for AgroScan.

Manages the top-level layout: Sidebar navigation + Header + paged content area.
Each navigation entry maps 1-to-1 to a QWidget registered in the QStackedWidget.
As Phase 2 pages are implemented, replace the corresponding _PlaceholderPage
with the real page class — no other changes needed.
"""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agroscan.ui.components.loading_screen import LoadingScreen
from agroscan.ui.pages.dashboard_page import DashboardPage


# ---------------------------------------------------------------------------
# Navigation configuration
# ---------------------------------------------------------------------------

# Ordered list of sidebar menu items.
# Index in this list == QStackedWidget index == navigation row.
_NAV_ITEMS: list[str] = [
    "Dashboard",          # 0
    "New Inspection",     # 1
    "Inspection History", # 2
    "Quality Review",     # 3
    "Reports",            # 4
    "Settings",           # 5
]

# Pages that simulate an async loading delay (name → estimated real load time ms).
# Pages NOT listed here are considered lightweight and switch instantly.
_HEAVY_PAGES: dict[str, int] = {
    "New Inspection":     1800,
    "Inspection History": 2200,
    "Quality Review":     2000,
    "Reports":            2400,
}

# QStackedWidget index reserved for the loading screen overlay.
_LOADING_SCREEN_STACK_INDEX: int = len(_NAV_ITEMS)  # 6


# ---------------------------------------------------------------------------
# Internal helper widget
# ---------------------------------------------------------------------------


class _PlaceholderPage(QWidget):
    """Trang tạm thời cho module chưa triển khai.

    Khi một page thật hoàn thành (M2.x), thay thế instance này trong
    ``MainWindow._build_page_stack()`` bằng class tương ứng.
    """

    def __init__(self, page_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("PlaceholderPage")
        self._init_ui(page_name)

    def _init_ui(self, page_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        title = QLabel(page_name)
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("This module will be developed in the upcoming phase.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Cửa sổ chính của ứng dụng AgroScan.

    Layout:
        [Sidebar 260px] | [Header 72px + Content area (QStackedWidget)]
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("AgroScan - Inspection Workstation")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 700)

        # Navigation state
        self._current_nav_index: int  = 0
        self._pending_nav_index: int  = 0
        self._is_loading:        bool = False

        self._init_ui()
        self._connect_signals()
        self._load_stylesheet()

        # Select Dashboard on startup
        self.navigation.setCurrentRow(0)

    # ------------------------------------------------------------------
    # Private init helpers
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Khởi tạo toàn bộ layout root."""
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content_area())

    def _build_sidebar(self) -> QFrame:
        """Tạo sidebar chứa brand identity và navigation menu."""
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(12)

        # Brand
        brand = QLabel("AgroScan")
        brand.setObjectName("Brand")

        brand_subtitle = QLabel("INSPECTION WORKSTATION")
        brand_subtitle.setObjectName("BrandSubtitle")

        layout.addWidget(brand)
        layout.addWidget(brand_subtitle)
        layout.addSpacing(32)

        # Navigation list
        self.navigation = QListWidget()
        self.navigation.setObjectName("Navigation")
        self.navigation.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.navigation.setCursor(Qt.CursorShape.PointingHandCursor)

        for name in _NAV_ITEMS:
            item = QListWidgetItem(name)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            self.navigation.addItem(item)

        layout.addWidget(self.navigation)
        layout.addStretch()

        # Demo badge
        demo_badge = QLabel("DEMO MODE")
        demo_badge.setObjectName("DemoBadge")
        demo_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(demo_badge)

        return sidebar

    def _build_content_area(self) -> QWidget:
        """Tạo vùng nội dung chính gồm Header và QStackedWidget."""
        content = QWidget()
        content.setObjectName("Content")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_page_stack())

        return content

    def _build_header(self) -> QFrame:
        """Tạo header bar chứa breadcrumb và thông tin người dùng."""
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(72)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(32, 0, 32, 0)

        self.breadcrumb = QLabel("AgroScan  /  Dashboard")
        self.breadcrumb.setObjectName("Breadcrumb")

        user_label = QLabel("Inspector User")
        user_label.setObjectName("UserLabel")
        user_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.breadcrumb)
        layout.addStretch()
        layout.addWidget(user_label)

        return header

    def _build_page_stack(self) -> QStackedWidget:
        """Đăng ký tất cả các trang vào QStackedWidget.

        Thứ tự index phải khớp với ``_NAV_ITEMS``.
        Khi một page thật hoàn thành, thay _PlaceholderPage tương ứng.
        """
        self.pages = QStackedWidget()

        # Index 0 — Dashboard (real page)
        self.dashboard_page = DashboardPage()
        self.pages.addWidget(self.dashboard_page)

        # Index 1 — New Inspection (placeholder → M2.1)
        self.new_inspection_page = _PlaceholderPage("New Inspection")
        self.pages.addWidget(self.new_inspection_page)

        # Index 2 — Inspection History (placeholder → M2.6)
        self.inspection_history_page = _PlaceholderPage("Inspection History")
        self.pages.addWidget(self.inspection_history_page)

        # Index 3 — Quality Review (placeholder → future)
        self.quality_review_page = _PlaceholderPage("Quality Review")
        self.pages.addWidget(self.quality_review_page)

        # Index 4 — Reports (placeholder → M2.6 / Phase C)
        self.reports_page = _PlaceholderPage("Reports")
        self.pages.addWidget(self.reports_page)

        # Index 5 — Settings (placeholder → Phase C)
        self.settings_page = _PlaceholderPage("Settings")
        self.pages.addWidget(self.settings_page)

        # Index 6 — Loading screen overlay (not a nav target)
        self.loading_screen = LoadingScreen()
        self.pages.addWidget(self.loading_screen)

        return self.pages

    def _connect_signals(self) -> None:
        """Kết nối tất cả signal/slot cho navigation."""
        self.navigation.currentRowChanged.connect(self._on_nav_row_changed)

    # ------------------------------------------------------------------
    # Navigation handlers
    # ------------------------------------------------------------------

    def _on_nav_row_changed(self, nav_index: int) -> None:
        """Xử lý sự kiện click menu sidebar."""
        if nav_index < 0:
            return

        # Đang xem đúng trang này, không đang loading → bỏ qua
        if not self._is_loading and nav_index == self._current_nav_index:
            return

        # Đang loading tới cùng trang đó → bỏ qua (tránh reset)
        if self._is_loading and nav_index == self._pending_nav_index:
            return

        # Đang loading nhưng người dùng nhấn lại trang đang mở → huỷ loading
        if self._is_loading and nav_index == self._current_nav_index:
            self._cancel_loading()
            return

        # Dừng tiến trình loading cũ nếu còn
        self.loading_screen.stop()

        page_name = self._get_page_name(nav_index)

        if page_name in _HEAVY_PAGES:
            self._start_loading(nav_index, page_name)
        else:
            self._switch_instantly(nav_index, page_name)

    def _switch_instantly(self, nav_index: int, page_name: str) -> None:
        """Chuyển trang nhẹ không cần màn hình loading."""
        self._is_loading             = False
        self._current_nav_index      = nav_index
        self._pending_nav_index      = nav_index

        self._sync_sidebar_selection(nav_index)
        self._update_breadcrumb(page_name)
        self._switch_to_page_with_fade(self._get_page_widget(nav_index))

    def _start_loading(self, nav_index: int, page_name: str) -> None:
        """Bắt đầu sequence loading cho trang nặng."""
        self._pending_nav_index = nav_index
        self._is_loading        = True

        self.breadcrumb.setText(f"AgroScan  /  Loading {page_name}...")
        self.pages.setCurrentIndex(_LOADING_SCREEN_STACK_INDEX)

        estimated_ms = _HEAVY_PAGES.get(page_name, 2000)
        self.loading_screen.start(
            page_name=page_name,
            on_complete=lambda: self._on_loading_complete(nav_index, page_name),
            estimated_ms=estimated_ms,
            transition_ms=280,
        )

    def _on_loading_complete(self, nav_index: int, page_name: str) -> None:
        """Callback sau khi loading screen hoàn tất."""
        # Bỏ qua nếu người dùng đã chuyển sang trang khác trong lúc loading
        if nav_index != self._pending_nav_index:
            return

        self._is_loading        = False
        self._current_nav_index = nav_index

        self._sync_sidebar_selection(nav_index)
        self._update_breadcrumb(page_name)
        self._switch_to_page_with_fade(self._get_page_widget(nav_index))

    def _cancel_loading(self) -> None:
        """Huỷ loading và quay về trang đang mở."""
        self.loading_screen.stop()
        self._is_loading        = False
        self._pending_nav_index = self._current_nav_index

        page_name = self._get_page_name(self._current_nav_index)
        self._update_breadcrumb(page_name)
        self._sync_sidebar_selection(self._current_nav_index)
        self._switch_to_page_with_fade(self._get_page_widget(self._current_nav_index))

    # ------------------------------------------------------------------
    # Page resolution helpers
    # ------------------------------------------------------------------

    def _get_page_name(self, nav_index: int) -> str:
        """Trả về tên trang từ navigation index."""
        if 0 <= nav_index < len(_NAV_ITEMS):
            return _NAV_ITEMS[nav_index]
        return "Unknown"

    def _get_page_widget(self, nav_index: int) -> QWidget:
        """Trả về widget trang từ navigation index.

        Navigation index == QStackedWidget index (1-to-1 mapping).
        """
        self.pages.setCurrentIndex(nav_index)
        return self.pages.currentWidget()

    # ------------------------------------------------------------------
    # UI update helpers
    # ------------------------------------------------------------------

    def _update_breadcrumb(self, page_name: str) -> None:
        self.breadcrumb.setText(f"AgroScan  /  {page_name}")

    def _sync_sidebar_selection(self, nav_index: int) -> None:
        """Cập nhật highlight sidebar mà không trigger currentRowChanged."""
        self.navigation.blockSignals(True)
        self.navigation.setCurrentRow(nav_index)
        self.navigation.blockSignals(False)

    def _switch_to_page_with_fade(self, target_widget: QWidget) -> None:
        """Chuyển sang trang đích với hiệu ứng fade-in mượt mà."""
        self.pages.setCurrentWidget(target_widget)

        effect = QGraphicsOpacityEffect(target_widget)
        target_widget.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(240)
        anim.setStartValue(0.15)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: target_widget.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

        # Giữ reference để tránh GC xoá animation sớm
        self._page_transition_anim = anim

    # ------------------------------------------------------------------
    # Stylesheet
    # ------------------------------------------------------------------

    def _load_stylesheet(self) -> None:
        """Nạp font Inter và QSS dark theme vào ứng dụng."""
        fonts_dir = Path(__file__).parent / "resources" / "fonts"
        if fonts_dir.exists():
            for font_file in fonts_dir.glob("*.ttf"):
                QFontDatabase.addApplicationFont(str(font_file))

        style_path = Path(__file__).parent / "styles" / "dark_theme.qss"
        if style_path.exists():
            self.setStyleSheet(style_path.read_text(encoding="utf-8"))
