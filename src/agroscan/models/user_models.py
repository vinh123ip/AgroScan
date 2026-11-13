"""User, role, and authenticated session models (D-027)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class Role(Enum):
    """Ba vai trò mặc định của hệ thống."""

    ADMIN     = "Admin"
    INSPECTOR = "Inspector"
    REVIEWER  = "Reviewer"


@dataclass
class User:
    """Tài khoản người dùng. Mật khẩu không bao giờ nằm trong model này."""

    username:     str
    display_name: str
    role:         Role
    is_active:    bool = True


@dataclass(frozen=True)
class AuthSession:
    """Authenticated workstation session carrying a signed bearer token."""

    session_id:   str
    token:        str
    user:         User
    station_name: str
    issued_at:    datetime
    expires_at:   datetime

    @property
    def is_expired(self) -> bool:
        """Return True when the session has reached or passed ``expires_at``."""
        return self.is_expired_at()

    def is_expired_at(self, when: Optional[datetime] = None) -> bool:
        ref = when or datetime.now()
        return ref >= self.expires_at

    def remaining_seconds(self, when: Optional[datetime] = None) -> int:
        ref = when or datetime.now()
        return max(0, int((self.expires_at - ref).total_seconds()))

    @property
    def masked_token(self) -> str:
        """Safe preview of the bearer token for UI tooltips and logs."""
        if len(self.token) <= 14:
            return "***"
        return f"{self.token[:10]}…{self.token[-6:]}"

    @property
    def authorization_header(self) -> dict[str, str]:
        """HTTP header dictionary ready for LAN REST requests."""
        return {"Authorization": f"Bearer {self.token}"}

