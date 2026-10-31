"""Live Inspection page — steps 4–5: camera preview, evidence capture, deep analysis.

A live camera is mandatory: without one the page shows a blocking
"No camera detected" state and nothing can be captured.

UI-shell phase: the camera feed and captures are real (QtMultimedia), while
realtime counts, detection results and deep analysis are simulated
(``services.mock_ai``) and labelled as such. Captured images stay in memory
only — saving to SMB with SHA-256 (D-026) comes with the storage layer.
"""

from collections import deque
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QImageCapture,
    QMediaCaptureSession,
    QMediaDevices,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import (
    DetectionResult,
    EvidenceImage,
    InspectionRecord,
    InspectionSession,
)
from agroscan.services import mock_ai
from agroscan.services.app_settings import AppSettings
from agroscan.ui.components.evidence_strip import EvidenceStrip
from agroscan.ui.components.page_layout import SectionCard, make_hint
from agroscan.ui.components.status_badge import StatusBadge


class LiveInspectionPage(QWidget):

    inspection_finished = Signal(object)   # InspectionRecord (chưa gửi duyệt)
    next_box_scanned    = Signal(str)      # D-020: quét hộp mới khi đang kiểm tra
    session_discarded   = Signal()

    _REALTIME_INTERVAL_MS = 400
    _SMOOTHING_FRAMES     = 5
    _DEEP_ANALYSIS_MS     = 1500

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("LiveInspectionPage")
        self._settings = settings

        self._session: Optional[InspectionSession] = None
        self._evidence: list[EvidenceImage] = []
        self._images: list[QImage] = []
        self._detection: Optional[DetectionResult] = None
        self._deep_analysis: str = ""
        self._analysis_token = 0
        self._is_analyzing = False
        self._frame_history: dict[str, deque] = {}

        self._camera: Optional[QCamera] = None
        self._media_devices = QMediaDevices(self)
        self._capture_session = QMediaCaptureSession(self)
        self._image_capture = QImageCapture(self)
        self._capture_session.setImageCapture(self._image_capture)

        self._realtime_timer = QTimer(self)
        self._realtime_timer.setInterval(self._REALTIME_INTERVAL_MS)

        self._init_ui()
        self._connect_signals()
        self._set_session_widgets_enabled(False)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 28, 40, 28)
        root.setSpacing(18)

        # Session header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(6)
        title = QLabel("Live Inspection")
        title.setObjectName("PageTitleSmall")
        self.session_label = QLabel("No active session")
        self.session_label.setObjectName("PageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(self.session_label)
        header.addLayout(title_col, 1)
        self.status_badge = StatusBadge()
        header.addWidget(self.status_badge, alignment=Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addLayout(self._build_camera_column(), 3)
        body.addWidget(self._build_side_panel())
        root.addLayout(body, 1)

    def _build_camera_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(14)

        self.camera_stack = QStackedWidget()
        self.camera_stack.setObjectName("CameraFrame")
        self.camera_stack.setMinimumHeight(380)

        self.video_widget = QVideoWidget()
        self._capture_session.setVideoOutput(self.video_widget)
        self.camera_stack.addWidget(self.video_widget)

        no_camera = QWidget()
        no_camera.setObjectName("NoCameraPanel")
        nc_layout = QVBoxLayout(no_camera)
        nc_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nc_layout.setSpacing(12)
        nc_icon = QLabel("◉")
        nc_icon.setObjectName("NoCameraIcon")
        nc_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_camera_title = QLabel("No camera detected")
        self.no_camera_title.setObjectName("NoCameraTitle")
        self.no_camera_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_camera_text = QLabel(
            "AgroScan requires a live camera feed. Connect the inspection camera — "
            "it will be picked up automatically."
        )
        self.no_camera_text.setObjectName("PageSubtitle")
        self.no_camera_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_camera_text.setWordWrap(True)
        self.btn_retry_camera = QPushButton("Retry")
        self.btn_retry_camera.setObjectName("SecondaryButton")
        self.btn_retry_camera.setFixedSize(120, 40)
        nc_layout.addWidget(nc_icon)
        nc_layout.addWidget(self.no_camera_title)
        nc_layout.addWidget(self.no_camera_text)
        nc_layout.addWidget(self.btn_retry_camera, alignment=Qt.AlignmentFlag.AlignCenter)
        self.camera_stack.addWidget(no_camera)
        self._no_camera_panel = no_camera
        column.addWidget(self.camera_stack, 1)

        controls = QHBoxLayout()
        self.camera_label = QLabel("")
        self.camera_label.setObjectName("HintLabel")
        controls.addWidget(self.camera_label, 1)
        self.btn_deep = QPushButton("Deep Analysis (Qwen-VL)")
        self.btn_deep.setObjectName("SecondaryButton")
        self.btn_capture = QPushButton("●  Capture Evidence")
        self.btn_capture.setObjectName("PrimaryButton")
        for btn, width in ((self.btn_deep, 220), (self.btn_capture, 200)):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(width)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            controls.addWidget(btn)
        column.addLayout(controls)

        evidence_card = SectionCard("Evidence Images")
        self.evidence_strip = EvidenceStrip()
        evidence_card.body.addWidget(self.evidence_strip)
        evidence_card.body.addWidget(make_hint(
            "Official results are computed from captured still images, not from the live "
            "video. Auto-capture when the box is steady arrives with YOLO integration; "
            "use manual capture for now."
        ))
        column.addWidget(evidence_card)
        return column

    def _build_side_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("PageScrollArea")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(372)

        panel = QWidget()
        panel.setObjectName("ScrollContent")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(16)

        # Realtime metrics
        realtime = SectionCard("Realtime (Simulated)")
        self.realtime_total = QLabel("—")
        self.realtime_total.setObjectName("RealtimeValue")
        realtime.body.addWidget(QLabel("Objects in frame", objectName="KeyLabel"))
        realtime.body.addWidget(self.realtime_total)
        self.realtime_grid = QGridLayout()
        self.realtime_grid.setVerticalSpacing(8)
        realtime.body.addLayout(self.realtime_grid)
        self._realtime_labels: dict[str, QLabel] = {}
        self.model_label = make_hint("")
        realtime.body.addWidget(self.model_label)
        layout.addWidget(realtime)

        # Deep analysis
        self.deep_card = SectionCard("Deep Analysis")
        self.deep_suggestion = QLabel("▲  Low detection confidence — deep analysis recommended.")
        self.deep_suggestion.setObjectName("WarningNote")
        self.deep_suggestion.setWordWrap(True)
        self.deep_suggestion.setVisible(False)
        self.deep_text = QPlainTextEdit()
        self.deep_text.setObjectName("NotesField")
        self.deep_text.setReadOnly(True)
        self.deep_text.setPlaceholderText(
            "Press Deep Analysis to request a detailed review of the latest capture."
        )
        self.deep_text.setMinimumHeight(120)
        self.deep_card.body.addWidget(self.deep_suggestion)
        self.deep_card.body.addWidget(self.deep_text)
        layout.addWidget(self.deep_card, 1)

        # Next box (D-020)
        next_card = SectionCard("Next Box")
        self.next_scan_field = QLineEdit()
        self.next_scan_field.setObjectName("FormField")
        self.next_scan_field.setPlaceholderText("Scan next box to submit this one")
        next_card.body.addWidget(self.next_scan_field)
        self.error_label = QLabel("")
        self.error_label.setObjectName("InlineErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        next_card.body.addWidget(self.error_label)
        layout.addWidget(next_card)

        self.btn_finish = QPushButton("Finish Inspection  →")
        self.btn_finish.setObjectName("PrimaryButton")
        self.btn_discard = QPushButton("Discard Session")
        self.btn_discard.setObjectName("DangerButton")
        for btn in (self.btn_finish, self.btn_discard):
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(btn)
        scroll.setWidget(panel)
        return scroll

    def _connect_signals(self) -> None:
        self._media_devices.videoInputsChanged.connect(self._on_devices_changed)
        self._image_capture.imageCaptured.connect(self._on_image_captured)
        self._image_capture.errorOccurred.connect(
            lambda _id, _err, message: self.show_error(f"Capture failed — {message}")
        )
        self._image_capture.readyForCaptureChanged.connect(lambda _: self._update_buttons())
        self._realtime_timer.timeout.connect(self._on_realtime_tick)
        self.btn_retry_camera.clicked.connect(self._start_camera)
        self.btn_capture.clicked.connect(self._on_capture)
        self.btn_deep.clicked.connect(self._on_deep_analysis)
        self.btn_finish.clicked.connect(self._on_finish)
        self.btn_discard.clicked.connect(self._on_discard)
        self.next_scan_field.returnPressed.connect(self._on_next_scanned)
        self.next_scan_field.textEdited.connect(lambda: self.error_label.setVisible(False))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session(self) -> Optional[InspectionSession]:
        return self._session

    @property
    def captured_images(self) -> list[QImage]:
        return list(self._images)

    def start_session(self, session: InspectionSession) -> None:
        self._session = session
        self._evidence, self._images = [], []
        self._detection, self._deep_analysis = None, ""
        self._analysis_token += 1
        self._frame_history = {
            cls: deque(maxlen=self._SMOOTHING_FRAMES) for cls in session.product.detect_classes
        }

        self.session_label.setText(
            f"{session.session_id}   ·   Box {session.box_code}   ·   {session.product.name}"
            f"   ·   Inspector: {session.inspector}   ·   {session.station}"
        )
        self.status_badge.set_value(session.status)
        self.model_label.setText(
            f"Model: {session.product.model_file}  (not loaded — simulated counts)"
        )
        self._build_realtime_rows(session.product.detect_classes)
        self.evidence_strip.set_evidence([])
        self.deep_text.clear()
        self.deep_suggestion.setVisible(False)
        self.next_scan_field.clear()
        self.error_label.setVisible(False)
        self._set_session_widgets_enabled(True)
        if self.isVisible():
            self._start_camera()

    def finalize(self) -> Optional[InspectionRecord]:
        """Đóng phiên hiện tại thành InspectionRecord; None nếu chưa có ảnh bằng chứng."""
        if self._session is None or not self._evidence or self._detection is None:
            return None
        record = InspectionRecord(
            session=self._session,
            evidence=list(self._evidence),
            detection=self._detection,
            assessment=mock_ai.assess_quality(self._session.product, self._detection),
            deep_analysis=self._deep_analysis,
        )
        return record

    def clear_session(self) -> None:
        self._session = None
        self._analysis_token += 1
        self._stop_camera()
        self.session_label.setText("No active session")
        self.status_badge.set_value(None)
        self._set_session_widgets_enabled(False)

    def show_error(self, message: str) -> None:
        self.error_label.setText(f"⚠   {message}")
        self.error_label.setVisible(True)

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _select_device(self) -> Optional[QCameraDevice]:
        devices = QMediaDevices.videoInputs()
        if not devices:
            return None
        wanted = self._settings.load().camera_id
        for device in devices:
            if wanted and bytes(device.id()).decode(errors="replace") == wanted:
                return device
        default = QMediaDevices.defaultVideoInput()
        return default if not default.isNull() else devices[0]

    def _start_camera(self) -> None:
        self._stop_camera()
        if self._session is None:
            return
        device = self._select_device()
        if device is None:
            self._show_no_camera("No camera detected")
            return
        self._camera = QCamera(device, self)
        self._camera.errorOccurred.connect(
            lambda _err, message: self._show_no_camera(f"Camera error — {message}")
        )
        self._camera.activeChanged.connect(lambda _: self._update_buttons())
        self._capture_session.setCamera(self._camera)
        self._camera.start()
        self.camera_stack.setCurrentWidget(self.video_widget)
        self.camera_label.setText(f"Camera: {device.description()}")
        self._realtime_timer.start()
        self._update_buttons()

    def _stop_camera(self) -> None:
        self._realtime_timer.stop()
        if self._camera is not None:
            self._camera.stop()
            self._capture_session.setCamera(None)
            self._camera.deleteLater()
            self._camera = None
        self._update_buttons()

    def _show_no_camera(self, title: str) -> None:
        self._stop_camera()
        self.no_camera_title.setText(title)
        self.camera_stack.setCurrentWidget(self._no_camera_panel)
        self.camera_label.setText("Camera: not available")
        self.realtime_total.setText("—")

    def _on_devices_changed(self) -> None:
        if self._session is not None and self.isVisible():
            self._start_camera()

    def _camera_active(self) -> bool:
        return self._camera is not None and self._camera.isActive()

    # ------------------------------------------------------------------
    # Realtime metrics (simulated, D-026: frame counts + moving average)
    # ------------------------------------------------------------------

    def _build_realtime_rows(self, classes: list[str]) -> None:
        while self.realtime_grid.count():
            widget = self.realtime_grid.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self._realtime_labels = {}
        for row, cls in enumerate(classes):
            name = QLabel(cls.capitalize())
            name.setObjectName("FormLabel")
            value = QLabel("—")
            value.setObjectName("ValueLabel")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.realtime_grid.addWidget(name, row, 0)
            self.realtime_grid.addWidget(value, row, 1)
            self._realtime_labels[cls] = value

    def _on_realtime_tick(self) -> None:
        if self._session is None or not self._camera_active():
            return
        counts = mock_ai.simulate_frame_counts(self._session.product)
        for cls, count in counts.items():
            self._frame_history[cls].append(count)
        smoothed = {
            cls: sum(h) / len(h) for cls, h in self._frame_history.items() if h
        }
        total = sum(smoothed.values())
        self.realtime_total.setText(f"{total:.0f}")
        for cls, value in smoothed.items():
            share = value / total if total else 0
            self._realtime_labels[cls].setText(f"{value:.0f}   ({share:.0%})")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_capture(self) -> None:
        if not self._camera_active():
            self.show_error("Camera is not running.")
            return
        if not self._image_capture.isReadyForCapture():
            self.show_error("Camera is not ready yet — try again in a moment.")
            return
        self._image_capture.capture()

    def _on_image_captured(self, _request_id: int, image: QImage) -> None:
        if self._session is None:
            return
        item = EvidenceImage(captured_at=datetime.now(), is_auto_capture=False)
        self._evidence.append(item)
        self._images.append(image)
        self.evidence_strip.add_thumbnail(item, image)

        self._detection = mock_ai.simulate_detection(self._session.product)
        low_confidence = self._detection.mean_confidence < self._session.product.min_confidence
        self.deep_suggestion.setVisible(low_confidence)
        self._update_buttons()

    def _on_deep_analysis(self) -> None:
        if self._session is None or self._detection is None:
            self.show_error("Capture an evidence image before requesting deep analysis.")
            return
        self._analysis_token += 1
        token = self._analysis_token
        self._is_analyzing = True
        self.btn_deep.setEnabled(False)
        self.btn_deep.setText("Analyzing…")
        self.deep_text.setPlainText("Waiting for AI service response…")
        QTimer.singleShot(self._DEEP_ANALYSIS_MS, lambda: self._on_deep_analysis_done(token))

    def _on_deep_analysis_done(self, token: int) -> None:
        self._is_analyzing = False
        self.btn_deep.setText("Deep Analysis (Qwen-VL)")
        self._update_buttons()
        if token != self._analysis_token or self._session is None or self._detection is None:
            return
        self._deep_analysis = mock_ai.simulate_deep_analysis(self._session.product, self._detection)
        self.deep_text.setPlainText("[SIMULATED]\n" + self._deep_analysis)

    def _on_finish(self) -> None:
        record = self.finalize()
        if record is None:
            self.show_error("Capture at least one evidence image before finishing.")
            return
        self._stop_camera()
        self.inspection_finished.emit(record)

    def _on_next_scanned(self) -> None:
        text = self.next_scan_field.text().strip()
        if text:
            self.next_scan_field.clear()
            self.next_box_scanned.emit(text)

    def _on_discard(self) -> None:
        answer = QMessageBox.question(
            self, "Discard Session",
            "Discard this session? Captured images and results will be lost.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_session()
            self.session_discarded.emit()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_session_widgets_enabled(self, enabled: bool) -> None:
        for widget in (self.btn_finish, self.btn_discard, self.next_scan_field):
            widget.setEnabled(enabled)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_session = self._session is not None
        self.btn_capture.setEnabled(has_session and self._camera_active())
        self.btn_deep.setEnabled(
            has_session and self._detection is not None and not self._is_analyzing
        )

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        if self._session is not None:
            self._start_camera()
            QTimer.singleShot(0, self.next_scan_field.setFocus)

    def hideEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._stop_camera()   # Giải phóng camera khi rời trang
        super().hideEvent(event)
