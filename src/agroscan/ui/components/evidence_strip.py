"""Horizontal strip of evidence image thumbnails."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from agroscan.models.inspection_models import EvidenceImage


class EvidenceStrip(QWidget):
    """Hiển thị ảnh tĩnh đã chụp; ảnh chưa có dữ liệu thì hiện ô giữ chỗ."""

    _THUMB_W, _THUMB_H = 168, 112

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
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

        thumb = QLabel()
        thumb.setObjectName("EvidenceThumb")
        thumb.setFixedSize(self._THUMB_W, self._THUMB_H)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source = "AUTO" if item.is_auto_capture else "MANUAL"
        thumb.setToolTip(f"{source} capture · {item.captured_at:%H:%M:%S}")
        if image is not None and not image.isNull():
            thumb.setPixmap(QPixmap.fromImage(image).scaled(
                self._THUMB_W, self._THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            thumb.setText(f"IMAGE\n{item.captured_at:%H:%M:%S}")
        self._layout.insertWidget(self._layout.count() - 1, thumb)
