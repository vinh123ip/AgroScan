"""Mock authentication with the three default accounts (D-027).

TEMPORARY: demo passwords live here only until user accounts move to
PostgreSQL with hashed passwords. Do not add real credentials to this file.
"""

from typing import Optional

from agroscan.models.user_models import Role, User


_DEMO_ACCOUNTS: list[tuple[User, str]] = [
    (User("admin",     "System Admin",     Role.ADMIN),     "admin123"),
    (User("inspector", "Station Inspector", Role.INSPECTOR), "inspector123"),
    (User("reviewer",  "Quality Reviewer",  Role.REVIEWER),  "reviewer123"),
]


class MockAuthService:
    """Xác thực bằng danh sách tài khoản demo trong bộ nhớ."""

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Trả về User nếu đúng tên đăng nhập và mật khẩu, ngược lại ``None``."""
        name = username.strip().lower()
        for user, secret in _DEMO_ACCOUNTS:
            if user.username == name and secret == password and user.is_active:
                return user
        return None

    @staticmethod
    def demo_accounts() -> list[tuple[User, str]]:
        """Danh sách tài khoản cho các nút chọn nhanh trên màn hình Login."""
        return list(_DEMO_ACCOUNTS)

    @staticmethod
    def default_users() -> list[User]:
        return [user for user, _ in _DEMO_ACCOUNTS]
