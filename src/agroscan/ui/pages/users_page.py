"""Users Management Page — view accounts, assign roles, reset passwords & toggle status (T3.5, D-027)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from agroscan.models.user_models import Role, User
from agroscan.services.mock_auth import MockAuthService
from agroscan.services.mock_repository import MockRepository
from agroscan.services.postgres_repository import PostgresRepository
from agroscan.ui.components.data_table import DataTable
from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard, make_hint


class UsersPage(ScrollPage):
    """Admin account directory: create/edit users, change passwords, and enable/disable access."""

    users_changed = Signal()

    def __init__(
        self,
        repo: MockRepository,
        auth_service: Optional[MockAuthService] = None,
        current_user: Optional[User] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("UsersPage", parent)
        self._repo = repo
        self._auth = auth_service
        self._current_user = current_user
        self._init_ui()
        self.refresh()

    def _init_ui(self) -> None:
        self.body.addWidget(
            PageHeader(
                "Users & Access Control",
                "Manage workstation accounts, role assignments (Admin, Inspector, Reviewer), passwords, and status.",
                is_mock=False,
            )
        )

        # Accounts Table
        table_card = SectionCard("Registered User Accounts")
        self.users_table = DataTable(["Username", "Display Name", "Role", "Status"])
        self.users_table.setMinimumHeight(220)
        table_card.body.addWidget(self.users_table)
        self.body.addWidget(table_card)

        # Account Editor Card
        editor_card = SectionCard("Create / Edit Account")
        form = QFormLayout()
        form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.username_field = QLineEdit()
        self.username_field.setObjectName("FormField")
        self.username_field.setPlaceholderText("e.g. inspector3")

        self.display_name_field = QLineEdit()
        self.display_name_field.setObjectName("FormField")
        self.display_name_field.setPlaceholderText("e.g. Shift B QC Inspector")

        self.role_combo = QComboBox()
        self.role_combo.setObjectName("FormCombo")
        for role in Role:
            self.role_combo.addItem(role.value, userData=role)

        self.password_field = QLineEdit()
        self.password_field.setObjectName("FormField")
        self.password_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_field.setPlaceholderText("Leave blank to keep existing password (min 4 chars)")

        self.active_checkbox = QCheckBox("Account is Active (allowed to sign in)")
        self.active_checkbox.setChecked(True)

        form.addRow(QLabel("Username", objectName="FormLabel"), self.username_field)
        form.addRow(QLabel("Display Name", objectName="FormLabel"), self.display_name_field)
        form.addRow(QLabel("Role", objectName="FormLabel"), self.role_combo)
        form.addRow(QLabel("New Password", objectName="FormLabel"), self.password_field)
        form.addRow(QLabel("Status", objectName="FormLabel"), self.active_checkbox)
        editor_card.body.addLayout(form)
        editor_card.body.addWidget(
            make_hint("Disabling an account immediately revokes any active session tokens for that user.")
        )

        self.status_label = QLabel("")
        self.status_label.setObjectName("HintLabel")
        editor_card.body.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.btn_new = QPushButton("+  New User")
        self.btn_new.setObjectName("SecondaryButton")
        self.btn_toggle_active = QPushButton("Toggle Active / Disable")
        self.btn_toggle_active.setObjectName("SecondaryButton")
        self.btn_save = QPushButton("Save Account")
        self.btn_save.setObjectName("PrimaryButton")

        for btn in (self.btn_new, self.btn_toggle_active, self.btn_save):
            btn.setFixedHeight(42)
            btn.setMinimumWidth(140)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        actions.addWidget(self.btn_new)
        actions.addWidget(self.btn_toggle_active)
        actions.addStretch()
        actions.addWidget(self.btn_save)
        editor_card.body.addLayout(actions)
        self.body.addWidget(editor_card)
        self.body.addStretch()

        self.users_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.btn_new.clicked.connect(self._on_new_user)
        self.btn_toggle_active.clicked.connect(self._on_toggle_active)
        self.btn_save.clicked.connect(self._on_save_user)

    def refresh(self) -> None:
        users = self._repo.users
        self.users_table.set_rows(
            [
                [
                    u.username,
                    u.display_name,
                    u.role.value,
                    "Active" if u.is_active else "Disabled",
                ]
                for u in users
            ],
            users,
        )
        if users and self.users_table.currentRow() < 0:
            self.users_table.selectRow(0)

    def _on_selection_changed(self) -> None:
        user: Optional[User] = self.users_table.selected_payload()
        if user is None:
            return
        self.username_field.setText(user.username)
        self.display_name_field.setText(user.display_name)
        idx = self.role_combo.findData(user.role)
        self.role_combo.setCurrentIndex(max(0, idx))
        self.active_checkbox.setChecked(user.is_active)
        self.password_field.clear()

    def _on_new_user(self) -> None:
        self.users_table.clearSelection()
        self.username_field.clear()
        self.display_name_field.clear()
        self.role_combo.setCurrentIndex(1)  # Inspector default
        self.active_checkbox.setChecked(True)
        self.password_field.clear()
        self.username_field.setFocus()
        self.status_label.setText("Enter details for the new user account and click Save Account.")

    def save_account(
        self,
        username: str,
        display_name: str,
        role: Role,
        is_active: bool = True,
        password: Optional[str] = None,
    ) -> User:
        """Persist account changes to both Repository (DB) and AuthService."""
        name = username.strip().lower()
        if (
            not is_active
            and self._current_user is not None
            and name == self._current_user.username.lower()
        ):
            raise ValueError("You cannot disable your own active administrator account.")

        saved = self._repo.save_user(
            username=name,
            display_name=display_name,
            role=role,
            is_active=is_active,
            password=password,
        )
        if self._auth is not None and not isinstance(self._repo, PostgresRepository):
            self._auth.upsert_user(
                username=name,
                display_name=display_name,
                role=role,
                is_active=is_active,
                password=password,
            )
        self.refresh()
        self.status_label.setText(f"✔  Account '{saved.username}' ({saved.role.value}) saved.")
        self.users_changed.emit()
        return saved

    def _on_save_user(self) -> None:
        try:
            self.save_account(
                username=self.username_field.text(),
                display_name=self.display_name_field.text(),
                role=self.role_combo.currentData() or Role.INSPECTOR,
                is_active=self.active_checkbox.isChecked(),
                password=self.password_field.text() or None,
            )
            self.password_field.clear()
        except ValueError as exc:
            self.status_label.setText(f"⚠  {exc}")

    def _on_toggle_active(self) -> None:
        user: Optional[User] = self.users_table.selected_payload()
        if user is None:
            return
        self.active_checkbox.setChecked(not user.is_active)
        self._on_save_user()

    def showEvent(self, event) -> None:  # noqa: N802
        self.refresh()
        super().showEvent(event)

