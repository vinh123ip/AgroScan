from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class CircularSpinner(QWidget):
    """Vòng xoay loading mượt mà 60 FPS được vẽ bằng QPainter."""

    def __init__(self, size: int = 52, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 FPS
        self._timer.timeout.connect(self._rotate)

    def _rotate(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def start(self):
        self._angle = 0
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(5, 5, -5, -5)

        # Track ring in light slate (#E2E8F0)
        track_pen = QPen(QColor("#E2E8F0"), 4)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Active spinning arc in royal blue (#2563EB)
        active_pen = QPen(QColor("#2563EB"), 4)
        active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(active_pen)
        painter.drawArc(rect, -self._angle * 16, 110 * 16)


class LoadingScreen(QWidget):
    """Màn hình loading chuyển trang căn chỉnh chuẩn mực với trạng thái động và cd tối thiểu 2s."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("LoadingContainer")

        self._timer = QTimer(self)
        self._timer.setInterval(20)  # Cập nhật mỗi 20ms
        self._timer.timeout.connect(self._on_tick)

        self._duration_ms = 2000
        self._elapsed_ms = 0
        self._on_complete_callback: Optional[Callable[[], None]] = None

        self._init_ui()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(40, 40, 40, 40)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Thẻ Card trung tâm
        self.card = QFrame()
        self.card.setObjectName("LoadingCard")
        self.card.setFixedWidth(480)

        # Hiệu ứng đổ bóng mờ tạo chiều sâu
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(15, 23, 42, 22))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(42, 38, 42, 36)
        card_layout.setSpacing(0)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. Spinner ở trên cùng
        self.spinner = CircularSpinner(size=52)
        spinner_container = QHBoxLayout()
        spinner_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_container.addWidget(self.spinner)
        card_layout.addLayout(spinner_container)
        card_layout.addSpacing(18)

        # 2. Tiêu đề trang đang tải
        self.title_label = QLabel("Loading Page...")
        self.title_label.setObjectName("LoadingTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.title_label)
        card_layout.addSpacing(8)

        # 3. Phụ đề trạng thái (chuỗi hành động mô phỏng cho thấy hệ thống đang làm việc thực sự)
        self.status_label = QLabel("Connecting inspection services...")
        self.status_label.setObjectName("LoadingStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedHeight(22)  # Cố định chiều cao tránh nhảy bố cục khi đổi text
        card_layout.addWidget(self.status_label)
        card_layout.addSpacing(20)

        # 4. Khu vực thanh tiến trình và thông tin Estimate
        progress_container = QVBoxLayout()
        progress_container.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("LoadingProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        progress_container.addWidget(self.progress_bar)

        # Dòng thông tin: Estimate đếm lùi thực tế (trái) và Phần trăm tiến độ (phải)
        info_layout = QHBoxLayout()
        self.countdown_label = QLabel("Estimated: 2.0s")
        self.countdown_label.setObjectName("LoadingSubtitle")

        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("LoadingSubtitle")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        info_layout.addWidget(self.countdown_label)
        info_layout.addWidget(self.percent_label)
        progress_container.addLayout(info_layout)

        card_layout.addLayout(progress_container)
        root_layout.addWidget(self.card)

    def start(
        self,
        page_name: str,
        on_complete: Callable[[], None],
        estimated_ms: int = 2000,
        transition_ms: int = 300,
    ):
        """
        Bắt đầu chu trình loading chuyển trang nhanh gọn.
        - estimated_ms: Thời gian ước tính thực tế của module (hiển thị trên nhãn Estimated).
        - transition_ms: Thời gian chuyển cảnh loading nhanh (mặc định 300ms, không còn ép cd 2s).
        """
        self._duration_ms = max(50, transition_ms)
        self._elapsed_ms = 0
        self._on_complete_callback = on_complete

        self.title_label.setText(f"Loading {page_name}...")
        self.status_label.setText("Initializing...")

        # Giữ nguyên nhãn estimate thực tế của module theo yêu cầu
        est_sec = estimated_ms / 1000.0
        self.countdown_label.setText(f"Estimated: {est_sec:.1f}s")

        self.progress_bar.setValue(0)
        self.percent_label.setText("0%")

        self.spinner.start()
        self._timer.start()

    def complete(self):
        """Hoàn tất ngay lập tức khi tác vụ thực tế hoàn thành (không bị nghẽn cd)."""
        self._elapsed_ms = self._duration_ms
        self._timer.stop()
        self.spinner.stop()
        self.progress_bar.setValue(100)
        self.percent_label.setText("100%")
        self.status_label.setText("Ready!")
        self._trigger_completion_flash()

    def _on_tick(self):
        self._elapsed_ms += self._timer.interval()

        progress = min(100, int((self._elapsed_ms / self._duration_ms) * 100))
        self.progress_bar.setValue(progress)
        self.percent_label.setText(f"{progress}%")

        if progress < 30:
            self.status_label.setText("Initializing...")
        elif progress < 80:
            self.status_label.setText("Working...")
        else:
            self.status_label.setText("Ready!")

        if self._elapsed_ms >= self._duration_ms:
            self.complete()

    def _trigger_completion_flash(self):
        """Subtle royal-blue glow (#2563EB) when page transition completes."""
        shadow = self.card.graphicsEffect()
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(QColor(37, 99, 235, 95))
            shadow.setBlurRadius(44)

        # Nhịp flash nhanh gọn 100ms rồi chuyển cảnh mượt
        QTimer.singleShot(100, self._finalize_completion)

    def _finalize_completion(self):
        shadow = self.card.graphicsEffect()
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(QColor(15, 23, 42, 22))
            shadow.setBlurRadius(32)

        callback = self._on_complete_callback
        self.stop()
        if callback:
            callback()

    def stop(self):
        """Dừng hoàn toàn tiến trình loading và xóa callback đang chờ."""
        if self._timer.isActive():
            self._timer.stop()
        self.spinner.stop()
        self._on_complete_callback = None

        shadow = self.card.graphicsEffect()
        if isinstance(shadow, QGraphicsDropShadowEffect):
            shadow.setColor(QColor(15, 23, 42, 22))
            shadow.setBlurRadius(32)
