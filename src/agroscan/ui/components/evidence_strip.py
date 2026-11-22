"""Horizontal strip of evidence image thumbnails (click to enlarge)."""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from agroscan.models.inspection_models import EvidenceImage
from agroscan.services.evidence_service import load_evidence_qimage


class _ThumbLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class EvidenceStrip(QWidget):
    """Hiển thị ảnh tĩnh đã chụp; bấm vào ảnh để xem phóng to (T2.4)."""

    thumbnail_clicked = Signal(int)   # index trong danh sách

    _THUMB_W, _THUMB_H = 168, 112

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._items: list[EvidenceImage] = []
        self._images: list[Optional[QImage]] = []
        self._thumbs: list[QLabel] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self._layout.addStretch()
        self.clear()

    def clear(self) -> None:
        while self._layout.count() > 1:
            widget = self._layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self._items, self._images, self._thumbs = [], [], []

    @property
    def thumbnail_count(self) -> int:
        return len(self._items)

    def set_evidence(
        self, evidence: list[EvidenceImage], images: Optional[list[QImage]] = None
    ) -> None:
        self.clear()
        images = images or []
        for i, item in enumerate(evidence):
            image = images[i] if i < len(images) else None
            self.add_thumbnail(item, image)
        if not evidence:
            empty = QLabel("No evidence images yet")
            empty.setObjectName("HintLabel")
            self._layout.insertWidget(0, empty)

    def add_thumbnail(self, item: EvidenceImage, image: Optional[QImage] = None) -> None:
        if self._layout.count() > 1:
            first = self._layout.itemAt(0).widget()
            if isinstance(first, QLabel) and first.objectName() == "HintLabel":
                first.deleteLater()
                self._layout.takeAt(0)

        thumb = _ThumbLabel()
        thumb.setObjectName("EvidenceThumb")
        thumb.setFixedSize(self._THUMB_W, self._THUMB_H)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        source = "AUTO" if item.is_auto_capture else "MANUAL"
        tooltip_lines = [f"{source} capture · {item.captured_at:%H:%M:%S}"]
        if item.relative_path:
            tooltip_lines.append(f"File: {item.relative_path}")
        if item.sha256:
            tooltip_lines.append(f"SHA-256: {item.sha256[:16]}…{item.sha256[-8:]}")
        tooltip_lines.append("Click to enlarge")
        thumb.setToolTip("\n".join(tooltip_lines))

        if (image is None or image.isNull()) and item.relative_path:
            image = load_evidence_qimage(item)

        if image is not None and not image.isNull():
            thumb.setPixmap(QPixmap.fromImage(image).scaled(
                self._THUMB_W, self._THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            hash_tag = f"\n#{item.sha256[:8]}" if item.sha256 else ""
            thumb.setText(f"IMAGE\n{item.captured_at:%H:%M:%S}{hash_tag}")

        index = len(self._items)
        self._items.append(item)
        self._images.append(image)
        self._thumbs.append(thumb)
        thumb.clicked.connect(lambda i=index: self.open_viewer(i))
        self._layout.insertWidget(self._layout.count() - 1, thumb)

    def open_viewer(self, index: int) -> None:
        """Open the full-size viewer dialog for the evidence at ``index``."""
        if not 0 <= index < len(self._items):
            return
        self.thumbnail_clicked.emit(index)
        from agroscan.ui.components.evidence_viewer_dialog import EvidenceViewerDialog

        dialog = EvidenceViewerDialog(
            self._items[index],
            self._images[index],
            title=f"Evidence Image {index + 1} of {len(self._items)}",
            parent=self.window(),
        )
        dialog.exec()
        dialog.deleteLater()
