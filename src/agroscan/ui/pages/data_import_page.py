"""Data Import page — step 1: import orders from Excel (.xlsx) or CSV (D-029).

Admin only (``navigation.py``). Flow: select a file → it is read and validated
on a worker thread → the preview table highlights invalid rows and lists every
problem → Import is enabled only when the whole file is valid (all-or-nothing).

Persistence goes through ``OrderGateway`` (``services/order_gateway.py``).
Task 3.1.5.7 was approved as UI + validation only: no Order Import / List
Orders API exists yet, so the page is created with ``gateway=None``. In that
state Import stays disabled and Latest Orders shows a "not connected" state;
nothing is simulated.
"""

from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from agroscan.services.mock_repository import MockRepository
from agroscan.services.order_gateway import (
    ImportResult,
    OrderGateway,
    OrderGatewayError,
    OrderListItem,
)
from agroscan.services.order_import import (
    MAX_DATA_ROWS,
    MAX_FILE_BYTES,
    ORDER_COLUMNS,
    FileInfo,
    ImportFileError,
    ImportPreview,
    build_preview,
    inspect_file,
    template_csv_text,
)
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.import_preview_model import ImportPreviewModel
from agroscan.ui.components.page_layout import (
    KeyValueGrid,
    PageHeader,
    ScrollPage,
    SectionCard,
    make_hint,
)
from agroscan.ui.components.status_badge import StatusBadge

_FILE_FILTER = (
    "Order files (*.xlsx *.csv);;Excel workbook (*.xlsx);;CSV file (*.csv);;All files (*)"
)
_MAX_LISTED_ISSUES = 2000
_ORDER_LIST_LIMIT = 50


# ---------------------------------------------------------------------------
# Background work
# ---------------------------------------------------------------------------


class _TaskSignals(QObject):
    succeeded = Signal(int, object)   # token, result
    failed    = Signal(int, str)      # token, message


