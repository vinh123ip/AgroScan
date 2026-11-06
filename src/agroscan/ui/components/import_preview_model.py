"""Table model for the Data Import preview: raw file rows with validation highlighting."""

from typing import Any, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QColor, QFont

from agroscan.services.order_import import ImportPreview, RowIssue

# Translucent tints work on both the light and the dark theme.
_INVALID_ROW_BG  = QColor(220, 38, 38, 28)
_INVALID_CELL_BG = QColor(220, 38, 38, 70)
_INVALID_FG      = QColor(185, 28, 28)
_VALID_FG        = QColor(21, 128, 61)


class ImportPreviewModel(QAbstractTableModel):
    """Columns: ``Row`` | every header of the file | ``Status``."""

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._preview: Optional[ImportPreview] = None
        self._cell_issues: list[dict[int, list[RowIssue]]] = []   # per row: column index → issues
        self._row_issues: list[list[RowIssue]] = []               # per row: whole-row issues

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_preview(self, preview: Optional[ImportPreview]) -> None:
        self.beginResetModel()
        self._preview = preview
        self._cell_issues = []
        self._row_issues = []
        if preview is not None:
            index_of = {key: i for i, key in enumerate(preview.column_keys) if key is not None}
            for row in preview.rows:
                cells: dict[int, list[RowIssue]] = {}
                whole: list[RowIssue] = []
                for issue in row.issues:
                    col = index_of.get(issue.column) if issue.column else None
                    if col is None:
                        whole.append(issue)
                    else:
                        cells.setdefault(col, []).append(issue)
                self._cell_issues.append(cells)
                self._row_issues.append(whole)
        self.endResetModel()

    def row_for_number(self, row_number: int) -> int:
        """Model row of a spreadsheet row number, or -1."""
        if self._preview is None:
            return -1
        for i, row in enumerate(self._preview.rows):
            if row.row_number == row_number:
                return i
        return -1

    # ------------------------------------------------------------------
    # QAbstractTableModel
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 — Qt override
        if parent.isValid() or self._preview is None:
            return 0
        return len(self._preview.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802 — Qt override
        if parent.isValid() or self._preview is None:
            return 0
        return len(self._preview.headers) + 2

    def headerData(  # noqa: N802 — Qt override
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if self._preview is None or orientation != Qt.Orientation.Horizontal:
            return None
        last = len(self._preview.headers) + 1
        if role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return "Row"
            if section == last:
                return "Status"
            return self._preview.headers[section - 1] or "(blank)"
        if role == Qt.ItemDataRole.ToolTipRole and 0 < section < last:
            key = self._preview.column_keys[section - 1]
            return f"Mapped to '{key}'" if key else "Not used for orders (ignored)"
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._preview is None:
            return None
        row = self._preview.rows[index.row()]
        col = index.column()
        last = len(self._preview.headers) + 1
        file_col = col - 1
        cell_issues = self._cell_issues[index.row()].get(file_col, []) if 0 < col < last else []

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return str(row.row_number)
            if col == last:
                count = len(row.issues)
                return "✔  Valid" if count == 0 else f"✖  {count} issue{'s' if count > 1 else ''}"
            return row.cells[file_col]

        if role == Qt.ItemDataRole.ToolTipRole:
            if col == last or col == 0:
                issues = row.issues
            else:
                issues = cell_issues + self._row_issues[index.row()]
            return "\n".join(f"• {i.message}" for i in issues) if issues else None

        if role == Qt.ItemDataRole.BackgroundRole and not row.is_valid:
            return _INVALID_CELL_BG if cell_issues else _INVALID_ROW_BG

        if role == Qt.ItemDataRole.ForegroundRole:
            if col == last:
                return _VALID_FG if row.is_valid else _INVALID_FG
            if cell_issues:
                return _INVALID_FG

        if role == Qt.ItemDataRole.FontRole and (col == last or cell_issues):
            font = QFont()
            font.setBold(True)
            return font

        if role == Qt.ItemDataRole.TextAlignmentRole and col == 0:
            return int(Qt.AlignmentFlag.AlignCenter)
        return None
