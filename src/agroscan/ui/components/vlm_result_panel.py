"""VLM Result Panel — renders one Qwen-VL deep analysis (schema 1.0, ``vlm_models``).

States (see docs/ui-spec/3.2.4.2-ui-spec.md §4):

* ``idle``    — nothing requested yet (hint text).
* ``loading`` — request in flight; Cancel is offered.
* ``result``  — status OK / PARTIAL: defects, label OCR, uncertainty,
  observations, AI assessment and suggestion, each in its own section.
* ``error``   — status ERROR: code-specific title, message, fallback note and
  Retry when the error is retryable.

Used by Live Inspection (narrow side panel) and ``RecordDetailWidget``
(assessment result / review queue). Read-only: VLM output never changes the
YOLO counts or the rule-engine recommendation (PROJECT.md §6).
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.vlm_models import (
    DefectSeverity,
    UncertaintyLevel,
    VlmAnalysis,
    VlmErrorCode,
    VlmStatus,
)
from agroscan.ui.components.page_layout import make_hint
from agroscan.ui.components.status_badge import StatusBadge


_STATUS_TONES = {VlmStatus.OK: "good", VlmStatus.PARTIAL: "warning", VlmStatus.ERROR: "critical"}
_UNCERTAINTY_TONES = {
    UncertaintyLevel.LOW: "good", UncertaintyLevel.MEDIUM: "warning", UncertaintyLevel.HIGH: "critical",
}
_SEVERITY_TEXT = {
    DefectSeverity.MINOR: "Minor", DefectSeverity.MAJOR: "Major", DefectSeverity.CRITICAL: "▲ Critical",
}
_ERROR_TITLES = {
    VlmErrorCode.TIMEOUT:             "AI service timed out",
    VlmErrorCode.SERVICE_UNAVAILABLE: "AI service unavailable",
    VlmErrorCode.INVALID_RESPONSE:    "Invalid response from AI service",
    VlmErrorCode.IMAGE_UNUSABLE:      "Image cannot be analyzed",
    VlmErrorCode.MODEL_ERROR:         "AI model error",
}
_ERROR_ADVICE = {
    VlmErrorCode.TIMEOUT:             "Try again, or increase the timeout in Settings.",
    VlmErrorCode.SERVICE_UNAVAILABLE: "Check the AI service URL in Settings and that the server is on.",
    VlmErrorCode.INVALID_RESPONSE:    "The response was rejected by schema validation and was not used.",
    VlmErrorCode.IMAGE_UNUSABLE:      "Capture a new, sharper evidence image, then run deep analysis again.",
    VlmErrorCode.MODEL_ERROR:         "Try again in a moment. Contact the administrator if it persists.",
}


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


class VlmResultPanel(QWidget):
    """Read-only view of a ``VlmAnalysis`` with idle / loading / result / error states."""

    retry_requested  = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("VlmResultPanel")
        self._state = "idle"
        self._analysis: Optional[VlmAnalysis] = None
        self._init_ui()
        self.set_idle()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Header: status + simulated flag + meta
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.status_badge = StatusBadge()
        self.simulated_label = QLabel("SIMULATED")
        self.simulated_label.setObjectName("MockBadge")
        header.addWidget(self.status_badge)
        header.addWidget(self.simulated_label)
        header.addStretch()
        self.header_row = QWidget()
        self.header_row.setLayout(header)
        layout.addWidget(self.header_row)
        self.meta_label = make_hint("")
        layout.addWidget(self.meta_label)

        # Idle
        self.idle_label = make_hint("")
        layout.addWidget(self.idle_label)

        # Loading
        self.loading_box = QWidget()
        loading_layout = QVBoxLayout(self.loading_box)
        loading_layout.setContentsMargins(0, 0, 0, 0)
        loading_layout.setSpacing(10)
        self.loading_label = QLabel("Analyzing the latest capture — waiting for AI service…")
        self.loading_label.setObjectName("VlmValue")
        self.loading_label.setWordWrap(True)
        self.loading_bar = QProgressBar()
        self.loading_bar.setObjectName("LoadingProgressBar")
        self.loading_bar.setRange(0, 0)          # Indeterminate
        self.loading_bar.setTextVisible(False)
        self.loading_bar.setFixedHeight(6)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("SecondaryButton")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.cancel_requested)
        loading_layout.addWidget(self.loading_label)
        loading_layout.addWidget(self.loading_bar)
        loading_layout.addWidget(self.btn_cancel, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.loading_box)

        # Error
        self.error_box = QFrame()
        self.error_box.setObjectName("VlmErrorBox")
        error_layout = QVBoxLayout(self.error_box)
        error_layout.setContentsMargins(16, 14, 16, 14)
        error_layout.setSpacing(8)
        self.error_title = QLabel("")
        self.error_title.setObjectName("VlmErrorTitle")
        self.error_title.setWordWrap(True)
        self.error_message = QLabel("")
        self.error_message.setObjectName("VlmErrorText")
        self.error_message.setWordWrap(True)
        self.error_message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_advice = make_hint("")
        self.error_fallback = make_hint(
            "The YOLO result and the rule-engine recommendation are still valid — "
            "you can finish the inspection without deep analysis."
        )
        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setObjectName("SecondaryButton")
        self.btn_retry.setFixedHeight(36)
        self.btn_retry.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_retry.clicked.connect(self.retry_requested)
        for widget in (self.error_title, self.error_message, self.error_advice, self.error_fallback):
            error_layout.addWidget(widget)
        error_layout.addWidget(self.btn_retry, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.error_box)

        # Result
        self.result_box = QWidget()
        result_layout = QVBoxLayout(self.result_box)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(10)

        self.warnings_label = QLabel("")
        self.warnings_label.setObjectName("WarningNote")
        self.warnings_label.setWordWrap(True)
        result_layout.addWidget(self.warnings_label)

        result_layout.addWidget(self._section_title("Defects"))
        self.defect_grid = self._make_grid()
        result_layout.addLayout(self.defect_grid)

        result_layout.addWidget(self._section_title("Label OCR"))
        self.ocr_note = QLabel("")
        self.ocr_note.setObjectName("WarningNote")
        self.ocr_note.setWordWrap(True)
        result_layout.addWidget(self.ocr_note)
        self.ocr_grid = self._make_grid()
        result_layout.addLayout(self.ocr_grid)

        result_layout.addWidget(self._section_title("Uncertainty"))
        self.uncertainty_badge = StatusBadge()
        result_layout.addWidget(self.uncertainty_badge, alignment=Qt.AlignmentFlag.AlignLeft)
        self.uncertainty_reasons = self._value_label()
        result_layout.addWidget(self.uncertainty_reasons)

        result_layout.addWidget(self._section_title("Observations"))
        self.observations_label = self._value_label()
        result_layout.addWidget(self.observations_label)

        result_layout.addWidget(self._section_title("AI Assessment"))
        self.assessment_label = self._value_label()
        result_layout.addWidget(self.assessment_label)

        result_layout.addWidget(self._section_title("Suggestion"))
        self.suggestion_label = self._value_label()
        result_layout.addWidget(self.suggestion_label)

        result_layout.addWidget(make_hint(
            "Advisory only — deep analysis never changes the YOLO counts or the "
            "system recommendation. The reviewer makes the final decision."
        ))
        layout.addWidget(self.result_box)

    @staticmethod
    def _section_title(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("KeyLabel")
        return label

    @staticmethod
    def _value_label() -> QLabel:
        label = QLabel("")
        label.setObjectName("VlmValue")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    @staticmethod
    def _make_grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        return grid

    @staticmethod
    def _clear_grid(grid: QGridLayout) -> None:
        while grid.count():
            widget = grid.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()

    def _cell(self, text: str, name: str = "VlmValue", tooltip: str = "") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        if tooltip:
            label.setToolTip(tooltip)
        return label

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> str:
        return self._state

    @property
    def analysis(self) -> Optional[VlmAnalysis]:
        return self._analysis

    def set_idle(self, text: str = "") -> None:
        self._analysis = None
        self.idle_label.setText(text or "Press Deep Analysis to request a detailed review "
                                        "of the latest capture.")
        self._show("idle")

    def set_loading(self) -> None:
        self._analysis = None
        self.status_badge.set_tone("info", "Analyzing")
        self.simulated_label.setVisible(False)
        self.meta_label.setText("")
        self._show("loading")

    def set_analysis(
        self, analysis: VlmAnalysis, expected: Optional[dict[str, str]] = None
    ) -> None:
        """Render ``analysis``. ``expected`` maps OCR keys to order values for mismatch flags."""
        self._analysis = analysis
        self.status_badge.set_tone(_STATUS_TONES[analysis.status], analysis.status.value)
        self.simulated_label.setVisible(analysis.is_simulated)
        meta = []
        if analysis.model:
            meta.append(analysis.model)
        if analysis.latency_ms:
            meta.append(f"{analysis.latency_ms / 1000:.1f} s")
        meta.append(f"{analysis.analyzed_at:%H:%M:%S}")
        if analysis.request_id:
            meta.append(analysis.request_id)
        self.meta_label.setText("  ·  ".join(meta))

        if analysis.is_error and analysis.error is not None:
            self._render_error(analysis)
            self._show("error")
        else:
            self._render_result(analysis, expected or {})
            self._show("result")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_error(self, analysis: VlmAnalysis) -> None:
        error = analysis.error
        assert error is not None
        self.error_title.setText(f"✖  {_ERROR_TITLES.get(error.code, 'Deep analysis failed')}")
        self.error_message.setText(f"{error.message}   [{error.code.value}]")
        self.error_advice.setText(_ERROR_ADVICE.get(error.code, ""))
        self.btn_retry.setVisible(error.retryable)

    def _render_result(self, analysis: VlmAnalysis, expected: dict[str, str]) -> None:
        self.warnings_label.setVisible(bool(analysis.warnings))
        self.warnings_label.setText("\n".join(f"▲  {w}" for w in analysis.warnings))

        # Defects
        self._clear_grid(self.defect_grid)
        if analysis.defects:
            for col, head in enumerate(("Class", "Count", "Severity", "Conf.")):
                self.defect_grid.addWidget(self._cell(head, "FormLabel"), 0, col)
            for row, defect in enumerate(analysis.defects, start=1):
                severity_name = (
                    "VlmCritical" if defect.severity == DefectSeverity.CRITICAL else "VlmValue"
                )
                self.defect_grid.addWidget(
                    self._cell(defect.defect_class.capitalize(), tooltip=defect.description), row, 0
                )
                self.defect_grid.addWidget(self._cell(str(defect.count)), row, 1)
                self.defect_grid.addWidget(
                    self._cell(_SEVERITY_TEXT[defect.severity], severity_name), row, 2
                )
                self.defect_grid.addWidget(self._cell(f"{defect.confidence:.0%}"), row, 3)
        else:
            self.defect_grid.addWidget(self._cell("No defects reported."), 0, 0)

        # OCR
        self._clear_grid(self.ocr_grid)
        ocr = analysis.ocr
        if ocr is None:
            self.ocr_note.setText("▲  Label OCR was not returned by the AI service.")
            self.ocr_note.setVisible(True)
        elif not ocr.readable or not ocr.fields:
            self.ocr_note.setText("▲  The box label could not be read. Check the label manually.")
            self.ocr_note.setVisible(True)
        else:
            self.ocr_note.setVisible(False)
            for row, item in enumerate(ocr.fields):
                self.ocr_grid.addWidget(self._cell(item.label, "FormLabel"), row * 2, 0)
                self.ocr_grid.addWidget(
                    self._cell(item.value, tooltip=f"OCR confidence {item.confidence:.0%}"), row * 2, 1
                )
                self.ocr_grid.addWidget(self._cell(f"{item.confidence:.0%}", "HintLabel"), row * 2, 2)
                wanted = expected.get(item.key)
                if wanted and _normalize(wanted) != _normalize(item.value):
                    self.ocr_grid.addWidget(
                        self._cell(f"≠  Differs from order: {wanted}", "VlmMismatch"), row * 2 + 1, 1, 1, 2
                    )
            self.ocr_grid.setColumnStretch(1, 1)

        # Uncertainty
        uncertainty = analysis.uncertainty
        if uncertainty is not None:
            self.uncertainty_badge.set_tone(
                _UNCERTAINTY_TONES[uncertainty.level],
                f"{uncertainty.level.value}  ·  {uncertainty.score:.2f}",
            )
            self.uncertainty_reasons.setText("\n".join(f"•  {r}" for r in uncertainty.reasons) or "—")
        else:
            self.uncertainty_badge.set_tone("neutral", "Unknown")
            self.uncertainty_reasons.setText("—")

        self.observations_label.setText(
            "\n".join(f"•  {o}" for o in analysis.observations) or "—"
        )
        self.assessment_label.setText(analysis.assessment or "—")
        self.suggestion_label.setText(analysis.suggestion or "—")

    def _show(self, state: str) -> None:
        self._state = state
        self.idle_label.setVisible(state == "idle")
        self.loading_box.setVisible(state == "loading")
        self.error_box.setVisible(state == "error")
        self.result_box.setVisible(state == "result")
        self.header_row.setVisible(state != "idle")
        self.meta_label.setVisible(state in ("result", "error") and bool(self.meta_label.text()))
