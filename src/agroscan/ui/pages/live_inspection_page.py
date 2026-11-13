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
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QImageCapture,
    QMediaCaptureSession,
    QMediaDevices,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
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
from agroscan.models.vlm_models import VlmAnalysis
from agroscan.services import mock_ai, rule_engine
from agroscan.services.app_settings import AppSettings
from agroscan.services.evidence_service import capture_and_save_evidence
from agroscan.services.yolo_engine import (
    YoloEngine,
    YoloInferenceOutput,
    YoloInferenceThread,
    draw_detections_on_qimage,
)
from agroscan.ui.components.evidence_strip import EvidenceStrip
from agroscan.ui.components.page_layout import SectionCard, make_hint
from agroscan.ui.components.status_badge import StatusBadge
from agroscan.ui.components.vlm_result_panel import VlmResultPanel


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
        self._deep_analysis: Optional[VlmAnalysis] = None
        self._analysis_token = 0
        self._is_analyzing = False
        self._frame_history: dict[str, deque] = {}

        # Simulation feed state (D-031)
        self._is_sim_mode: bool = False
        self._custom_sim_image: Optional[QImage] = None
        self._current_raw_sim_image: Optional[QImage] = None
        self._current_sim_image: Optional[QImage] = None

        # YOLOv8 ONNX Runtime engine & background QThread worker (T1.4)
        self._yolo_engine = YoloEngine()
        self._yolo_worker = YoloInferenceThread(self._yolo_engine, self)

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
        column.setSpacing(12)

        # Feed Mode & Simulation Controls (D-031)
        source_bar = QHBoxLayout()
        source_bar.setSpacing(10)
        source_lbl = QLabel("Feed Source:")
        source_lbl.setObjectName("FormLabel")
        source_bar.addWidget(source_lbl)

        self.feed_mode_combo = QComboBox()
        self.feed_mode_combo.setObjectName("FormCombo")
        self.feed_mode_combo.addItem("🎥  Physical Camera (Live)", userData="camera")
        self.feed_mode_combo.addItem("🧪  Simulation Feed (Demo / D-031)", userData="simulation")
        self.feed_mode_combo.setFixedWidth(270)
        source_bar.addWidget(self.feed_mode_combo)

        self.sim_controls_widget = QWidget()
        sim_layout = QHBoxLayout(self.sim_controls_widget)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.setSpacing(8)

        sample_lbl = QLabel("Sample:")
        sample_lbl.setObjectName("FormLabel")
        sim_layout.addWidget(sample_lbl)

        self.sim_sample_combo = QComboBox()
        self.sim_sample_combo.setObjectName("FormCombo")
        self.sim_sample_combo.addItem("🍌 Fresh Bananas (Pass)", userData="fresh")
        self.sim_sample_combo.addItem("🍌 Bruised Bananas (Fail - 15% bruised)", userData="bruised")
        self.sim_sample_combo.addItem("🍌 Rotten Bananas (Fail - 1 critical rotten)", userData="rotten")
        self.sim_sample_combo.addItem("🍎 Fresh Apples (Pass)", userData="apple_fresh")
        self.sim_sample_combo.addItem("📁 Custom Image File...", userData="custom")
        sim_layout.addWidget(self.sim_sample_combo, 1)

        self.btn_load_custom = QPushButton("Browse...")
        self.btn_load_custom.setObjectName("SecondaryButton")
        self.btn_load_custom.setFixedHeight(32)
        self.btn_load_custom.setVisible(False)
        sim_layout.addWidget(self.btn_load_custom)

        self.sim_controls_widget.setVisible(False)
        source_bar.addWidget(self.sim_controls_widget, 1)
        source_bar.addStretch()
        column.addLayout(source_bar)

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
            "AgroScan requires an inspection feed. Connect the physical camera, "
            "or switch to Simulation Feed to continue in Demo Mode."
        )
        self.no_camera_text.setObjectName("PageSubtitle")
        self.no_camera_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_camera_text.setWordWrap(True)

        nc_btn_row = QHBoxLayout()
        nc_btn_row.setSpacing(10)
        self.btn_retry_camera = QPushButton("Retry")
        self.btn_retry_camera.setObjectName("SecondaryButton")
        self.btn_retry_camera.setFixedSize(110, 40)
        self.btn_switch_sim = QPushButton("🧪  Use Simulation Feed")
        self.btn_switch_sim.setObjectName("PrimaryButton")
        self.btn_switch_sim.setFixedHeight(40)
        self.btn_switch_sim.setCursor(Qt.CursorShape.PointingHandCursor)
        nc_btn_row.addWidget(self.btn_retry_camera)
        nc_btn_row.addWidget(self.btn_switch_sim)

        nc_layout.addWidget(nc_icon)
        nc_layout.addWidget(self.no_camera_title)
        nc_layout.addWidget(self.no_camera_text)
        nc_layout.addLayout(nc_btn_row)
        self.camera_stack.addWidget(no_camera)
        self._no_camera_panel = no_camera

        # Simulation Display Panel
        sim_panel = QWidget()
        sim_panel.setObjectName("SimulationPanel")
        sim_p_layout = QVBoxLayout(sim_panel)
        sim_p_layout.setContentsMargins(0, 0, 0, 0)
        sim_p_layout.setSpacing(0)
        self.sim_frame_label = QLabel()
        self.sim_frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sim_frame_label.setMinimumHeight(380)
        sim_p_layout.addWidget(self.sim_frame_label)
        self.camera_stack.addWidget(sim_panel)
        self._sim_panel = sim_panel

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

        # Deep analysis (VLM Result Panel, schema 1.0)
        self.deep_card = SectionCard("Deep Analysis")
        self.deep_suggestion = QLabel("▲  Low detection confidence — deep analysis recommended.")
        self.deep_suggestion.setObjectName("WarningNote")
        self.deep_suggestion.setWordWrap(True)
        self.deep_suggestion.setVisible(False)
        self.vlm_panel = VlmResultPanel()
        scenario_row = QHBoxLayout()
        scenario_row.setSpacing(8)
        scenario_label = QLabel("Demo outcome")
        scenario_label.setObjectName("FormLabel")
        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("FormCombo")
        self.scenario_combo.setToolTip(
            "DEMO MODE only: choose what the simulated AI service returns, "
            "to preview every state of the result panel."
        )
        for scenario in mock_ai.VlmScenario:
            self.scenario_combo.addItem(scenario.value, userData=scenario)
        scenario_row.addWidget(scenario_label)
        scenario_row.addWidget(self.scenario_combo, 1)
        self.deep_card.body.addWidget(self.deep_suggestion)
        self.deep_card.body.addWidget(self.vlm_panel)
        self.deep_card.body.addLayout(scenario_row)
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
        self._yolo_worker.inference_ready.connect(self._on_yolo_inference_ready)
        self.btn_retry_camera.clicked.connect(self._start_camera)
        self.btn_switch_sim.clicked.connect(lambda: self.feed_mode_combo.setCurrentIndex(1))
        self.feed_mode_combo.currentIndexChanged.connect(self._on_feed_mode_changed)
        self.sim_sample_combo.currentIndexChanged.connect(self._on_sim_sample_changed)
        self.btn_load_custom.clicked.connect(self._on_browse_custom_image)
        self.btn_capture.clicked.connect(self._on_capture)
        self.btn_deep.clicked.connect(self._on_deep_analysis)
        self.vlm_panel.retry_requested.connect(self._on_deep_analysis)
        self.vlm_panel.cancel_requested.connect(self._on_cancel_deep_analysis)
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
        self._detection, self._deep_analysis = None, None
        self._analysis_token += 1
        self._is_analyzing = False
        self.btn_deep.setText("Deep Analysis (Qwen-VL)")
        self._frame_history = {
            cls: deque(maxlen=self._SMOOTHING_FRAMES) for cls in session.product.detect_classes
        }

        self.session_label.setText(
            f"{session.session_id}   ·   Box {session.box_code}   ·   {session.product.name}"
            f"   ·   Inspector: {session.inspector}   ·   {session.station}"
        )
        self.status_badge.set_value(session.status)
        model_loaded = self._yolo_engine.load_for_product(session.product)
        if model_loaded:
            loaded_name = self._yolo_engine.model_path.name if self._yolo_engine.model_path else ""
            suffix = (
                "ONNX Runtime loaded"
                if loaded_name == session.product.model_file
                else f"generic fallback: {loaded_name}"
            )
            self.model_label.setText(f"Model: {session.product.model_file}  ({suffix})")
        else:
            self.model_label.setText(
                f"Model: {session.product.model_file}  (not loaded — simulated counts)"
            )
        self._build_realtime_rows(session.product.detect_classes)
        self.evidence_strip.set_evidence([])
        self.vlm_panel.set_idle()
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
            assessment=rule_engine.assess_quality(self._session.product, self._detection),
            deep_analysis=self._deep_analysis,
        )
        return record

    def clear_session(self) -> None:
        self._session = None
        self._analysis_token += 1
        self._is_analyzing = False
        self.btn_deep.setText("Deep Analysis (Qwen-VL)")
        self.vlm_panel.set_idle()
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
        if self._is_sim_mode:
            self.camera_stack.setCurrentWidget(self._sim_panel)
            self._update_sim_frame()
            self.camera_label.setText("Feed: Simulation / Demo Mode (D-031)")
            self._realtime_timer.start()
            self._update_buttons()
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
        self._yolo_worker.stop_worker(wait_ms=500)
        if self._camera is not None:
            self._camera.stop()
            self._capture_session.setCamera(None)
            self._camera.deleteLater()
            self._camera = None
        self._update_buttons()

    def _show_no_camera(self, title: str) -> None:
        self._stop_camera()
        if self._is_sim_mode:
            return
        self.no_camera_title.setText(title)
        self.camera_stack.setCurrentWidget(self._no_camera_panel)
        self.camera_label.setText("Camera: not available")
        self.realtime_total.setText("—")
        self._update_buttons()

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

    def _apply_realtime_counts(self, counts: dict[str, int]) -> None:
        for cls, count in counts.items():
            if cls in self._frame_history:
                self._frame_history[cls].append(count)
        smoothed = {
            cls: sum(h) / len(h) for cls, h in self._frame_history.items() if h
        }
        total = sum(smoothed.values())
        self.realtime_total.setText(f"{total:.0f}")
        for cls, value in smoothed.items():
            if cls in self._realtime_labels:
                share = value / total if total else 0
                self._realtime_labels[cls].setText(f"{value:.0f}   ({share:.0%})")

    def _on_yolo_inference_ready(self, output: YoloInferenceOutput) -> None:
        if self._session is None:
            return
        self._apply_realtime_counts(output.detection.class_counts)
        if self._is_sim_mode and self._current_raw_sim_image is not None:
            self._current_sim_image = draw_detections_on_qimage(
                self._current_raw_sim_image,
                output.boxes,
                fps_text=f"ONNX · {output.inference_ms:.1f} ms",
            )
            pixmap = QPixmap.fromImage(self._current_sim_image)
            scaled = pixmap.scaled(
                self.sim_frame_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.sim_frame_label.setPixmap(scaled)

    def _on_realtime_tick(self) -> None:
        if self._session is None:
            return
        if not self._camera_active() and not self._is_sim_mode:
            return

        if (
            self._is_sim_mode
            and self._yolo_engine.is_loaded
            and self._current_raw_sim_image is not None
        ):
            self._yolo_worker.submit_frame(self._current_raw_sim_image, track=True)
            return

        scenario = self.sim_sample_combo.currentData() if self._is_sim_mode else None
        if scenario == "rotten":
            counts = {"fresh": 17, "bruised": 2, "rotten": 1}
        elif scenario == "bruised":
            counts = {"fresh": 16, "bruised": 4, "rotten": 0}
        elif scenario in ("fresh", "apple_fresh"):
            counts = {"fresh": 19, "bruised": 1, "rotten": 0}
        else:
            counts = mock_ai.simulate_frame_counts(self._session.product)

        self._apply_realtime_counts(counts)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_capture(self) -> None:
        if self._is_sim_mode:
            if self._current_raw_sim_image is None:
                self._update_sim_frame()
            raw_frame = self._current_raw_sim_image or self._current_sim_image
            if raw_frame is not None:
                self._on_image_captured(0, raw_frame)
            return

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

        # T1.6 / D-026: Hash SHA-256 on raw image bytes and save to disk BEFORE drawing boxes
        try:
            item = capture_and_save_evidence(
                raw_image=image,
                session_id=self._session.session_id,
                sequence=len(self._evidence) + 1,
                is_auto_capture=False,
                settings=self._settings,
            )
        except Exception:
            item = EvidenceImage(captured_at=datetime.now(), is_auto_capture=False)

        display_image = image
        if self._yolo_engine.is_loaded:
            yolo_out = self._yolo_engine.infer(image, track=True)
            if yolo_out.detection.total_objects > 0:
                self._detection = yolo_out.detection
                display_image = draw_detections_on_qimage(
                    image,
                    yolo_out.boxes,
                    fps_text=f"ONNX · {yolo_out.inference_ms:.1f} ms",
                )
            else:
                self._detection = self._fallback_detection()
        else:
            self._detection = self._fallback_detection()

        self._evidence.append(item)
        self._images.append(display_image)
        self.evidence_strip.add_thumbnail(item, display_image)

        low_confidence = self._detection.mean_confidence < self._session.product.min_confidence
        self.deep_suggestion.setVisible(low_confidence)
        self._update_buttons()

    def _fallback_detection(self) -> DetectionResult:
        if self._session is None:
            return DetectionResult(total_objects=0, class_counts={}, mean_confidence=0.0)
        scenario = self.sim_sample_combo.currentData() if self._is_sim_mode else None
        if scenario == "rotten":
            counts = {"fresh": 17, "bruised": 2, "rotten": 1}
            return DetectionResult(total_objects=20, class_counts=counts, mean_confidence=0.92)
        if scenario == "bruised":
            counts = {"fresh": 16, "bruised": 4, "rotten": 0}
            return DetectionResult(total_objects=20, class_counts=counts, mean_confidence=0.88)
        if scenario in ("fresh", "apple_fresh"):
            counts = {"fresh": 19, "bruised": 1, "rotten": 0}
            return DetectionResult(total_objects=20, class_counts=counts, mean_confidence=0.95)
        return mock_ai.simulate_detection(self._session.product)

    def _on_deep_analysis(self) -> None:
        if self._session is None or self._detection is None:
            self.show_error("Capture an evidence image before requesting deep analysis.")
            return
        self._analysis_token += 1
        token = self._analysis_token
        self._is_analyzing = True
        self.btn_deep.setEnabled(False)
        self.btn_deep.setText("Analyzing…")
        self.vlm_panel.set_loading()
        QTimer.singleShot(self._DEEP_ANALYSIS_MS, lambda: self._on_deep_analysis_done(token))

    def _on_cancel_deep_analysis(self) -> None:
        self._analysis_token += 1          # Late response is ignored (token mismatch)
        self._is_analyzing = False
        self.btn_deep.setText("Deep Analysis (Qwen-VL)")
        self._update_buttons()
        if self._deep_analysis is not None:
            self.vlm_panel.set_analysis(self._deep_analysis, self._expected_label_values())
        else:
            self.vlm_panel.set_idle("Deep analysis cancelled. Press Deep Analysis to try again.")

    def _on_deep_analysis_done(self, token: int) -> None:
        if token != self._analysis_token:
            return                         # Cancelled or superseded
        self._is_analyzing = False
        self.btn_deep.setText("Deep Analysis (Qwen-VL)")
        self._update_buttons()
        if self._session is None or self._detection is None:
            return
        result = mock_ai.simulate_deep_analysis(
            self._session,
            self._detection,
            scenario=self.scenario_combo.currentData(),
            timeout_s=self._settings.load().ai_timeout_s,
        )
        if not result.is_error:
            self._deep_analysis = result   # Errors are shown but never stored in the record
        self.vlm_panel.set_analysis(result, self._expected_label_values())

    def _expected_label_values(self) -> dict[str, str]:
        """Giá trị theo đơn hàng để panel đánh dấu nhãn OCR khác khai báo (chỉ hiển thị)."""
        if self._session is None:
            return {}
        return {
            "box_code": self._session.box_code.text,
            "supplier": self._session.order.supplier,
        }

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
        can_capture = self._camera_active() or self._is_sim_mode
        self.btn_capture.setEnabled(has_session and can_capture)
        self.btn_deep.setEnabled(
            has_session and self._detection is not None and not self._is_analyzing
        )

    # ------------------------------------------------------------------
    # Simulation Feed Handlers & Rendering (D-031)
    # ------------------------------------------------------------------

    def _on_feed_mode_changed(self, index: int) -> None:
        mode = self.feed_mode_combo.itemData(index)
        self._is_sim_mode = (mode == "simulation")
        self.sim_controls_widget.setVisible(self._is_sim_mode)
        if self._session is not None and self.isVisible():
            self._start_camera()
        elif self._is_sim_mode:
            self._stop_camera()
            self.camera_stack.setCurrentWidget(self._sim_panel)
            self._update_sim_frame()
            self.camera_label.setText("Feed: Simulation / Demo Mode (D-031)")
            self._update_buttons()
        else:
            self._stop_camera()
            self.camera_stack.setCurrentWidget(self.video_widget)
            self._update_buttons()

    def _on_sim_sample_changed(self, index: int) -> None:
        scenario = self.sim_sample_combo.itemData(index)
        self.btn_load_custom.setVisible(scenario == "custom")
        if scenario == "custom" and self._custom_sim_image is None:
            self._on_browse_custom_image()
        else:
            self._update_sim_frame()

    def _on_browse_custom_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Inspection Sample Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            loaded = QImage(path)
            if not loaded.isNull():
                self._custom_sim_image = loaded
                self._update_sim_frame()
            else:
                self.show_error("Could not load the selected image file.")

    def _update_sim_frame(self) -> None:
        scenario = self.sim_sample_combo.currentData() or "fresh"
        if scenario == "custom" and self._custom_sim_image is not None:
            raw_img = self._custom_sim_image
        else:
            raw_img = self._render_raw_sim_image(scenario)
        self._current_raw_sim_image = raw_img

        if self._yolo_engine.is_loaded:
            yolo_out = self._yolo_engine.infer(raw_img, track=True)
            self._current_sim_image = draw_detections_on_qimage(
                raw_img,
                yolo_out.boxes,
                fps_text=f"ONNX · {yolo_out.inference_ms:.1f} ms",
            )
            self._apply_realtime_counts(yolo_out.detection.class_counts)
        else:
            self._current_sim_image = raw_img

        pixmap = QPixmap.fromImage(self._current_sim_image)
        scaled = pixmap.scaled(
            self.sim_frame_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.sim_frame_label.setPixmap(scaled)

    def _render_raw_sim_image(self, scenario: str) -> QImage:
        """Render an unannotated synthetic fruit crate image BEFORE bounding boxes (T1.6)."""
        img = QImage(800, 480, QImage.Format.Format_RGB32)
        img.fill(QColor(18, 22, 28))
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen_grid = QPen(QColor(35, 45, 58), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen_grid)
        for x in range(40, 800, 80):
            painter.drawLine(x, 40, x, 440)
        for y in range(40, 480, 80):
            painter.drawLine(40, y, 760, y)

        pen_crate = QPen(QColor(59, 130, 246, 140), 2)
        painter.setPen(pen_crate)
        painter.drawRoundedRect(50, 50, 700, 380, 8, 8)

        painter.setPen(QColor(148, 163, 184))
        painter.setFont(QFont("Inter", 10))
        prod = self._session.product.name if self._session else "Produce Crate"
        painter.drawText(65, 75, f"AGROSCAN INDUSTRIAL QC  ·  FEED: SIMULATION  ·  PRODUCT: {prod.upper()}")

        # 20 fruit positions (5 cols x 4 rows) inside crate
        cols_x = (140, 260, 380, 500, 620)
        rows_y = (100, 180, 260, 340)
        centers = [(cx, cy) for cy in rows_y for cx in cols_x]

        if scenario == "rotten":
            # 17 fresh, 2 bruised, 1 rotten -> critical Fail
            labels = ["fresh"] * 20
            labels[2] = "bruised"
            labels[8] = "rotten"
            labels[14] = "bruised"
        elif scenario == "bruised":
            # 16 fresh, 4 bruised (20% bruised > 10% max) -> Fail
            labels = ["fresh"] * 20
            for idx in (1, 4, 11, 17):
                labels[idx] = "bruised"
        else:
            # 19 fresh, 1 bruised (5% bruised <= 8-10% max) -> Pass
            labels = ["fresh"] * 20
            labels[12] = "bruised"

        painter.setPen(Qt.PenStyle.NoPen)
        for (cx, cy), cls_label in zip(centers, labels):
            if cls_label == "rotten":
                fill_color = QColor(240, 35, 40)
            elif cls_label == "bruised":
                fill_color = QColor(245, 165, 15)
            else:
                fill_color = QColor(20, 220, 90)
            painter.setBrush(fill_color)
            painter.drawRoundedRect(cx - 20, cy - 20, 40, 40, 8, 8)

        painter.setPen(QColor(100, 116, 139))
        painter.setFont(QFont("Inter", 9))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        painter.drawText(65, 415, f"REC ● EVIDENCE CAPTURE READY  ·  {now_str}")

        painter.end()
        return img

    def _render_sim_image(self, scenario: str) -> QImage:
        """Backward-compatible helper returning the annotated simulation frame."""
        raw = self._render_raw_sim_image(scenario)
        if self._yolo_engine.is_loaded:
            out = self._yolo_engine.infer(raw, track=True)
            return draw_detections_on_qimage(raw, out.boxes)
        return raw

    def showEvent(self, event) -> None:  # noqa: N802 — Qt override
        super().showEvent(event)
        if self._session is not None:
            self._start_camera()
            QTimer.singleShot(0, self.next_scan_field.setFocus)

    def hideEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._stop_camera()   # Giải phóng camera khi rời trang
        super().hideEvent(event)
