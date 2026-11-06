"""Login screen with quick-pick demo accounts and bearer session issuance (D-027)."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.user_models import AuthSession, User
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_auth import MockAuthService
from agroscan.ui.pages.settings_page import ConnectionSettingsDialog


class LoginDialog(QDialog):
    """Sign-in dialog; populates ``self.user`` and ``self.session`` when Accepted."""

    def __init__(
        self,
        auth: MockAuthService,
        settings: AppSettings,
        notice: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("LoginDialog")
        self.setWindowTitle("AgroScan — Sign In")
        self.setFixedSize(520, 680)
        self._auth = auth
        self._settings = settings
        self._initial_notice = notice.strip()
        self.user: Optional[User] = None
        self.session: Optional[AuthSession] = None
        self._init_ui()
        self._restore_preferences()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 28)
        root.setSpacing(0)

        brand = QLabel("AgroScan")
        brand.setObjectName("Brand")
        subtitle = QLabel("INSPECTION WORKSTATION")
        subtitle.setObjectName("BrandSubtitle")
        root.addWidget(brand)
        root.addWidget(subtitle)
        root.addSpacing(26)

        header_row = QHBoxLayout()
        title = QLabel("Sign in")
        title.setObjectName("LoginTitle")
        header_row.addWidget(title)
        header_row.addStretch()
        self.station_label = QLabel("")
        self.station_label.setObjectName("HintLabel")
        header_row.addWidget(self.station_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(header_row)
        root.addSpacing(18)

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
        root.addSpacing(10)

        options_row = QHBoxLayout()
        self.chk_remember = QCheckBox("Remember username")
        options_row.addWidget(self.chk_remember)
        options_row.addStretch()
        self.btn_toggle_pw = QPushButton("Show password")
        self.btn_toggle_pw.setObjectName("LinkButton")
        self.btn_toggle_pw.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_pw.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        options_row.addWidget(self.btn_toggle_pw)
        root.addLayout(options_row)
        root.addSpacing(10)

        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        root.addWidget(self.error_label)
        root.addSpacing(8)

        self.btn_sign_in = QPushButton("Sign In")
        self.btn_sign_in.setObjectName("PrimaryButton")
        self.btn_sign_in.setFixedHeight(46)
        self.btn_sign_in.setDefault(True)
        self.btn_sign_in.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.btn_sign_in)
        root.addSpacing(24)

        divider = QFrame()
        divider.setObjectName("FormDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)
        root.addSpacing(14)

        quick_title = QLabel("DEMO ACCOUNTS — QUICK SIGN IN")
        quick_title.setObjectName("FormSectionTitle")
        root.addWidget(quick_title)
        root.addSpacing(10)

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
        self.btn_toggle_pw.clicked.connect(self._toggle_password_visibility)
        self.btn_connection.clicked.connect(self._on_connection_settings)

    def _restore_preferences(self) -> None:
        self._refresh_station_label()
        state = self._settings.load_session_state()
        self.chk_remember.setChecked(state.remember_username)
        if state.remember_username and state.last_username:
            self.username.setText(state.last_username)
            self.password.setFocus()
        if self._initial_notice:
            self._show_error(self._initial_notice)

    def _refresh_station_label(self) -> None:
        station = self._settings.load().station_name or "STATION-01"
        self.station_label.setText(f"Station: {station}")

    def _toggle_password_visibility(self) -> None:
        hidden = self.password.echoMode() == QLineEdit.EchoMode.Password
        self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        )
        self.btn_toggle_pw.setText("Hide password" if hidden else "Show password")

    def _quick_sign_in(self, username: str, password: str) -> None:
        self.username.setText(username)
        self.password.setText(password)
        self._on_sign_in()

    def _on_sign_in(self) -> None:
        user, error = self._auth.authenticate_with_reason(
            self.username.text(), self.password.text()
        )
        if user is None:
            if self.password.text():
                self.password.clear()
            self._show_error(error or "Incorrect username or password.")
            return

        station = self._settings.load().station_name
        session = self._auth.issue_session(user, station_name=station)
        self._settings.save_session_state(
            session, remember_username=self.chk_remember.isChecked()
        )
        self.user = session.user
        self.session = session
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(f"⚠   {message}")
        self.error_label.setVisible(True)

    def _on_connection_settings(self) -> None:
        ConnectionSettingsDialog(self._settings, self).exec()
        self._refresh_station_label()
