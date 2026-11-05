"""Login screen with quick-pick demo accounts (D-027)."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.user_models import User
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_auth import MockAuthService
from agroscan.ui.pages.settings_page import ConnectionSettingsDialog


class LoginDialog(QDialog):
    """Đăng nhập; ``self.user`` được gán khi dialog trả về Accepted."""

    def __init__(
        self,
        auth: MockAuthService,
        settings: AppSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LoginDialog")
        self.setWindowTitle("AgroScan — Sign In")
        self.setFixedSize(520, 640)
        self._auth = auth
        self._settings = settings
        self.user: Optional[User] = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 44, 48, 32)
        root.setSpacing(0)

        brand = QLabel("AgroScan")
        brand.setObjectName("Brand")
        subtitle = QLabel("INSPECTION WORKSTATION")
        subtitle.setObjectName("BrandSubtitle")
        root.addWidget(brand)
        root.addWidget(subtitle)
        root.addSpacing(32)

        title = QLabel("Sign in")
        title.setObjectName("LoginTitle")
        root.addWidget(title)
        root.addSpacing(20)

        self.username = QLineEdit()
        self.username.setObjectName("FormField")
        self.username.setPlaceholderText("Username")
        self.password = QLineEdit()
        self.password.setObjectName("FormField")
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        root.addWidget(self.username)
        root.addSpacing(12)
        root.addWidget(self.password)
        root.addSpacing(12)

        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)
        root.addSpacing(8)

        self.btn_sign_in = QPushButton("Sign In")
        self.btn_sign_in.setObjectName("PrimaryButton")
        self.btn_sign_in.setFixedHeight(46)
        self.btn_sign_in.setDefault(True)
        self.btn_sign_in.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.btn_sign_in)
        root.addSpacing(28)

        divider = QFrame()
        divider.setObjectName("FormDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)
        root.addSpacing(16)

        quick_title = QLabel("DEMO ACCOUNTS — QUICK SIGN IN")
        quick_title.setObjectName("FormSectionTitle")
        root.addWidget(quick_title)
        root.addSpacing(12)

        quick_row = QHBoxLayout()
        quick_row.setSpacing(10)
        for user, password in self._auth.demo_accounts():
            button = QPushButton(f"{user.role.value}\n{user.username}")
            button.setObjectName("QuickLoginButton")
            button.setFixedHeight(60)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, u=user.username, p=password: self._quick_sign_in(u, p)
            )
            quick_row.addWidget(button)
        root.addLayout(quick_row)
        root.addStretch()

        footer = QHBoxLayout()
        self.btn_connection = QPushButton("⚙  Connection Settings")
        self.btn_connection.setObjectName("LinkButton")
        self.btn_connection.setCursor(Qt.CursorShape.PointingHandCursor)
        footer.addWidget(self.btn_connection)
        footer.addStretch()
        demo = QLabel("DEMO MODE")
        demo.setObjectName("DemoBadge")
        footer.addWidget(demo)
        root.addLayout(footer)

        self.btn_sign_in.clicked.connect(self._on_sign_in)
        self.password.returnPressed.connect(self._on_sign_in)
        self.username.returnPressed.connect(self.password.setFocus)
        self.username.textChanged.connect(lambda: self.error_label.setVisible(False))
        self.password.textChanged.connect(lambda: self.error_label.setVisible(False))
        self.btn_connection.clicked.connect(self._on_connection_settings)

    def _quick_sign_in(self, username: str, password: str) -> None:
        self.username.setText(username)
        self.password.setText(password)
        self._on_sign_in()

    def _on_sign_in(self) -> None:
        if not self.username.text().strip() or not self.password.text():
            self._show_error("Enter username and password.")
            return
        user = self._auth.authenticate(self.username.text(), self.password.text())
        if user is None:
            self.password.clear()
            self._show_error("Incorrect username or password.")
            return
        self.user = user
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(f"⚠   {message}")
        self.error_label.setVisible(True)

    def _on_connection_settings(self) -> None:
        ConnectionSettingsDialog(self._settings, self).exec()
