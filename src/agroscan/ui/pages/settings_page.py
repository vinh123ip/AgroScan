"""Settings page and connection dialog (D-028).

``ConnectionSettingsForm`` is shared by the admin Settings page and the
"Connection Settings" dialog on the login screen, so a workstation can be
pointed at the server before anyone signs in.
"""

from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from agroscan.services import connection_checker
from agroscan.services.app_settings import AppSettings, ConnectionSettings
from agroscan.services.connection_checker import CheckResult
from agroscan.ui.components.page_layout import (
    PageHeader,
    ScrollPage,
    SectionCard,
    make_hint,
)


class _CheckSignals(QObject):
    finished = Signal(str, bool, str)   # check_key, ok, message


class _CheckTask(QRunnable):
    """Chạy một kiểm tra kết nối trên thread pool để không treo giao diện."""

    def __init__(self, key: str, func: Callable[[], CheckResult], signals: _CheckSignals) -> None:
        super().__init__()
        self._key, self._func, self._signals = key, func, signals

    def run(self) -> None:
        try:
            result = self._func()
        except Exception as exc:  # noqa: BLE001 — báo mọi lỗi bất ngờ lên UI
            result = CheckResult(False, f"Unexpected error — {exc}")
        try:
            self._signals.finished.emit(self._key, result.ok, result.message)
        except RuntimeError:
            pass  # Form đã đóng trước khi kiểm tra xong


