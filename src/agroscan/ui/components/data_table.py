"""Read-only table with an optional payload object per row."""

from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class DataTable(QTableWidget):
    """Bảng chỉ đọc, chọn theo dòng. Mỗi dòng có thể gắn một object payload."""

    def __init__(self, headers: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(0, len(headers), parent)
        self.setObjectName("DataTable")
        self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(40)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._payloads: list[Any] = []

    def set_rows(self, rows: list[list[str]], payloads: Optional[list[Any]] = None) -> None:
        self.setRowCount(0)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                self.setItem(r, c, QTableWidgetItem(value))
        self._payloads = list(payloads) if payloads is not None else [None] * len(rows)

    def payload_at(self, row: int) -> Any:
        return self._payloads[row] if 0 <= row < len(self._payloads) else None

    def selected_payload(self) -> Any:
        return self.payload_at(self.currentRow())