class _Task(QRunnable):
    """Run a blocking call on the thread pool; report back through queued signals."""

    def __init__(self, token: int, func: Callable[[], Any], signals: _TaskSignals) -> None:
        super().__init__()
        self._token, self._func, self._signals = token, func, signals

    def run(self) -> None:
        try:
            result = self._func()
        except (ImportFileError, OrderGatewayError) as exc:
            self._emit_failure(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 — surface any unexpected error to the UI
            self._emit_failure(f"Unexpected error — {exc}")
            return
        try:
            self._signals.succeeded.emit(self._token, result)
        except RuntimeError:
            pass  # Page was destroyed before the task finished

    def _emit_failure(self, message: str) -> None:
        try:
            self._signals.failed.emit(self._token, message)
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


class DataImportPage(ScrollPage):
    """Order import: file selection, preview + validation, import, latest orders."""

    def __init__(
        self,
        repo: MockRepository,
        gateway: Optional[OrderGateway] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("DataImportPage", parent)
        self._repo = repo                     # Catalog reference for product codes only
        self._gateway = gateway
        self._file: Optional[FileInfo] = None
        self._preview: Optional[ImportPreview] = None
        self._imported = False                # Current preview already imported
        self._busy: Optional[str] = None      # "preview" | "import" while running
        self._orders_loading = False
        self._token = 0
        self._orders_token = 0
        self._last_dir = str(Path.home())

        self._signals = _TaskSignals(self)
        self._signals.succeeded.connect(self._on_task_succeeded)
        self._signals.failed.connect(self._on_task_failed)
        self._order_signals = _TaskSignals(self)
        self._order_signals.succeeded.connect(self._on_orders_loaded)
        self._order_signals.failed.connect(self._on_orders_failed)
        self._handlers: dict[int, tuple[Callable[[Any], None], Callable[[str], None]]] = {}

        self._init_ui()
        self._connect_signals()
        self._apply_preview(None)
        self._set_status("idle", "No file selected")
        self.refresh_orders()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        return self._busy is not None

    @property
    def preview(self) -> Optional[ImportPreview]:
        return self._preview

    @property
    def gateway_connected(self) -> bool:
        return self._gateway is not None

    def select_file(self, path: str) -> bool:
        """Check the file and start reading it. Returns ``False`` if it was rejected."""
        if self.is_busy:
            return False
        self._clear_messages()
        try:
            info = inspect_file(path)
        except ImportFileError as exc:
            self._file = None
            self._show_file_info(None, Path(path).name)
            self._apply_preview(None)
            self._show_error(str(exc))
            self._set_status("error", "File rejected")
            return False
        self._file = info
        self._last_dir = str(info.path.parent)
        self._show_file_info(info)
        self.start_preview()
        return True

    def start_preview(self) -> bool:
        """(Re)read and validate the selected file on a worker thread."""
        if self.is_busy or self._file is None:
            return False
        path = self._file.path
        product_codes = [p.code for p in self._repo.products]   # Read on the UI thread
        existing_orders = list(self._repo.orders)
        self._clear_messages()
        self._start(
            "preview",
            f"Reading and validating {self._file.name}…",
            lambda: build_preview(
                path,
                known_product_codes=product_codes,
                existing_order_codes=existing_orders,
            ),
            self._on_preview_ready,
            self._on_preview_failed,
        )
        return True

    def start_import(self) -> bool:
        """Send every row to the Order Import backend. No-op unless allowed."""
        if self.is_busy or self._gateway is None or self._imported:
            return False
        if self._preview is None or not self._preview.can_import:
            return False
        gateway, rows = self._gateway, list(self._preview.rows)
        self._clear_messages()
        self._start(
            "import",
            f"Importing {len(rows)} order(s)…",
            lambda: gateway.import_orders(rows),
            self._on_import_done,
            self._on_import_failed,
        )
        return True

    def refresh_orders(self) -> bool:
        """Reload Latest Orders from the backend (no-op while not connected)."""
        if self._gateway is None:
            self._show_orders_state(
                "Order service not connected. Imported orders will be listed here once the "
                "List Orders API is available."
            )
            self.orders_status.setText("Not connected")
            self.btn_refresh_orders.setEnabled(False)
            return False
        if self._orders_loading:
            return False
        self._orders_loading = True
        self._orders_token += 1
        token, gateway = self._orders_token, self._gateway
        self.btn_refresh_orders.setEnabled(False)
        self.orders_status.setText("Loading…")
        self.orders_progress.setVisible(True)
        QThreadPool.globalInstance().start(
            _Task(token, lambda: gateway.list_orders(_ORDER_LIST_LIMIT), self._order_signals)
        )
        return True

    def clear(self) -> None:
        if self.is_busy:
            return
        self._file = None
        self._show_file_info(None)
        self._apply_preview(None)
        self._clear_messages()
        self._set_status("idle", "No file selected")

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        self.body.addWidget(PageHeader(
            "Data Import",
            "Import orders from Excel (.xlsx) or CSV. Every row is validated before "
            "anything is sent to the database; the file is imported only when all rows are valid.",
            is_mock=False,
        ))

        self.backend_banner = QLabel(
            "Order Import API is not connected yet. You can select, preview and validate "
            "files now; importing is enabled once the Order Import / List Orders API "
            "(tasks 3.1.5.2 / 3.1.5.6) is available."
        )
        self.backend_banner.setObjectName("WarningNote")
        self.backend_banner.setWordWrap(True)
        self.backend_banner.setVisible(self._gateway is None)
        self.body.addWidget(self.backend_banner)

        self.body.addWidget(self._build_source_card())
        self.body.addLayout(self._build_summary_row())
        self.body.addWidget(self._build_preview_card())
        self.body.addWidget(self._build_issues_card())
        self.body.addLayout(self._build_action_row())
        self.body.addWidget(self._build_orders_card())
        self.body.addStretch()

    def _build_source_card(self) -> SectionCard:
        card = SectionCard("Source File")
        columns = ", ".join(c.key for c in ORDER_COLUMNS)
        card.body.addWidget(make_hint(
            f"Required columns (first row): {columns}. Max {MAX_FILE_BYTES // 1024 // 1024} MB "
            f"and {MAX_DATA_ROWS:,} rows per file. CSV files must be saved as UTF-8."
        ))

        row = QHBoxLayout()
        row.setSpacing(10)
        self.file_field = QLineEdit()
        self.file_field.setObjectName("ReadOnlyField")
        self.file_field.setReadOnly(True)
        self.file_field.setPlaceholderText("No file selected")
        self.file_field.setMinimumHeight(42)
        row.addWidget(self.file_field, 1)

        self.btn_browse = self._button("Browse…", "PrimaryButton")
        self.btn_preview = self._button("Preview", "SecondaryButton")
        self.btn_preview.setToolTip("Read the selected file again and re-run validation.")
        self.btn_clear = self._button("Clear", "SecondaryButton")
        self.btn_template = self._button("Save Template…", "SecondaryButton")
        self.btn_template.setToolTip("Save a CSV template with the required columns.")
        for btn in (self.btn_browse, self.btn_preview, self.btn_clear, self.btn_template):
            row.addWidget(btn)
        card.body.addLayout(row)

        self.file_info = KeyValueGrid(columns=4)
        card.body.addWidget(self.file_info)

        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        self.progress = self._progress_bar()
        self.status_label = QLabel("")
        self.status_label.setObjectName("CheckStatus")
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.progress)
        status_row.addWidget(self.status_label, 1)
        card.body.addLayout(status_row)

        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_label.setVisible(False)
        card.body.addWidget(self.error_label)

        self.success_label = QLabel("")
        self.success_label.setObjectName("ImportSuccessLabel")
        self.success_label.setWordWrap(True)
        self.success_label.setVisible(False)
        card.body.addWidget(self.success_label)
        return card

    def _build_summary_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)
        card, self.total_value = self._metric_card("Total Rows")
        row.addWidget(card, 1)
        card, self.valid_value = self._metric_card("Valid Rows")
        self.valid_value.setProperty("tone", "good")
        row.addWidget(card, 1)
        card, self.invalid_value = self._metric_card("Invalid Rows")
        self.invalid_value.setProperty("tone", "critical")
        row.addWidget(card, 1)

        status_card = QFrame()
        status_card.setObjectName("ImportMetricCard")
        layout = QVBoxLayout(status_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        title = QLabel("VALIDATION STATUS")
        title.setObjectName("ImportMetricTitle")
        self.status_badge = StatusBadge()
        layout.addWidget(title)
        layout.addWidget(self.status_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        row.addWidget(status_card, 2)
        return row

    def _build_preview_card(self) -> SectionCard:
        card = SectionCard("Data Preview")
        self.structure_label = QLabel("")
        self.structure_label.setObjectName("InlineErrorLabel")
        self.structure_label.setWordWrap(True)
        self.structure_label.setVisible(False)
        card.body.addWidget(self.structure_label)

        self.warning_label = QLabel("")
        self.warning_label.setObjectName("WarningNote")
        self.warning_label.setWordWrap(True)
        self.warning_label.setVisible(False)
        card.body.addWidget(self.warning_label)

        self.preview_model = ImportPreviewModel(self)
        self.preview_view = QTableView()
        self.preview_view.setObjectName("DataTable")
        self.preview_view.setModel(self.preview_model)
        self.preview_view.setMinimumHeight(320)
        self.preview_view.setAlternatingRowColors(True)
        self.preview_view.setShowGrid(False)
        self.preview_view.setWordWrap(False)
        self.preview_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.preview_view.verticalHeader().setVisible(False)
        self.preview_view.verticalHeader().setDefaultSectionSize(36)
        header = self.preview_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setDefaultSectionSize(160)
        header.setStretchLastSection(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        card.body.addWidget(self.preview_view)

        self.preview_empty = QLabel("")
        self.preview_empty.setObjectName("ImportEmptyState")
        self.preview_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_empty.setWordWrap(True)
        self.preview_empty.setMinimumHeight(120)
        card.body.addWidget(self.preview_empty)
        return card

    def _build_issues_card(self) -> SectionCard:
        card = SectionCard("Validation Issues")
        self.issues_hint = make_hint("Click an issue to jump to its row in the preview.")
        card.body.addWidget(self.issues_hint)
        self.issues_table = DataTable(["Row", "Column", "Problem"])
        self.issues_table.setMinimumHeight(180)
        header = self.issues_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        card.body.addWidget(self.issues_table)
        self.issues_empty = QLabel("")
        self.issues_empty.setObjectName("ImportEmptyState")
        self.issues_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.issues_empty.setWordWrap(True)
        card.body.addWidget(self.issues_empty)
        return card

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        self.import_hint = QLabel("")
        self.import_hint.setObjectName("HintLabel")
        self.import_hint.setWordWrap(True)
        row.addWidget(self.import_hint, 1)
        self.btn_import = self._button("Import Orders", "PrimaryButton")
        self.btn_import.setMinimumWidth(180)
        self.btn_import.setFixedHeight(44)
        row.addWidget(self.btn_import)
        return row

    def _build_orders_card(self) -> SectionCard:
        card = SectionCard("Latest Orders")
        top = QHBoxLayout()
        self.orders_progress = self._progress_bar()
        self.orders_status = QLabel("")
        self.orders_status.setObjectName("HintLabel")
        top.addWidget(self.orders_progress)
        top.addWidget(self.orders_status, 1)
        self.btn_refresh_orders = self._button("Refresh", "SecondaryButton")
        top.addWidget(self.btn_refresh_orders)
        card.body.addLayout(top)

        self.orders_table = DataTable(
            ["Order Code", "Product", "Supplier", "Boxes", "Expected Qty", "Created"]
        )
        self.orders_table.setMinimumHeight(220)
        card.body.addWidget(self.orders_table)
        self.orders_empty = QLabel("")
        self.orders_empty.setObjectName("ImportEmptyState")
        self.orders_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orders_empty.setWordWrap(True)
        self.orders_empty.setMinimumHeight(100)
        card.body.addWidget(self.orders_empty)
        return card

    @staticmethod
    def _button(text: str, object_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFixedHeight(42)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    @staticmethod
    def _progress_bar() -> QProgressBar:
        bar = QProgressBar()
        bar.setObjectName("LoadingProgressBar")
        bar.setRange(0, 0)               # Indeterminate
        bar.setTextVisible(False)
        bar.setFixedSize(140, 6)
        bar.setVisible(False)
        return bar

    @staticmethod
    def _metric_card(title: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("ImportMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)
        title_label = QLabel(title.upper())
        title_label.setObjectName("ImportMetricTitle")
        value = QLabel("—")
        value.setObjectName("ImportMetricValue")
        layout.addWidget(title_label)
        layout.addWidget(value)
        return card, value

    def _connect_signals(self) -> None:
        self.btn_browse.clicked.connect(self._on_browse)
        self.btn_preview.clicked.connect(self.start_preview)
        self.btn_clear.clicked.connect(self.clear)
        self.btn_template.clicked.connect(self._on_save_template)
        self.btn_import.clicked.connect(self._on_import_clicked)
        self.btn_refresh_orders.clicked.connect(self.refresh_orders)
        self.issues_table.cellClicked.connect(self._on_issue_clicked)

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Order File", self._last_dir, _FILE_FILTER)
        if path:
            self.select_file(path)

    def _on_save_template(self) -> None:
        default = str(Path(self._last_dir) / "agroscan_orders_template.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Save Order Template", default, "CSV file (*.csv)")
        if not path:
            return
        try:
            # UTF-8 with BOM so Excel opens it with the correct encoding
            Path(path).write_text(template_csv_text(), encoding="utf-8-sig", newline="")
        except OSError as exc:
            self._show_error(f"Could not save the template — {exc.strerror or exc}")
            return
        self._show_success(f"Template saved to {path}")

    def _on_import_clicked(self) -> None:
        if self.is_busy or self._gateway is None or self._imported:
            return
        if self._preview is None or not self._preview.can_import:
            return
        answer = QMessageBox.question(
            self, "Import Orders",
            f"Import {self._preview.total_rows} order(s) from {self._preview.file.name}?\n"
            "All rows are imported together; if any row is rejected, nothing is imported.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.start_import()

    def _on_issue_clicked(self, row: int, _column: int) -> None:
        number = self.issues_table.payload_at(row)
        if number is None:
            return
        model_row = self.preview_model.row_for_number(number)
        if model_row >= 0:
            self.preview_view.selectRow(model_row)
            self.preview_view.scrollTo(self.preview_model.index(model_row, 0))

    # ------------------------------------------------------------------
    # Task plumbing
    # ------------------------------------------------------------------

    def _start(
        self,
        kind: str,
        message: str,
        func: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_failure: Callable[[str], None],
    ) -> None:
        self._token += 1
        self._handlers = {self._token: (on_success, on_failure)}
        self._busy = kind
        self._set_status("running", message)
        self._update_controls()
        QThreadPool.globalInstance().start(_Task(self._token, func, self._signals))

    def _finish(self, token: int) -> Optional[tuple[Callable[[Any], None], Callable[[str], None]]]:
        handlers = self._handlers.pop(token, None)
        if handlers is not None:
            self._busy = None
        return handlers

    def _on_task_succeeded(self, token: int, result: object) -> None:
        handlers = self._finish(token)
        if handlers is not None:
            handlers[0](result)
            self._update_controls()

    def _on_task_failed(self, token: int, message: str) -> None:
        handlers = self._finish(token)
        if handlers is not None:
            handlers[1](message)
            self._update_controls()

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def _on_preview_ready(self, preview: ImportPreview) -> None:
        self._apply_preview(preview)
        self._show_file_info(preview.file, rows=preview.total_rows)
        if preview.structure_errors:
            self._set_status("error", "Validation failed: the file structure is invalid.")
        elif preview.total_rows == 0:
            self._set_status("error", "The file has a header row but no data rows.")
        elif preview.invalid_rows:
            self._set_status(
                "error",
                f"Validation failed: {preview.invalid_rows} of {preview.total_rows} row(s) have problems.",
            )
        else:
            self._set_status("ok", f"All {preview.total_rows} row(s) are valid.")

    def _on_preview_failed(self, message: str) -> None:
        self._apply_preview(None)
        self._show_error(message)
        self._set_status("error", "Could not read the file")

    def _on_import_done(self, result: ImportResult) -> None:
        self._imported = True
        count = result.imported_count
        text = result.message or f"Imported {count} order(s) successfully."
        self._set_status("ok", text)
        self._show_success(text)
        self.refresh_orders()

    def _on_import_failed(self, message: str) -> None:
        self._set_status("error", "Import failed — nothing was imported.")
        self._show_error(message)

    def _on_orders_loaded(self, token: int, items: object) -> None:
        if token != self._orders_token:
            return
        self._orders_loading = False
        self.orders_progress.setVisible(False)
        self.btn_refresh_orders.setEnabled(True)
        orders: list[OrderListItem] = list(items or [])  # type: ignore[arg-type]
        if not orders:
            self._show_orders_state("No orders yet. Import a file to create the first orders.")
            self.orders_status.setText("0 orders")
            return
        self.orders_table.set_rows(
            [
                [
                    o.order_code, o.product_code, o.supplier, str(o.total_boxes),
                    f"{o.expected_quantity:,}",
                    o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "—",
                ]
                for o in orders
            ],
            payloads=orders,
        )
        self.orders_table.setVisible(True)
        self.orders_empty.setVisible(False)
        self.orders_status.setText(f"Showing latest {len(orders)} order(s)")

    def _on_orders_failed(self, token: int, message: str) -> None:
        if token != self._orders_token:
            return
        self._orders_loading = False
        self.orders_progress.setVisible(False)
        self.btn_refresh_orders.setEnabled(True)
        self._show_orders_state(f"Could not load orders — {message}")
        self.orders_status.setText("Error")

    # ------------------------------------------------------------------
    # View state
    # ------------------------------------------------------------------

    def _apply_preview(self, preview: Optional[ImportPreview]) -> None:
        self._preview = preview
        self._imported = False
        self.preview_model.set_preview(preview)

        has_rows = preview is not None and preview.total_rows > 0
        self.preview_view.setVisible(has_rows)
        self.preview_empty.setVisible(not has_rows)
        if preview is None:
            self.preview_empty.setText("Select an Excel or CSV file to preview its rows here.")
        elif not has_rows:
            self.preview_empty.setText("The file has a header row but no data rows.")

        self.structure_label.setVisible(bool(preview and preview.structure_errors))
        self.structure_label.setText("\n".join(preview.structure_errors) if preview else "")
        self.warning_label.setVisible(bool(preview and preview.warnings))
        self.warning_label.setText("\n".join(preview.warnings) if preview else "")

        self.total_value.setText(str(preview.total_rows) if preview else "—")
        self.valid_value.setText(str(preview.valid_rows) if preview else "—")
        self.invalid_value.setText(str(preview.invalid_rows) if preview else "—")
        if preview is None:
            self.status_badge.set_tone("neutral", "No file")
        elif preview.can_import:
            self.status_badge.set_tone("good", preview.status_text)
        elif preview.total_rows == 0 and not preview.structure_errors:
            self.status_badge.set_tone("warning", preview.status_text)
        else:
            self.status_badge.set_tone("critical", preview.status_text)

        issues = preview.issues if preview else []
        shown = issues[:_MAX_LISTED_ISSUES]
        self.issues_table.set_rows(
            [[str(i.row_number), i.column_label, i.message] for i in shown],
            payloads=[i.row_number for i in shown],
        )
        self.issues_table.setVisible(bool(issues))
        self.issues_hint.setVisible(bool(issues))
        self.issues_empty.setVisible(not issues)
        if preview is None:
            self.issues_empty.setText("Validation results appear here after a file is read.")
        elif preview.structure_errors and not issues:
            self.issues_empty.setText("Fix the file structure problems shown above first.")
        elif not issues:
            self.issues_empty.setText("✔  No row-level issues found.")
        if len(issues) > len(shown):
            self.issues_hint.setText(
                f"Showing the first {len(shown):,} of {len(issues):,} issues. "
                "Click an issue to jump to its row in the preview."
            )
        else:
            self.issues_hint.setText("Click an issue to jump to its row in the preview.")
        self._update_controls()

    def _update_controls(self) -> None:
        busy = self.is_busy
        has_file = self._file is not None
        self.btn_browse.setEnabled(not busy)
        self.btn_preview.setEnabled(not busy and has_file)
        self.btn_clear.setEnabled(not busy and (has_file or self._preview is not None))
        self.btn_template.setEnabled(not busy)
        self.progress.setVisible(busy)

        preview = self._preview
        can_import = (
            not busy and not self._imported and self._gateway is not None
            and preview is not None and preview.can_import
        )
        self.btn_import.setEnabled(can_import)
        if self._busy == "import":
            self.btn_import.setText("Importing…")
        elif self._imported:
            self.btn_import.setText("Imported")
        elif preview is not None and preview.total_rows:
            self.btn_import.setText(f"Import {preview.total_rows} Order(s)")
        else:
            self.btn_import.setText("Import Orders")

        if busy:
            hint = "Please wait for the current operation to finish."
        elif preview is None:
            hint = "Select a file to validate it before importing."
        elif self._imported:
            hint = "This file has been imported. Select another file to import more orders."
        elif not preview.can_import:
            hint = "Import is available only when the file structure and every row are valid."
        elif self._gateway is None:
            hint = "The file is valid. Import is disabled until the Order Import API is connected."
        else:
            hint = "The file is valid and ready to import."
        self.import_hint.setText(hint)
        self.btn_import.setToolTip(hint)

    def _show_file_info(self, info: Optional[FileInfo], name: str = "", rows: Optional[int] = None) -> None:
        if info is None:
            self.file_field.setText(name)
            self.file_info.set_items([])
            return
        self.file_field.setText(str(info.path))
        self.file_field.setToolTip(str(info.path))
        self.file_info.set_items([
            ("File", info.name),
            ("Type", info.type_label),
            ("Size", info.size_label),
            ("Modified", info.modified_at.strftime("%Y-%m-%d %H:%M")),
        ] + ([("Data Rows", f"{rows:,}")] if rows is not None else []))

    def _show_orders_state(self, text: str) -> None:
        self.orders_table.set_rows([])
        self.orders_table.setVisible(False)
        self.orders_empty.setText(text)
        self.orders_empty.setVisible(True)

    def _set_status(self, state: str, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _show_error(self, text: str) -> None:
        self.success_label.setVisible(False)
        self.error_label.setText(text)
        self.error_label.setVisible(True)

    def _show_success(self, text: str) -> None:
        self.error_label.setVisible(False)
        self.success_label.setText(f"✔  {text}")
        self.success_label.setVisible(True)

    def _clear_messages(self) -> None:
        self.error_label.setVisible(False)
        self.success_label.setVisible(False)
