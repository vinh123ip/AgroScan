"""Workstation connection settings (D-028), persisted with QSettings.

Stored as an INI file in the user profile (``%APPDATA%/AgroScan/AgroScan.ini``
on Windows), so changing networks only needs a new IP on the Settings screen.
The database password is intentionally not stored in this phase.
"""

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QSettings

from agroscan.models.user_models import AuthSession


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


@dataclass
class SessionState:
    """Non-sensitive workstation session metadata persisted in QSettings."""

    session_id:        str = ""
    username:          str = ""
    role:              str = ""
    station_name:      str = ""
    issued_at:         str = ""
    expires_at:        str = ""
    masked_token:      str = ""
    remember_username: bool = False
    last_username:     str = ""


def _coerce_bool(raw: object, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(raw, (int, float)):
        return bool(raw)
    return default


class AppSettings:
    """Đọc/ghi ``ConnectionSettings`` qua QSettings."""

    _GROUP = "connection"
    _SESSION_GROUP = "session"

    def __init__(self, store: Union[QSettings, Path, str, None] = None) -> None:
        if isinstance(store, (Path, str)):
            self._store = QSettings(str(store), QSettings.Format.IniFormat)
        elif store is not None:
            self._store = store
        else:
            self._store = QSettings(
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

    def load_session_state(self) -> SessionState:
        """Load persisted session metadata and remembered username preference."""
        defaults = SessionState()
        values: dict[str, object] = {}
        self._store.beginGroup(self._SESSION_GROUP)
        for f in fields(SessionState):
            default = getattr(defaults, f.name)
            raw = self._store.value(f.name, default)
            if isinstance(default, bool):
                values[f.name] = _coerce_bool(raw, default)
            else:
                values[f.name] = str(raw) if raw is not None else default
        self._store.endGroup()
        return SessionState(**values)  # type: ignore[arg-type]

    def save_session_state(
        self,
        session: AuthSession,
        remember_username: Optional[bool] = None,
    ) -> SessionState:
        """Persist non-sensitive metadata for ``session`` (never raw password/secret)."""
        prior = self.load_session_state()
        remember = prior.remember_username if remember_username is None else remember_username
        state = SessionState(
            session_id=session.session_id,
            username=session.user.username,
            role=session.user.role.value,
            station_name=session.station_name,
            issued_at=session.issued_at.isoformat(timespec="seconds"),
            expires_at=session.expires_at.isoformat(timespec="seconds"),
            masked_token=session.masked_token,
            remember_username=remember,
            last_username=session.user.username if remember else "",
        )
        self._write_session_state(state)
        return state

    def clear_session_state(self) -> SessionState:
        """Clear active session fields on logout while preserving remember-username preference."""
        prior = self.load_session_state()
        cleared = SessionState(
            remember_username=prior.remember_username,
            last_username=prior.last_username if prior.remember_username else "",
        )
        self._write_session_state(cleared)
        return cleared

    def _write_session_state(self, state: SessionState) -> None:
        self._store.beginGroup(self._SESSION_GROUP)
        for key, value in asdict(state).items():
            self._store.setValue(key, value)
        self._store.endGroup()
        self._store.sync()