class ConnectionSettingsForm(QWidget):
    """Form cấu hình DB / AI / lưu trữ / camera / trạm, có nút Test Connection."""

    saved = Signal()

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._signals = _CheckSignals(self)
        self._signals.finished.connect(self._on_check_finished)
        self._status_labels: dict[str, QLabel] = {}
        self._test_buttons: dict[str, QPushButton] = {}

        self._init_ui()
        self.load()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(20)

        # Database server
        db_card = SectionCard("Database Server (PostgreSQL)")
        db_form = self._make_form()
        self.db_host = self._make_line("e.g.  192.168.1.10")
        self.db_port = QSpinBox()
        self.db_port.setObjectName("FormSpin")
        self.db_port.setRange(1, 65535)
        self.db_name = self._make_line("agroscan")
        self.db_user = self._make_line("agroscan")
        db_form.addRow(self._label("Server IP / Host"), self.db_host)
        db_form.addRow(self._label("Port"), self.db_port)
        db_form.addRow(self._label("Database"), self.db_name)
        db_form.addRow(self._label("User"), self.db_user)
        db_card.body.addLayout(db_form)
        db_card.body.addWidget(make_hint(
            "The test checks that the server port is reachable. "
            "Credentials are verified once the database layer is connected."
        ))
        db_card.body.addLayout(self._make_test_row("db", "Test Connection"))
        layout.addWidget(db_card)

        # AI service
        ai_card = SectionCard("AI Service (Qwen-VL)")
        ai_form = self._make_form()
        self.ai_url = self._make_line("e.g.  http://192.168.1.10:8000")
        self.ai_timeout = QSpinBox()
        self.ai_timeout.setObjectName("FormSpin")
        self.ai_timeout.setRange(1, 120)
        self.ai_timeout.setSuffix("  s")
        ai_form.addRow(self._label("Service URL"), self.ai_url)
        ai_form.addRow(self._label("Timeout"), self.ai_timeout)
        ai_card.body.addLayout(ai_form)
        ai_card.body.addLayout(self._make_test_row("ai", "Test Connection"))
        layout.addWidget(ai_card)

        # Image storage
        storage_card = SectionCard("Image Storage (SMB Share)")
        storage_form = self._make_form()
        path_row = QHBoxLayout()
        self.storage_path = self._make_line(r"e.g.  \\SERVER_IP\AgroScan_Data")
        browse = QPushButton("Browse…")
        browse.setObjectName("SecondaryButton")
        browse.setFixedHeight(42)
        browse.clicked.connect(self._on_browse_storage)
        path_row.addWidget(self.storage_path)
        path_row.addWidget(browse)
        storage_form.addRow(self._label("Folder"), path_row)
        storage_card.body.addLayout(storage_form)
        storage_card.body.addLayout(self._make_test_row("storage", "Test Access"))
        layout.addWidget(storage_card)

        # Workstation
        station_card = SectionCard("Workstation")
        station_form = self._make_form()
        self.station_name = self._make_line("STATION-01")
        self.camera_combo = QComboBox()
        self.camera_combo.setObjectName("FormCombo")
        refresh = QPushButton("Refresh")
        refresh.setObjectName("SecondaryButton")
        refresh.setFixedHeight(42)
        refresh.clicked.connect(lambda: self._fill_cameras(self._current_camera_id()))
        camera_row = QHBoxLayout()
        camera_row.addWidget(self.camera_combo, 1)
        camera_row.addWidget(refresh)
        station_form.addRow(self._label("Station Name"), self.station_name)
        station_form.addRow(self._label("Camera"), camera_row)
        station_card.body.addLayout(station_form)
        layout.addWidget(station_card)

        # Actions
        actions = QHBoxLayout()
        self.saved_label = QLabel("")
        self.saved_label.setObjectName("HintLabel")
        actions.addWidget(self.saved_label)
        actions.addStretch()
        self.btn_test_all = QPushButton("Test All")
        self.btn_test_all.setObjectName("SecondaryButton")
        self.btn_reset = QPushButton("Revert")
        self.btn_reset.setObjectName("SecondaryButton")
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setObjectName("PrimaryButton")
        for btn in (self.btn_test_all, self.btn_reset, self.btn_save):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(120)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(btn)
        layout.addLayout(actions)

        self.btn_test_all.clicked.connect(self._on_test_all)
        self.btn_reset.clicked.connect(self.load)
        self.btn_save.clicked.connect(self._on_save)

    def _make_test_row(self, key: str, text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        button = QPushButton(text)
        button.setObjectName("SecondaryButton")
        button.setFixedHeight(38)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda: self._run_check(key))
        status = QLabel("Not tested")
        status.setObjectName("CheckStatus")
        status.setProperty("state", "idle")
        status.setWordWrap(True)
        row.addWidget(button)
        row.addWidget(status, 1)
        self._test_buttons[key] = button
        self._status_labels[key] = status
        return row

    @staticmethod
    def _make_form() -> QFormLayout:
        form = QFormLayout()
        form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    @staticmethod
    def _make_line(placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("FormField")
        field.setPlaceholderText(placeholder)
        return field

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("FormLabel")
        return label

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        cfg = self._settings.load()
        self.db_host.setText(cfg.db_host)
        self.db_port.setValue(cfg.db_port)
        self.db_name.setText(cfg.db_name)
        self.db_user.setText(cfg.db_user)
        self.ai_url.setText(cfg.ai_url)
        self.ai_timeout.setValue(cfg.ai_timeout_s)
        self.storage_path.setText(cfg.storage_path)
        self.station_name.setText(cfg.station_name)
        self._fill_cameras(cfg.camera_id)
        self.saved_label.setText(f"Stored in {self._settings.file_path}")

    def current_settings(self) -> ConnectionSettings:
        return ConnectionSettings(
            db_host=self.db_host.text().strip(),
            db_port=self.db_port.value(),
            db_name=self.db_name.text().strip(),
            db_user=self.db_user.text().strip(),
            ai_url=self.ai_url.text().strip(),
            ai_timeout_s=self.ai_timeout.value(),
            storage_path=self.storage_path.text().strip(),
            camera_id=self._current_camera_id(),
            station_name=self.station_name.text().strip() or "STATION-01",
        )

    def _on_save(self) -> None:
        self._settings.save(self.current_settings())
        self.saved_label.setText("✔  Settings saved.")
        self.saved.emit()

    def _fill_cameras(self, selected_id: str) -> None:
        self.camera_combo.clear()
        self.camera_combo.addItem("System default camera", userData="")
        for device in QMediaDevices.videoInputs():
            device_id = bytes(device.id()).decode(errors="replace")
            self.camera_combo.addItem(device.description(), userData=device_id)
        index = self.camera_combo.findData(selected_id)
        self.camera_combo.setCurrentIndex(max(index, 0))

    def _current_camera_id(self) -> str:
        return self.camera_combo.currentData() or ""

    def _on_browse_storage(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select image storage folder")
        if folder:
            self.storage_path.setText(folder)

    # ------------------------------------------------------------------
    # Connection checks
    # ------------------------------------------------------------------

    def _on_test_all(self) -> None:
        for key in self._test_buttons:
            self._run_check(key)

    def _run_check(self, key: str) -> None:
        cfg = self.current_settings()
        checks: dict[str, Callable[[], CheckResult]] = {
            "db":      lambda: connection_checker.check_database(cfg.db_host, cfg.db_port),
            "ai":      lambda: connection_checker.check_ai_service(cfg.ai_url, cfg.ai_timeout_s),
            "storage": lambda: connection_checker.check_storage(cfg.storage_path),
        }
        self._test_buttons[key].setEnabled(False)
        self._set_status(key, "running", "Testing…")
        QThreadPool.globalInstance().start(_CheckTask(key, checks[key], self._signals))

    def _on_check_finished(self, key: str, ok: bool, message: str) -> None:
        self._test_buttons[key].setEnabled(True)
        self._set_status(key, "ok" if ok else "error", ("✔  " if ok else "✖  ") + message)

    def _set_status(self, key: str, state: str, text: str) -> None:
        label = self._status_labels[key]
        label.setText(text)
        label.setProperty("state", state)
        label.style().unpolish(label)
        label.style().polish(label)


class SettingsPage(ScrollPage):
    """Trang Settings cho admin (bước 2 — cấu hình hệ thống)."""

    settings_saved = Signal()

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__("SettingsPage", parent)
        self.body.addWidget(PageHeader(
            "Settings",
            "Server addresses, AI service, image storage and camera for this workstation.",
            is_mock=False,
        ))
        self.form = ConnectionSettingsForm(settings)
        self.form.saved.connect(self.settings_saved)
        self.body.addWidget(self.form)
        self.body.addStretch()


class ConnectionSettingsDialog(QDialog):
    """Hộp thoại cấu hình kết nối mở từ màn hình Login."""

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("AppDialog")
        self.setWindowTitle("AgroScan — Connection Settings")
        self.resize(760, 820)

        page = ScrollPage("DialogPage")
        page.body.addWidget(PageHeader(
            "Connection Settings", "Point this workstation at the AgroScan server.", is_mock=False
        ))
        self.form = ConnectionSettingsForm(settings)
        self.form.saved.connect(self.accept)
        page.body.addWidget(self.form)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(page)
