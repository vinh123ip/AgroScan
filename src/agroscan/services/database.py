"""PostgreSQL connection helper for AgroScan.

Reads connection parameters from ``AppSettings`` (``ConnectionSettings``)
and overlays environment variables / local ``.env`` values (standard library
only, no ``python-dotenv`` dependency required). Passwords never live in code.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extensions import connection as PgConnection

from agroscan.services.app_settings import AppSettings, ConnectionSettings

_DEFAULT_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


@dataclass(frozen=True)
class DbConfig:
    """Resolved PostgreSQL connection configuration."""

    host: str
    port: int
    dbname: str
    user: str
    password: str
    connect_timeout_s: int = 5

    def to_psycopg2_kwargs(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
            "connect_timeout": self.connect_timeout_s,
        }


def parse_env_file(env_path: Optional[Path] = None) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` ``.env`` file without mutating ``os.environ``."""
    target = env_path or _DEFAULT_ENV_PATH
    if not target.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        if key:
            values[key] = val
    return values


def resolve_db_config(
    settings: Optional[AppSettings | ConnectionSettings] = None,
    env_path: Optional[Path] = None,
) -> DbConfig:
    """Resolve DB config from ``ConnectionSettings``, ``.env``, and ``os.environ``."""
    if isinstance(settings, ConnectionSettings):
        conn_settings = settings
    elif isinstance(settings, AppSettings):
        conn_settings = settings.load()
    else:
        conn_settings = AppSettings().load()

    file_env = parse_env_file(env_path)

    def _get(env_key: str, fallback: str) -> str:
        if env_key in os.environ and os.environ[env_key].strip():
            return os.environ[env_key].strip()
        if env_key in file_env and file_env[env_key].strip():
            return file_env[env_key].strip()
        return fallback

    host = _get("AGROSCAN_DB_HOST", conn_settings.db_host)
    port_str = _get("AGROSCAN_DB_PORT", str(conn_settings.db_port))
    try:
        port = int(port_str)
    except ValueError:
        port = conn_settings.db_port
    dbname = _get("AGROSCAN_DB_NAME", conn_settings.db_name)
    user = _get("AGROSCAN_DB_USER", conn_settings.db_user)
    password = _get("AGROSCAN_DB_PASSWORD", "")

    return DbConfig(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password,
    )


def get_connection(config: DbConfig) -> PgConnection:
    """Open a new psycopg2 connection using ``config``."""
    return psycopg2.connect(**config.to_psycopg2_kwargs())


def test_connection(config: DbConfig) -> tuple[bool, str]:
    """Verify PostgreSQL connectivity and authentication."""
    try:
        with get_connection(config) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, f"Connected to {config.dbname}@{config.host}:{config.port} as {config.user}."
    except Exception as exc:
        return False, f"PostgreSQL connection failed: {exc}"

