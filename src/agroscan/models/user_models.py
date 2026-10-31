"""User and role models (D-027)."""

from dataclasses import dataclass
from enum import Enum


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
