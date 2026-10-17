"""Reusable stat card widget for dashboard-style metric displays."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class StatCardWidget(QFrame):
    """Thẻ thống kê hiển thị tiêu đề, giá trị và ghi chú với hiệu ứng đổ bóng.

    Dùng chung ở DashboardPage và bất kỳ trang nào cần hiển thị metric dạng card.
    """

    def __init__(
        self,
        title: str,
        value: str,
        note: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        self._init_shadow()
        self._init_ui(title, value, note)

    # ------------------------------------------------------------------
    # Private init helpers
    # ------------------------------------------------------------------

    def _init_shadow(self) -> None:
        """Thêm hiệu ứng đổ bóng tạo chiều sâu cho thẻ."""
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

    def _init_ui(self, title: str, value: str, note: str) -> None:
        """Khởi tạo layout và các label bên trong thẻ."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        value_label = QLabel(value)
        value_label.setObjectName("CardValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        note_label = QLabel(note)
        note_label.setObjectName("CardNote")
        note_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(note_label)
        layout.addStretch()
