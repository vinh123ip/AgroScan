"""Placeholder page for modules registered in ``navigation.py`` that are not yet built."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from agroscan.ui.components.page_layout import PageHeader, ScrollPage, SectionCard, make_hint


class PlaceholderPage(ScrollPage):
    """Temporary page showing the module header and a 'Coming Soon / Mock' card.

    Replace this page in ``MainWindow._create_page`` once the real module is implemented.
    """

    def __init__(
        self,
        title: str,
        description: str,
        planned_items: Optional[list[str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("PlaceholderPage", parent)
        self.body.addWidget(PageHeader(title, description, is_mock=True))

        card = SectionCard("Coming Soon / Mock")
        status = QLabel("This module is scheduled for an upcoming implementation phase.")
        status.setObjectName("ValueLabel")
        status.setWordWrap(True)
        card.body.addWidget(status)

        if planned_items:
            planned = QLabel("\n".join(f"•  {item}" for item in planned_items))
            planned.setObjectName("PlaceholderList")
            planned.setWordWrap(True)
            planned.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            card.body.addWidget(planned)

        card.body.addWidget(make_hint(
            "Navigation and role-based access for this module are active; "
            "detailed UI and backend integration are pending."
        ))
        self.body.addWidget(card)
        self.body.addStretch()
