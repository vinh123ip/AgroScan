"""Full-size evidence image viewer for reviewers (T2.4, D-026).

Shows the original still image (loaded from disk when available, so the
reviewer sees the unannotated raw frame), zoom controls, and the stored file
path with SHA-256 integrity status.
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import EvidenceImage
from agroscan.services.evidence_service import (
    load_evidence_qimage,
    resolve_evidence_path,
    verify_evidence_integrity,
)


class EvidenceViewerDialog(QDialog):
    """Modal viewer with fit-to-window and step zoom for one evidence image."""

    _ZOOM_STEP = 1.25
    _MIN_ZOOM = 0.1
    _MAX_ZOOM = 8.0

    def __init__(
        self,
        item: EvidenceImage,
        image: Optional[QImage] = None,
        title: str = "Evidence Image",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EvidenceViewerDialog")
        self.setWindowTitle(title)
        self.resize(1000, 720)

        self._item = item
        self._source_label = "memory"
        self._image = self._load_image(item, image)
        self._zoom = 1.0
        self._fit = True
        self.integrity_state = self._compute_integrity(item)

        self._init_ui()
        self._render()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_image(self, item: EvidenceImage, fallback: Optional[QImage]) -> Optional[QImage]:
        if item.relative_path:
            from_disk = load_evidence_qimage(item)
            if from_disk is not None:
                self._source_label = "disk"
                return from_disk
        if fallback is not None and not fallback.isNull():
            return fallback
        return None

    @staticmethod
    def _compute_integrity(item: EvidenceImage) -> str:
        """Return ``verified``, ``mismatch``, ``missing`` or ``unsaved``."""
        if not item.relative_path or not item.sha256:
            return "unsaved"
        if resolve_evidence_path(item) is None:
            return "missing"
        return "verified" if verify_evidence_integrity(item) else "mismatch"

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def is_fit(self) -> bool:
        return self._fit

    @property
    def has_image(self) -> bool:
        return self._image is not None

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_in = QPushButton("+")
        self.btn_fit = QPushButton("Fit")
        self.btn_actual = QPushButton("100%")
        for btn in (self.btn_zoom_out, self.btn_zoom_in, self.btn_fit, self.btn_actual):
            btn.setObjectName("SecondaryButton")
            btn.setFixedHeight(34)
            btn.setMinimumWidth(56)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            bar.addWidget(btn)
        self.zoom_label = QLabel("")
        self.zoom_label.setObjectName("HintLabel")
        bar.addWidget(self.zoom_label)
        bar.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("PrimaryButton")
        self.btn_close.setFixedHeight(34)
        bar.addWidget(self.btn_close)
        layout.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("PageScrollArea")
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidgetResizable(False)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.image_label)
        layout.addWidget(self.scroll, 1)

        self.info_label = QLabel(self._info_text())
        self.info_label.setObjectName("ValueLabel")
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info_label)

        self.integrity_label = QLabel(self._integrity_text())
        self.integrity_label.setObjectName(
            "InlineErrorLabel" if self.integrity_state in ("mismatch", "missing") else "HintLabel"
        )
        self.integrity_label.setWordWrap(True)
        layout.addWidget(self.integrity_label)

        self.btn_zoom_in.clicked.connect(lambda: self.zoom_by(self._ZOOM_STEP))
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_by(1 / self._ZOOM_STEP))
        self.btn_fit.clicked.connect(self.fit_to_window)
        self.btn_actual.clicked.connect(self.actual_size)
        self.btn_close.clicked.connect(self.accept)
        QShortcut(QKeySequence("Ctrl++"), self, activated=lambda: self.zoom_by(self._ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl+="), self, activated=lambda: self.zoom_by(self._ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl+-"), self, activated=lambda: self.zoom_by(1 / self._ZOOM_STEP))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=self.fit_to_window)

    def _info_text(self) -> str:
        item = self._item
        source = "MANUAL" if not item.is_auto_capture else "AUTO"
        lines = [f"{source} capture  ·  {item.captured_at:%Y-%m-%d %H:%M:%S}"]
        if item.relative_path:
            lines.append(f"File: {item.relative_path}")
        if item.sha256:
            lines.append(f"SHA-256: {item.sha256}")
        if self._image is not None:
            lines.append(
                f"Size: {self._image.width()} × {self._image.height()} px  ·  loaded from {self._source_label}"
            )
        return "\n".join(lines)

    def _integrity_text(self) -> str:
        return {
            "verified": "✔  Integrity verified — file on disk matches the stored SHA-256.",
            "mismatch": "✖  Integrity check FAILED — the file on disk does not match the stored SHA-256.",
            "missing": "✖  Image file not found on the storage path.",
            "unsaved": "No stored file or hash for this image (not persisted yet).",
        }[self.integrity_state]

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def fit_to_window(self) -> None:
        self._fit = True
        self._render()

    def actual_size(self) -> None:
        self._fit = False
        self._zoom = 1.0
        self._render()

    def zoom_by(self, factor: float) -> None:
        if self._image is None:
            return
        if self._fit:
            self._zoom = self._fit_zoom()
            self._fit = False
        self._zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, self._zoom * factor))
        self._render()

    def _fit_zoom(self) -> float:
        if self._image is None:
            return 1.0
        area = self.scroll.viewport().size()
        if self._image.width() <= 0 or self._image.height() <= 0:
            return 1.0
        return max(
            self._MIN_ZOOM,
            min(
                self._MAX_ZOOM,
                min(area.width() / self._image.width(), area.height() / self._image.height()),
            ),
        )

    def _render(self) -> None:
        if self._image is None:
            self.image_label.setText("Image not available")
            self.image_label.adjustSize()
            self.zoom_label.setText("")
            return
        if self._fit:
            self._zoom = self._fit_zoom()
        width = max(1, int(self._image.width() * self._zoom))
        height = max(1, int(self._image.height() * self._zoom))
        pixmap = QPixmap.fromImage(self._image).scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(pixmap)
        self.image_label.resize(pixmap.size())
        self.zoom_label.setText(f"{self._zoom:.0%}" + ("  (fit)" if self._fit else ""))

    def resizeEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().resizeEvent(event)
        if self._fit and self._image is not None:
            self._render()

