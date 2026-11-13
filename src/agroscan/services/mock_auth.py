"""Mock authentication and bearer session/token service (D-027).

TEMPORARY: demo passwords live here only until user accounts move to
PostgreSQL with hashed passwords. Do not add real credentials to this file.
"""

import base64
import copy
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from agroscan.models.user_models import AuthSession, Role, User

DEFAULT_SESSION_TTL_SECONDS = 8 * 3600  # 8-hour workstation shift

_DEMO_ACCOUNTS: list[tuple[User, str]] = [
    (User("admin",     "System Admin",          Role.ADMIN),     "admin123"),
    (User("inspector", "Station Inspector",     Role.INSPECTOR), "inspector123"),
    (User("reviewer",  "Quality Reviewer",      Role.REVIEWER),  "reviewer123"),
]

_EXTRA_ACCOUNTS: list[tuple[User, str]] = [
    (User("inspector2", "Night Shift Inspector", Role.INSPECTOR, is_active=False), "inspector123"),
]


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode((segment + padding).encode("ascii"))


class MockAuthService:
    """In-memory authentication and HMAC-signed session token manager."""

    def __init__(self, session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> None:
        self._default_ttl = max(1, session_ttl_seconds)
        self._signing_key = secrets.token_bytes(32)
        self._session_counter = 0
        self._accounts: dict[str, tuple[User, str]] = {
            user.username: (copy.deepcopy(user), secret)
            for user, secret in (_DEMO_ACCOUNTS + _EXTRA_ACCOUNTS)
        }
        self._sessions_by_token: dict[str, AuthSession] = {}
        self._revoked_tokens: set[str] = set()
        self._current_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Account directory & credential check
    # ------------------------------------------------------------------

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Return ``User`` if credentials match an active account, otherwise ``None``."""
        user, _ = self.authenticate_with_reason(username, password)
        return user

    def authenticate_with_reason(
        self, username: str, password: str
    ) -> tuple[Optional[User], Optional[str]]:
        """Authenticate credentials and return ``(user, error_message)``."""
        name = username.strip().lower()
        if not name or not password:
            return None, "Enter username and password."
        entry = self._accounts.get(name)
        if entry is None:
            return None, "Incorrect username or password."
        account, secret = entry
        if not hmac.compare_digest(secret, password):
            return None, "Incorrect username or password."
        if not account.is_active:
            return None, f"Account '{account.username}' is disabled. Contact an administrator."
        return copy.deepcopy(account), None

    def set_user_active(self, username: str, is_active: bool) -> None:
        """Enable or disable an account; disabling immediately revokes active tokens."""
        name = username.strip().lower()
        entry = self._accounts.get(name)
        if entry is None:
            raise ValueError(f"User '{username}' was not found.")
        user, secret = entry
        user.is_active = is_active
        self._accounts[name] = (user, secret)
        if not is_active:
            for token, sess in list(self._sessions_by_token.items()):
                if sess.user.username == name:
                    self.logout(token)

    # ------------------------------------------------------------------
    # Session & bearer token lifecycle
    # ------------------------------------------------------------------

    @property
    def current_session(self) -> Optional[AuthSession]:
        """Return the active non-expired ``AuthSession``, or ``None``."""
        if self._current_token is None:
            return None
        return self.validate_token(self._current_token)

    def login(
        self,
        username: str,
        password: str,
        station_name: str = "STATION-01",
        ttl_seconds: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> Optional[AuthSession]:
        """Authenticate and issue a new ``AuthSession`` (revoking any previous session)."""
        user, _ = self.authenticate_with_reason(username, password)
        if user is None:
            return None
        return self.issue_session(user, station_name=station_name, ttl_seconds=ttl_seconds, now=now)

    def issue_session(
        self,
        user: User,
        station_name: str = "STATION-01",
        ttl_seconds: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> AuthSession:
        """Create and activate a signed bearer token session for ``user``."""
        if self._current_token is not None:
            self.logout(self._current_token)

        issued = now or datetime.now()
        ttl = self._default_ttl if ttl_seconds is None else max(1, ttl_seconds)
        expires = issued + timedelta(seconds=ttl)
        self._session_counter += 1
        session_id = f"SES-{issued:%Y%m%d}-{self._session_counter:04d}"
        station = station_name.strip() or "STATION-01"

        claims = {
            "sid": session_id,
            "sub": user.username,
            "role": user.role.value,
            "stn": station,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": secrets.token_hex(8),
        }
        payload_b64 = _b64url_encode(
            json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        sig = hmac.new(
            self._signing_key, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        token = f"ags.{payload_b64}.{_b64url_encode(sig)}"

        session = AuthSession(
            session_id=session_id,
            token=token,
            user=copy.deepcopy(user),
            station_name=station,
            issued_at=issued,
            expires_at=expires,
        )
        self._sessions_by_token[token] = session
        self._current_token = token
        return session

    def validate_token(
        self, token: str, now: Optional[datetime] = None
    ) -> Optional[AuthSession]:
        """Verify token signature, revocation state, account status, and expiration."""
        if not token or token in self._revoked_tokens:
            return None
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "ags":
            return None
        _, payload_b64, sig_b64 = parts
        try:
            provided_sig = _b64url_decode(sig_b64)
            claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        except Exception:
            return None

        expected_sig = hmac.new(
            self._signing_key, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            return None

        session = self._sessions_by_token.get(token)
        if session is None or session.session_id != claims.get("sid"):
            return None
        if session.is_expired_at(now):
            self.logout(token)
            return None
        entry = self._accounts.get(session.user.username)
        if entry is not None and not entry[0].is_active:
            self.logout(token)
            return None
        return session

    def logout(self, token: Optional[str] = None) -> None:
        """Revoke ``token`` (or the current active session token) immediately."""
        target = token or self._current_token
        if target:
            self._revoked_tokens.add(target)
            self._sessions_by_token.pop(target, None)
            if self._current_token == target:
                self._current_token = None

    @staticmethod
    def demo_accounts() -> list[tuple[User, str]]:
        """Return quick-pick demo accounts shown on ``LoginDialog``."""
        return [(copy.deepcopy(u), p) for u, p in _DEMO_ACCOUNTS]

    @staticmethod
    def default_users() -> list[User]:
        return [copy.deepcopy(user) for user, _ in _DEMO_ACCOUNTS]

