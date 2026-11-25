"""Application entry point: LoginDialog <-> MainWindow lifecycle (D-027, D-032)."""

import argparse
from getpass import getpass
import sys
from typing import Optional

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from agroscan.models.user_models import Role
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
from agroscan.services.postgres_auth import PostgresAuthService
from agroscan.services.postgres_repository import PostgresRepository
from agroscan.ui.main_window import MainWindow
from agroscan.ui.pages.login_dialog import LoginDialog
from agroscan.ui.theme import apply_theme


class AppController(QObject):
    """Coordinate sign-in and sign-out transitions across a shared session store.

    ``MockRepository`` is instantiated once and shared across sign-ins so that
    sessions submitted by an Inspector remain visible when a Reviewer signs in
    during the same demo run.
    """

    def __init__(
        self,
        settings: AppSettings,
        auth_service: MockAuthService,
        repo: MockRepository | PostgresRepository,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._auth = auth_service
        self._repo = repo
        self._window: Optional[MainWindow] = None
        self._pending_login_notice: str = ""

    @property
    def window(self) -> Optional[MainWindow]:
        return self._window

    def show_login(self, notice: str = "") -> bool:
        """Open ``LoginDialog`` and launch ``MainWindow`` upon authentication."""
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)

        dialog = LoginDialog(self._auth, self._settings, notice=notice)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted and dialog.user is not None
        user = dialog.user
        session = dialog.session
        dialog.deleteLater()
        if not accepted or user is None:
            return False

        self._window = MainWindow(
            user=user,
            auth_service=self._auth,
            repo=self._repo,
            settings=self._settings,
            auth_session=session,
        )
        self._window.session_expired.connect(self._on_session_expired)
        self._window.logout_requested.connect(self._on_logout_requested)
        self._window.show()
        if app is not None:
            app.setQuitOnLastWindowClosed(True)
        return True

    def _on_session_expired(self, message: str) -> None:
        self._pending_login_notice = message

    def _on_logout_requested(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)

        window, self._window = self._window, None
        if window is not None:
            window.hide()
            window.deleteLater()

        # Defer opening the modal LoginDialog until the current click handler finishes
        QTimer.singleShot(0, self._relogin)

    def _relogin(self) -> None:
        notice, self._pending_login_notice = self._pending_login_notice, ""
        if not self.show_login(notice=notice):
            QApplication.quit()


def create_repository(settings: AppSettings, *, demo: bool = False) -> PostgresRepository | MockRepository:
    if demo:
        return MockRepository()
    repository = PostgresRepository(settings)
    ok, message = repository.ping()
    if not ok:
        raise ValueError(message)
    return repository


def main() -> None:
    parser = argparse.ArgumentParser(description="AgroScan workstation")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Use the in-memory demo database.")
    mode.add_argument("--create-admin", metavar="LOGIN", help="Create a PostgreSQL workstation administrator.")
    args = parser.parse_args()
    settings = AppSettings()
    if args.create_admin:
        try:
            repo = PostgresRepository(settings)
            password = getpass("New workstation password: ")
            if password != getpass("Confirm password: "):
                raise ValueError("Passwords differ.")
            repo.save_user(args.create_admin, args.create_admin, Role.ADMIN,
                           password=password, create_only=True)
        except ValueError as exc:
            parser.exit(1, f"{exc}\n")
        print(f"Created workstation administrator {args.create_admin.strip().lower()}.")
        return

    app = QApplication([sys.argv[0]])
    app.setApplicationName("AgroScan")
    apply_theme(app)
    try:
        repo = create_repository(settings, demo=args.demo)
    except ValueError as exc:
        QMessageBox.critical(None, "AgroScan v1.2 database unavailable", str(exc))
        sys.exit(1)
    auth = PostgresAuthService(repo) if isinstance(repo, PostgresRepository) else MockAuthService()
    controller = AppController(settings, auth, repo)
    if not controller.show_login():
        return
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
