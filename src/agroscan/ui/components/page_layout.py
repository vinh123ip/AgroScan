"""Layout building blocks shared by all pages."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ScrollPage(QWidget):
    """Trang có vùng cuộn; nội dung thêm vào ``self.body``."""

    def __init__(self, object_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("PageScrollArea")

        content = QWidget()
        content.setObjectName("ScrollContent")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(48, 40, 48, 48)
        self.body.setSpacing(24)

        scroll.setWidget(content)
        root.addWidget(scroll)


class PageHeader(QWidget):
    """Tiêu đề + phụ đề trang, kèm nhãn MOCK DATA khi dữ liệu là giả lập."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        is_mock: bool = True,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(16)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        title_row.addWidget(title_label)
        if is_mock:
            badge = QLabel("MOCK DATA")
            badge.setObjectName("MockBadge")
            badge.setToolTip("Data on this page is simulated until the database is connected.")
            title_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        subtitle_label.setWordWrap(True)

        layout.addLayout(title_row)
        layout.addWidget(subtitle_label)


class SectionCard(QFrame):
    """Thẻ nội dung có tiêu đề nhỏ; nội dung thêm vào ``self.body``."""

    def __init__(self, title: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("FormCard")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(28, 24, 28, 24)
        self.body.setSpacing(16)
        if title:
            title_label = QLabel(title.upper())
            title_label.setObjectName("FormSectionTitle")
            self.body.addWidget(title_label)


class KeyValueGrid(QWidget):
    """Lưới nhãn–giá trị chỉ đọc, ví dụ thông tin đơn hàng."""

    def __init__(self, columns: int = 2, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._columns = columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(32)
        self._grid.setVerticalSpacing(14)

    def set_items(self, items: list[tuple[str, str]]) -> None:
        while self._grid.count():
            widget = self._grid.takeAt(0).widget()
            if widget:
                widget.hide()  # Prevent ghost overlap before deletion
                widget.deleteLater()
        for i, (key, value) in enumerate(items):
            row, col = divmod(i, self._columns)
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            key_label = QLabel(key.upper())
            key_label.setObjectName("KeyLabel")
            value_label = QLabel(value or "—")
            value_label.setObjectName("ValueLabel")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            cell_layout.addWidget(key_label)
            cell_layout.addWidget(value_label)
            self._grid.addWidget(cell, row, col)


def make_hint(text: str, object_name: str = "HintLabel") -> QLabel:
    """Nhãn chú thích nhỏ, tự xuống dòng."""
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(True)
    return label
