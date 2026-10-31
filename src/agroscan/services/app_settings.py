"""Workstation connection settings (D-028), persisted with QSettings.

Stored as an INI file in the user profile (``%APPDATA%/AgroScan/AgroScan.ini``
on Windows), so changing networks only needs a new IP on the Settings screen.
The database password is intentionally not stored in this phase.
"""

from dataclasses import asdict, dataclass, fields
from typing import Optional

from PySide6.QtCore import QSettings


@dataclass
class ConnectionSettings:
    db_host:      str = "127.0.0.1"
    db_port:      int = 5432
    db_name:      str = "agroscan"
    db_user:      str = "agroscan"
    ai_url:       str = "http://127.0.0.1:8000"
    ai_timeout_s: int = 10
    storage_path: str = r"\\SERVER_IP\AgroScan_Data"
    camera_id:    str = ""            # Rỗng = camera mặc định của hệ thống
    station_name: str = "STATION-01"


class AppSettings:
    """Đọc/ghi ``ConnectionSettings`` qua QSettings."""

    _GROUP = "connection"

    def __init__(self, store: Optional[QSettings] = None) -> None:
        self._store = store or QSettings(
            QSettings.Format.IniFormat, QSettings.Scope.UserScope, "AgroScan", "AgroScan"
        )

    @property
    def file_path(self) -> str:
        return self._store.fileName()

    def load(self) -> ConnectionSettings:
        defaults = ConnectionSettings()
        values = {}
        self._store.beginGroup(self._GROUP)
        for f in fields(ConnectionSettings):
            default = getattr(defaults, f.name)
            raw = self._store.value(f.name, default)
            try:
                values[f.name] = type(default)(raw)
            except (TypeError, ValueError):
                values[f.name] = default
        self._store.endGroup()
        return ConnectionSettings(**values)

    def save(self, settings: ConnectionSettings) -> None:
        self._store.beginGroup(self._GROUP)
        for key, value in asdict(settings).items():
            self._store.setValue(key, value)
        self._store.endGroup()
        self._store.sync()
