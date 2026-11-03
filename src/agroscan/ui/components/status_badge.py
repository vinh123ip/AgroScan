"""Colored status pill for session status, AI recommendation and decisions."""

from enum import Enum
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from agroscan.models.inspection_models import (
    AiRecommendation,
    ReviewerDecision,
    SessionStatus,
)


# tone → dùng trong QSS: #StatusBadge[tone="..."]
_TONES: dict[Enum, str] = {
    AiRecommendation.PASS:         "good",
    AiRecommendation.FAIL:         "critical",
    AiRecommendation.NEEDS_REVIEW: "warning",
    ReviewerDecision.PASS:         "good",
    ReviewerDecision.FAIL:         "critical",
    ReviewerDecision.RE_INSPECT:   "warning",
    SessionStatus.IN_PROGRESS:     "info",
    SessionStatus.PENDING_REVIEW:  "warning",
    SessionStatus.COMPLETED:       "neutral",
}

# Biểu tượng đi kèm để trạng thái không chỉ dựa vào màu
_ICONS: dict[str, str] = {
    "good": "✔", "critical": "✖", "warning": "▲", "info": "●", "neutral": "■",
}


def tone_of(value: Optional[Enum]) -> str:
    return _TONES.get(value, "neutral") if value else "neutral"


class StatusBadge(QLabel):
    def __init__(self, value: Optional[Enum] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_value(value)

    def set_value(self, value: Optional[Enum], text: Optional[str] = None) -> None:
        tone = tone_of(value)
        label = text or (value.value if value else "—")
        self.set_tone(tone, label)

    def set_tone(self, tone: str, text: str) -> None:
        """Hiển thị nhãn tùy ý với một tone có sẵn (good/critical/warning/info/neutral)."""
        tone = tone if tone in _ICONS else "neutral"
        self.setText(f"{_ICONS[tone]}  {text.upper()}")
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
