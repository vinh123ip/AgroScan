"""Authenticate workstation sessions against v1.2 users."""

from agroscan.services.mock_auth import MockAuthService
from agroscan.services.passwords import verify_password
from agroscan.services.postgres_repository import PostgresRepository


class PostgresAuthService(MockAuthService):
    def __init__(self, repository: PostgresRepository) -> None:
        super().__init__()
        self._accounts.clear()
        self._repository = repository

    def authenticate_with_reason(self, username, password):
        if not username.strip() or not password:
            return None, "Enter username and password."
        try:
            account = self._repository.account(username.strip().lower())
        except ValueError as exc:
            return None, f"Could not read the AgroScan account: {exc}"
        if account is None or not verify_password(password, account[1]):
            return None, "Incorrect username or password."
        if not account[0].is_active:
            return None, "This account is disabled. Contact an administrator."
        return account[0], None

    def validate_token(self, token, now=None):
        session = super().validate_token(token, now)
        if session is None:
            return None
        try:
            account = self._repository.account(session.user.username)
        except ValueError:
            return None
        if account is None or not account[0].is_active or account[0].role != session.user.role:
            self.logout(token)
            return None
        return session

    @staticmethod
    def demo_accounts():
        return []
