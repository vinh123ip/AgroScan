"""Application entry point: LoginDialog <-> MainWindow lifecycle (D-027, D-032)."""

import sys
from typing import Optional

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog

from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
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
        repo: MockRepository,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._auth = auth_service
        self._repo = repo
        self._window: Optional[MainWindow] = None

    @property
    def window(self) -> Optional[MainWindow]:
        return self._window

    def show_login(self) -> bool:
        """Open ``LoginDialog`` and launch ``MainWindow`` upon authentication."""
        app = QApplication.instance()
        if app is not None:
            app.setQuitOnLastWindowClosed(False)

        dialog = LoginDialog(self._auth, self._settings)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted and dialog.user is not None
        user = dialog.user
        dialog.deleteLater()
        if not accepted or user is None:
            return False

        self._window = MainWindow(
            user=user,
            auth_service=self._auth,
            repo=self._repo,
            settings=self._settings,
        )
        self._window.logout_requested.connect(self._on_logout_requested)
        self._window.show()
        if app is not None:
            app.setQuitOnLastWindowClosed(True)
        return True

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
        if not self.show_login():
            QApplication.quit()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AgroScan")
    apply_theme(app)

    controller = AppController(AppSettings(), MockAuthService(), MockRepository())
    if not controller.show_login():
        sys.exit(0)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
