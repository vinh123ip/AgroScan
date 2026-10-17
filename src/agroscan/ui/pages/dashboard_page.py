"""Dashboard page — overview of inspection activities."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from agroscan.ui.components.stat_card_widget import StatCardWidget


class DashboardPage(QWidget):
    """Trang tổng quan hiển thị thống kê hoạt động kiểm định.

    Hiển thị 4 thẻ số liệu và bảng hoạt động gần đây.
    Dữ liệu hiện tại là demo — sẽ kết nối database thật ở Phase C.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DashboardPage")
        self._init_ui()

    # ------------------------------------------------------------------
    # Private init helpers
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """Khởi tạo toàn bộ layout và widget cho Dashboard."""
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(40)

        root.addLayout(self._build_page_header())
        root.addLayout(self._build_stat_cards())
        root.addStretch()

    def _build_page_header(self) -> QVBoxLayout:
        """Tạo section tiêu đề trang."""
        layout = QVBoxLayout()
        layout.setSpacing(8)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Overview of goods inspection activities")
        subtitle.setObjectName("PageSubtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return layout

    def _build_stat_cards(self) -> QGridLayout:
        """Tạo lưới 4 thẻ thống kê với dữ liệu demo."""
        grid = QGridLayout()
        grid.setSpacing(24)

        _DEMO_STATS: list[tuple[str, str, str]] = [
            ("TOTAL INSPECTIONS", "1,248", "↑ 12% vs last week"),
            ("PENDING REVIEW",    "32",    "Needs attention"),
            ("COMPLETED",         "1,190", "All clear"),
            ("FLAGGED SAMPLES",   "26",    "Action required"),
        ]

        for col, (title, value, note) in enumerate(_DEMO_STATS):
            grid.addWidget(StatCardWidget(title, value, note), 0, col)

        return grid
