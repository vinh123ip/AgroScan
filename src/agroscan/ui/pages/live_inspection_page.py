"""Live Inspection page — steps 4–5: camera preview, evidence capture, deep analysis.

A live camera is mandatory: without one the page shows a blocking
"No camera detected" state and nothing can be captured.

UI-shell phase: the camera feed and captures are real (QtMultimedia), while
realtime counts, detection results and deep analysis are simulated
(``services.mock_ai``) and labelled as such. Captured images stay in memory
only — saving to SMB with SHA-256 (D-026) comes with the storage layer.
"""

import atexit
from collections import deque
from datetime import datetime
import logging
from pathlib import Path
from typing import Optional
import weakref

from PySide6.QtCore import QBuffer, QIODevice, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QKeySequence, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtMultimedia import (
    QCamera,
    QCameraDevice,
    QImageCapture,
    QMediaCaptureSession,
    QMediaDevices,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agroscan.models.inspection_models import (
    AuditEvent,
    DetectedUnit,
    BoxCoverageStatus,
    BoxZone,
    DetectionResult,
    EvidenceImage,
    InspectionRecord,
    InspectionSession,
    REQUIRED_COVERAGE_ZONES,
    compute_box_coverage,
)
from agroscan.models.vlm_models import VlmAnalysis
from agroscan.services import mock_ai, rule_engine, vlm_client
from agroscan.services.app_settings import AppSettings
from agroscan.services.evidence_service import capture_and_save_evidence, load_evidence_qimage
from agroscan.services.i18n import language_manager, tr
from agroscan.services.container_classifier import ContainerCheckResult
from agroscan.services.khang_ai_adapter import KhangAiAdapter
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


_LOG = logging.getLogger(__name__)
_ACTIVE_PREVIEW_LIFETIMES: weakref.WeakSet["_PreviewLifetime"] = weakref.WeakSet()
_ATEXIT_SHUTTING_DOWN = False


class _PreviewLifetime(QObject):
    """Keep preview QThreads parented safely outside LiveInspectionPage lifetime."""

    def __init__(
        self, engines: tuple[YoloEngine, ...], owner: Optional[QObject] = None
    ) -> None:
        app = QApplication.instance()
        super().__init__(app)
        self.workers = tuple(YoloInferenceThread(engine, self) for engine in engines)
        self._closed = False
        self._signals_disconnected = False
        self._owner_ref = weakref.ref(owner) if owner is not None else None
        _ACTIVE_PREVIEW_LIFETIMES.add(self)
        if owner is not None:
            owner.destroyed.connect(self.shutdown)
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def stop(self, wait_ms: int = 5000, *, permanent: bool = False) -> None:
        if self._closed:
            return
        for worker in self.workers:
            try:
                worker.stop_worker(wait_ms=0, permanent=permanent)
            except RuntimeError:
                pass
        for worker in self.workers:
            try:
                if not worker.wait(wait_ms):
                    raise RuntimeError("Could not join preview inference worker")
            except RuntimeError as exc:
                if "Could not join" in str(exc):
                    raise

    @Slot()
    def shutdown(self, *, defer_delete: bool = True) -> None:
        if self._closed:
            return
        if not self._signals_disconnected:
            self._signals_disconnected = True
            for worker in self.workers:
                for sig in (worker.inference_ready, worker.inference_error):
                    try:
                        sig.disconnect()
                    except (RuntimeError, TypeError):
                        pass
        unjoined: list[YoloInferenceThread] = []
        for worker in self.workers:
            try:
                worker.stop_worker(wait_ms=0, permanent=True)
            except RuntimeError:
                pass
        for worker in self.workers:
            try:
                if not worker.wait(10000):
                    unjoined.append(worker)
            except RuntimeError:
                pass
        if unjoined:
            raise RuntimeError("Could not join preview inference worker")

        owner = self._owner_ref() if self._owner_ref is not None else None
        if owner is not None:
            try:
                owner.destroyed.disconnect(self.shutdown)
            except (RuntimeError, TypeError):
                pass
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.disconnect(self.shutdown)
            except (RuntimeError, TypeError):
                pass
        self._closed = True
        if (
            defer_delete
            and not _ATEXIT_SHUTTING_DOWN
            and app is not None
            and not QApplication.closingDown()
        ):
            try:
                self.deleteLater()
            except RuntimeError:
                pass


def _shutdown_all_preview_lifetimes() -> None:
    global _ATEXIT_SHUTTING_DOWN
    _ATEXIT_SHUTTING_DOWN = True
    for lifetime in list(_ACTIVE_PREVIEW_LIFETIMES):
        try:
            lifetime.shutdown(defer_delete=False)
        except RuntimeError as exc:
            _LOG.warning("Preview worker did not stop cleanly at exit: %s", exc)


atexit.register(_shutdown_all_preview_lifetimes)


class LiveInspectionPage(QWidget):

    inspection_finished = Signal(object)   # InspectionRecord (chưa gửi duyệt)
    next_box_scanned    = Signal(str)      # D-020: quét hộp mới khi đang kiểm tra
    session_discarded   = Signal()

    _REALTIME_INTERVAL_MS = 400
    _SMOOTHING_FRAMES     = 5

    def __init__(self, settings: AppSettings, parent: Optional[QWidget] = None, *, demo: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("LiveInspectionPage")
        self._settings = settings
        self._demo = demo

        self._session: Optional[InspectionSession] = None
        self._evidence: list[EvidenceImage] = []
        self._images: list[QImage] = []
        self._detection: Optional[DetectionResult] = None
        self._deep_analysis: Optional[VlmAnalysis] = None
        self._session_audit: list[AuditEvent] = []
        self._analysis_token = 0
        self._is_analyzing = False
        self._frame_history: dict[str, deque] = {}

        # Request/session correlation and capture failure tracking
        self._session_generation = 0
        self._capture_requests: dict[int, tuple[int, str, BoxZone]] = {}
        self._retired_capture_ids: dict[int, None] = {}
        self._preview_revision = 0
        self._preview_request_id = 0
        self._last_completed_preview_id = 0
        self._frame_token = 0
        self._sim_frame_token = 0
        self._preview_requests: dict[int, tuple[int, str, int, Optional[QImage]]] = {}
        self._capture_analysis_error: Optional[str] = None

        # Simulation feed state (D-031)
        self._is_sim_mode: bool = False
        self._custom_original: Optional[tuple[bytes, str]] = None
        self._custom_sim_image: Optional[QImage] = None
        self._current_raw_sim_image: Optional[QImage] = None
        self._current_sim_image: Optional[QImage] = None

        # YOLOv8 ONNX Runtime engine & background QThread worker (T1.4)
        self._yolo_engine = YoloEngine()
        self._khang_adapter = KhangAiAdapter()
        self._khang_apple_engine = YoloEngine()
        self._preview_lifetime = _PreviewLifetime(
            (self._yolo_engine, self._khang_apple_engine),
            owner=self,
        )
        self._yolo_worker, self._khang_yolo_worker = self._preview_lifetime.workers
        self._last_container_check: Optional[ContainerCheckResult] = None

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
        self.page_title_label = QLabel(tr("live.title"))
        self.page_title_label.setObjectName("PageTitleSmall")
        self.session_label = QLabel("No active session")
        self.session_label.setObjectName("PageSubtitle")
        title_col.addWidget(self.page_title_label)
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

        self.apple_preset_label = QLabel("Apple Detector:")
        self.apple_preset_label.setObjectName("FormLabel")
        self.apple_preset_label.setVisible(False)
        self.apple_preset_combo = QComboBox()
        self.apple_preset_combo.setObjectName("FormCombo")
        self.apple_preset_combo.addItem("🍎 Open Box (1280)", userData="open_box")
        self.apple_preset_combo.addItem("🍎 Tray (960)", userData="tray")
        self.apple_preset_combo.addItem("🧪 Baseline 3-Class", userData="baseline")
        self.apple_preset_combo.setFixedWidth(185)
        self.apple_preset_combo.setVisible(False)
        source_bar.addWidget(self.apple_preset_label)
        source_bar.addWidget(self.apple_preset_combo)

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
        self.btn_deep = QPushButton(tr("live.deep_btn"))
        self.btn_deep.setObjectName("SecondaryButton")
        self.btn_capture = QPushButton(tr("live.capture_btn"))
        self.btn_capture.setObjectName("PrimaryButton")
        self.btn_import = QPushButton(tr("live.import"))
        self.btn_import.clicked.connect(self._import_original)
        for btn, width in ((self.btn_deep, 160), (self.btn_import, 130), (self.btn_capture, 160)):
            btn.setFixedHeight(44)
            btn.setMinimumWidth(width)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            controls.addWidget(btn)
        column.addLayout(controls)

        # Whole-Box Coverage Panel (3.4.5.1)
        self.coverage_card = SectionCard(tr("live.coverage.title"))
        cov_top = QHBoxLayout()
        cov_top.setSpacing(10)
        self.side_label = QLabel(tr("live.coverage.active_side"))
        self.side_label.setObjectName("FormLabel")
        self.zone_combo = QComboBox()
        self.zone_combo.setObjectName("FormCombo")
        self.zone_combo.setFixedWidth(185)
        for z in BoxZone:
            self.zone_combo.addItem(tr(f"zone.{z.value}"), userData=z)
        self.auto_advance_check = QCheckBox(tr("live.coverage.auto_advance"))
        self.auto_advance_check.setChecked(True)
        self.coverage_status_label = QLabel("")
        self.coverage_status_label.setObjectName("HintLabel")
        cov_top.addWidget(self.side_label)
        cov_top.addWidget(self.zone_combo)
        cov_top.addWidget(self.auto_advance_check)
        cov_top.addStretch()
        cov_top.addWidget(self.coverage_status_label)
        self.coverage_card.body.addLayout(cov_top)

        self.coverage_bar = QProgressBar()
        self.coverage_bar.setObjectName("CoverageProgressBar")
        self.coverage_bar.setRange(0, 100)
        self.coverage_bar.setValue(0)
        self.coverage_bar.setTextVisible(False)
        self.coverage_card.body.addWidget(self.coverage_bar)

        pills_row = QHBoxLayout()
        pills_row.setSpacing(8)
        self._zone_pills: dict[BoxZone, QLabel] = {}
        for z in BoxZone:
            pill = QLabel("")
            pill.setObjectName("CoveragePill")
            pill.setProperty("covered", "false")
            pills_row.addWidget(pill)
            self._zone_pills[z] = pill
        pills_row.addStretch()
        self.coverage_card.body.addLayout(pills_row)
        column.addWidget(self.coverage_card)

        evidence_card = SectionCard("Evidence Images")
        self.evidence_strip = EvidenceStrip()
        evidence_card.body.addWidget(self.evidence_strip)
        evidence_card.body.addWidget(make_hint(
            "Official results are computed from captured still images, not from the live "
            "video. View tags track camera angles. Confirm that all contents are visible in the count image before submission."
        ))
        column.addWidget(evidence_card)
        self._refresh_coverage_ui()
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
        self.operational_model_label = QLabel("")
        self.operational_model_label.setObjectName("WarningNote")
        self.operational_model_label.setWordWrap(True)
        self.operational_model_label.setVisible(False)
        realtime.body.addWidget(self.operational_model_label)
        self.container_advisory_label = QLabel("")
        self.container_advisory_label.setObjectName("WarningNote")
        self.container_advisory_label.setWordWrap(True)
        self.container_advisory_label.setVisible(False)
        realtime.body.addWidget(self.container_advisory_label)
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
        self._image_capture.errorOccurred.connect(self._on_capture_error)
        self._image_capture.readyForCaptureChanged.connect(lambda _: self._update_buttons())
        self._realtime_timer.timeout.connect(self._on_realtime_tick)
        self._yolo_worker.inference_ready.connect(self._on_yolo_inference_ready)
        self._yolo_worker.inference_error.connect(self._on_yolo_inference_error)
        self._khang_yolo_worker.inference_ready.connect(self._on_yolo_inference_ready)
        self._khang_yolo_worker.inference_error.connect(self._on_yolo_inference_error)
        self.btn_retry_camera.clicked.connect(self._start_camera)
        self.btn_switch_sim.clicked.connect(lambda: self.feed_mode_combo.setCurrentIndex(1))
        self.feed_mode_combo.currentIndexChanged.connect(self._on_feed_mode_changed)
        self.apple_preset_combo.currentIndexChanged.connect(self._sync_apple_detector_preset)
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
        self._capture_shortcut = QShortcut(QKeySequence("F5"), self)
        self._capture_shortcut.activated.connect(self._on_capture)
        language_manager().language_changed.connect(self.retranslate_ui)

    def retranslate_ui(self, _lang: str = "") -> None:
        self.page_title_label.setText(tr("live.title"))
        self.btn_import.setText(tr("live.import"))
        self.btn_capture.setText(tr("live.capture_btn"))
        if not self._is_analyzing:
            self.btn_deep.setText(tr("live.deep_btn"))
        self.btn_finish.setText(tr("live.finish_btn"))
        self.btn_discard.setText(tr("live.discard_btn"))
        self.side_label.setText(tr("live.coverage.active_side"))
        self.auto_advance_check.setText(tr("live.coverage.auto_advance"))
        current_zone = self.zone_combo.currentData()
        self.zone_combo.blockSignals(True)
        for idx, z in enumerate(BoxZone):
            self.zone_combo.setItemText(idx, tr(f"zone.{z.value}"))
        if current_zone is not None:
            pos = self.zone_combo.findData(current_zone)
            if pos >= 0:
                self.zone_combo.setCurrentIndex(pos)
        self.zone_combo.blockSignals(False)
        self._refresh_coverage_ui()

    @property
    def coverage_status(self) -> BoxCoverageStatus:
        """Return current Whole-Box Coverage summary for the active session (3.4.5.1)."""
        return compute_box_coverage(self._evidence)

    @property
    def is_coverage_complete(self) -> bool:
        return self.coverage_status.is_complete

    def current_capture_zone(self) -> BoxZone:
        data = self.zone_combo.currentData()
        return data if isinstance(data, BoxZone) else BoxZone.TOP

    def set_capture_zone(self, zone: BoxZone) -> None:
        idx = self.zone_combo.findData(zone)
        if idx >= 0:
            self.zone_combo.setCurrentIndex(idx)

    def _refresh_coverage_ui(self) -> None:
        cov = self.coverage_status
        pct = int(round(cov.percentage))
        self.coverage_bar.setValue(pct)
        self.coverage_bar.setProperty("complete", "true" if cov.is_complete else "false")
        self.coverage_bar.style().unpolish(self.coverage_bar)
        self.coverage_bar.style().polish(self.coverage_bar)

        if cov.is_complete:
            self.coverage_status_label.setText(
                tr("live.coverage.complete", covered=cov.covered_required, total=len(cov.required_zones))
            )
        else:
            missing_text = ", ".join(tr(f"zone.short.{z.value}") for z in cov.missing_zones)
            self.coverage_status_label.setText(
                tr(
                    "live.coverage.incomplete",
                    pct=pct,
                    covered=cov.covered_required,
                    total=len(cov.required_zones),
                    missing=missing_text,
                )
            )

        for z, pill in self._zone_pills.items():
            covered = z in cov.captured_zones
            is_req = z in REQUIRED_COVERAGE_ZONES
            prefix = "✔ " if covered else ("○ " if is_req else "+ ")
            pill.setText(f"{prefix}{tr(f'zone.short.{z.value}')}")
            pill.setProperty("covered", "true" if covered else "false")
            pill.style().unpolish(pill)
            pill.style().polish(pill)

    def _advance_to_next_uncovered_zone(self) -> None:
        if not self.auto_advance_check.isChecked():
            return
        missing = self.coverage_status.missing_zones
        if missing:
            self.set_capture_zone(missing[0])

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
        self._stop_camera()
        self._session_generation += 1
        self._capture_analysis_error = None

        self._session = session
        self._evidence, self._images = [], []
        self._detection, self._deep_analysis = None, None
        self._session_audit = [
            AuditEvent(
                action="Session Created",
                actor=session.inspector,
                role="Inspector",
                timestamp=session.started_at,
                details=f"Box {session.box_code.text} at {session.station}",
            )
        ]
        self._analysis_token += 1
        self._is_analyzing = False
        self.btn_deep.setText(tr("live.deep_btn"))
        self.set_capture_zone(BoxZone.TOP)
        self._refresh_coverage_ui()

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
            self._yolo_engine.unload()
            self.model_label.setText(
                f"Model: {session.product.model_file}  (not loaded — simulated counts)"
            )
        self._last_container_check = None
        self.container_advisory_label.clear()
        self.container_advisory_label.setVisible(False)
        self._set_operational_model_warning(None)
        is_apple_bundle = session.product.code.upper() == "APPLE" and self._khang_adapter.is_available()
        self.apple_preset_label.setVisible(is_apple_bundle)
        self.apple_preset_combo.setVisible(is_apple_bundle)
        self.apple_preset_combo.blockSignals(True)
        if is_apple_bundle:
            assigned_model = session.product.model_file.strip()
            if assigned_model == "apple_detector_tray.onnx":
                desired_preset = "tray"
            elif (
                session.order.lot_id is not None
                and assigned_model
                and assigned_model not in ("apple_detector_open_box.onnx", "apple_detector_tray.onnx")
            ):
                # Operational PostgreSQL profile specifies a non-Khang detector; respect it to avoid submit rejection.
                desired_preset = "baseline"
            else:
                desired_preset = "open_box"
            idx = self.apple_preset_combo.findData(desired_preset)
            if idx >= 0:
                self.apple_preset_combo.setCurrentIndex(idx)
        self.apple_preset_combo.blockSignals(False)
        self._sync_apple_detector_preset()
        self._sync_realtime_classes()
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
        model_error = self._submission_model_error()
        if model_error:
            self._set_operational_model_warning(model_error)
            self.show_error(model_error)
            return None
        assessment = rule_engine.assess_quality(self._session.product, self._detection)
        audit = list(self._session_audit)
        audit.append(
            AuditEvent(
                action="Assessment Prepared",
                actor=self._session.inspector,
                role="Inspector",
                timestamp=datetime.now(),
                details=(
                    f"AI recommendation: {assessment.recommendation.value} · "
                    f"coverage {self.coverage_status.percentage:.0f}%"
                ),
            )
        )
        record = InspectionRecord(
            session=self._session,
            evidence=list(self._evidence),
            detection=self._detection,
            assessment=assessment,
            deep_analysis=self._deep_analysis,
            audit_trail=audit,
        )
        return record

    def _assigned_operational_model(self) -> Optional[str]:
        if self._session is None or self._session.order.lot_id is None:
            return None
        assigned = self._session.product.model_file.strip()
        return assigned or None

    def _operational_warning_text(self) -> Optional[str]:
        assigned = self._assigned_operational_model()
        if assigned is None:
            return None
        engine = self._khang_apple_engine if self._use_khang_apple_detector() else self._yolo_engine
        actual = engine.model_path.name if engine.is_loaded and engine.model_path is not None else None
        if actual == assigned:
            return None
        return (
            f"DB profile expects '{assigned}'; selected detector is "
            f"'{actual or 'not loaded'}'. Select/load the assigned detector "
            "before running operational analysis."
        )

    def _model_assignment_error(self, *, demo: bool) -> Optional[str]:
        if demo:
            return None
        return self._operational_warning_text()

    def _submission_model_error(self) -> Optional[str]:
        assigned = self._assigned_operational_model()
        if assigned is None:
            return None
        if any((not item.demo_image) and item.model_file != assigned for item in self._evidence):
            return (
                f"DB profile expects '{assigned}'; captured evidence uses "
                "a different or unverified detector. Recapture with the "
                "assigned detector before submission."
            )
        return None

    def _set_operational_model_warning(self, message: Optional[str]) -> None:
        self.operational_model_label.setText(message or "")
        self.operational_model_label.setVisible(bool(message))

    def _use_khang_apple_detector(self) -> bool:
        return (
            self._session is not None
            and self._session.product.code.upper() == "APPLE"
            and self.apple_preset_combo.currentData() in ("open_box", "tray")
            and self._khang_apple_engine.is_loaded
        )

    def _sync_realtime_classes(self) -> None:
        if self._session is None:
            self._frame_history.clear()
            self._build_realtime_rows([])
            self.realtime_total.setText("—")
            return
        classes = (
            ["apple"]
            if (self._use_khang_apple_detector() and not self._is_sim_mode)
            else list(self._session.product.detect_classes)
        )
        self._frame_history = {cls: deque(maxlen=self._SMOOTHING_FRAMES) for cls in classes}
        self._build_realtime_rows(classes)
        self.realtime_total.setText("—")

    def _sync_apple_detector_preset(self) -> None:
        self._invalidate_preview()
        self._preview_lifetime.stop()
        preset = self.apple_preset_combo.currentData()
        if (
            self._session is None
            or self._session.product.code.upper() != "APPLE"
            or not self._khang_adapter.is_available()
            or preset not in ("open_box", "tray")
        ):
            self._khang_apple_engine.unload()
            if self._session is not None and self._session.product.code.upper() == "APPLE":
                if self._yolo_engine.is_loaded:
                    loaded_name = self._yolo_engine.model_path.name if self._yolo_engine.model_path else self._session.product.model_file
                    self.model_label.setText(f"Model: {loaded_name} (ONNX Runtime loaded)")
                self._sync_realtime_classes()
            self._set_operational_model_warning(self._operational_warning_text())
            self._update_buttons()
            return
        try:
            meta = self._khang_adapter.load_detector_preset(self._khang_apple_engine, str(preset))
            self.model_label.setText(
                f"Model: {meta['model_file']} ({preset} · {meta['image_size']}px ONNX)"
            )
        except Exception as exc:
            self._khang_apple_engine.unload()
            self.model_label.setText(f"Apple ONNX preset unavailable: {exc}")
        self._sync_realtime_classes()
        self._set_operational_model_warning(self._operational_warning_text())
        self._update_buttons()

    def clear_session(self) -> None:
        self._stop_camera()
        self._session_generation += 1
        self._capture_analysis_error = None
        self._session = None
        self._evidence.clear()
        self._images.clear()
        self._session_audit.clear()
        self._detection = self._deep_analysis = None
        self._last_container_check = None
        self._khang_apple_engine.unload()
        self.apple_preset_label.setVisible(False)
        self.apple_preset_combo.setVisible(False)
        self.container_advisory_label.clear()
        self.container_advisory_label.setVisible(False)
        self._set_operational_model_warning(None)
        self._frame_history.clear()
        self._build_realtime_rows([])
        self.realtime_total.setText("—")
        self.evidence_strip.set_evidence([])
        self._refresh_coverage_ui()
        self._analysis_token += 1
        self._is_analyzing = False
        self.btn_deep.setText(tr("live.deep_btn"))
        self.vlm_panel.set_idle()
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

    def _retire_capture_id(self, request_id: int) -> None:
        if request_id < 0:
            return
        self._retired_capture_ids.pop(request_id, None)
        self._retired_capture_ids[request_id] = None
        while len(self._retired_capture_ids) > 256:
            oldest = next(iter(self._retired_capture_ids))
            self._retired_capture_ids.pop(oldest, None)

    def _stop_camera(self) -> None:
        self._realtime_timer.stop()
        self._invalidate_preview()
        for rid in self._capture_requests:
            self._retire_capture_id(rid)
        self._capture_requests.clear()
        self._preview_lifetime.stop()
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

    def _invalidate_preview(self) -> None:
        self._preview_revision += 1
        self._last_completed_preview_id = 0
        self._preview_requests.clear()

    def _preview_detector_tag(self) -> str:
        role = (
            "khang"
            if self._use_khang_apple_detector() and not self._is_sim_mode
            else "baseline"
        )
        return f"{role}:{self._preview_revision}"

    def _submit_preview(self, image: QImage, *, simulation: bool) -> None:
        if self._session is None or simulation != self._is_sim_mode or image.isNull():
            return
        if self._model_assignment_error(demo=simulation):
            return

        use_khang = self._use_khang_apple_detector() and not simulation
        engine = self._khang_apple_engine if use_khang else self._yolo_engine
        worker = self._khang_yolo_worker if use_khang else self._yolo_worker
        if not engine.is_loaded:
            return

        tag = self._preview_detector_tag()
        for request_id, context in list(self._preview_requests.items()):
            if context[1] != tag:
                del self._preview_requests[request_id]
        while len(self._preview_requests) >= 8:
            keys = iter(self._preview_requests)
            next(keys)  # Preserve oldest in-flight request while capping pending queue
            self._preview_requests.pop(next(keys), None)

        if simulation:
            frame_token = self._sim_frame_token
            raw_frame = image.copy()
        else:
            self._frame_token += 1
            frame_token = self._frame_token
            raw_frame = None

        self._preview_request_id += 1
        request_id = self._preview_request_id
        self._preview_requests[request_id] = (
            self._session_generation,
            tag,
            frame_token,
            raw_frame,
        )
        try:
            worker.submit_frame(image, track=not use_khang, request_id=request_id)
        except Exception:
            self._preview_requests.pop(request_id, None)
            _LOG.exception("Could not submit preview inference")

    def _show_sim_image(self, image: QImage) -> None:
        self._current_sim_image = image
        pixmap = QPixmap.fromImage(image)
        self.sim_frame_label.setPixmap(
            pixmap.scaled(
                self.sim_frame_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _on_yolo_inference_error(self, *args) -> None:
        _LOG.warning(
            "Preview inference failed: %s",
            " | ".join(str(arg) for arg in args),
        )

    def _on_yolo_inference_ready(self, output: YoloInferenceOutput) -> None:
        context = self._preview_requests.pop(output.request_id, None)
        if context is None or self._session is None:
            return
        if output.request_id < self._last_completed_preview_id:
            return

        generation, detector_tag, frame_token, raw_frame = context
        if (
            generation != self._session_generation
            or detector_tag != self._preview_detector_tag()
        ):
            return

        if raw_frame is not None:
            if not self._is_sim_mode or frame_token != self._sim_frame_token:
                return
        elif self._is_sim_mode:
            return

        if self._model_assignment_error(demo=raw_frame is not None):
            return

        self._last_completed_preview_id = output.request_id
        for stale_id in [rid for rid in self._preview_requests if rid < output.request_id]:
            del self._preview_requests[stale_id]

        self._apply_realtime_counts(output.detection.class_counts)
        if raw_frame is not None:
            self._show_sim_image(
                draw_detections_on_qimage(
                    raw_frame,
                    output.boxes,
                    fps_text=f"ONNX · {output.inference_ms:.1f} ms",
                )
            )

    def _on_realtime_tick(self) -> None:
        if self._session is None:
            return
        if self._model_assignment_error(demo=self._is_sim_mode):
            return
        if not self._camera_active() and not self._is_sim_mode:
            return

        if (
            self._is_sim_mode
            and self._yolo_engine.is_loaded
            and self._current_raw_sim_image is not None
        ):
            self._submit_preview(self._current_raw_sim_image, simulation=True)
            return

        if not self._is_sim_mode:
            frame = self.video_widget.videoSink().videoFrame()
            if frame.isValid():
                self._submit_preview(frame.toImage(), simulation=False)
            return
        scenario = self.sim_sample_combo.currentData()
        if scenario == "custom":
            return
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
        if self._session is None:
            return
        model_error = self._model_assignment_error(demo=self._is_sim_mode)
        if model_error:
            self._set_operational_model_warning(model_error)
            self.show_error(model_error)
            return
        if self._is_sim_mode:
            if self._current_raw_sim_image is None:
                self._update_sim_frame()
            raw_frame = self._current_raw_sim_image
            if raw_frame is not None:
                self._capture_evidence(raw_frame, "imported_image", True,
                                       self._custom_original if self.sim_sample_combo.currentData() == "custom" else None)
            return

        if not self._camera_active():
            self.show_error("Camera is not running.")
            return
        if not self._image_capture.isReadyForCapture():
            self.show_error("Camera is not ready yet — try again in a moment.")
            return
        context = (
            self._session_generation,
            self._session.session_id,
            self.current_capture_zone(),
        )
        request_id = self._image_capture.capture()
        if request_id < 0:
            self.show_error("Camera rejected the capture request.")
            return
        self._retired_capture_ids.pop(request_id, None)
        self._capture_requests[request_id] = context

    def _on_image_captured(self, request_id: int, image: QImage) -> None:
        if self._session is None:
            for rid in self._capture_requests:
                self._retire_capture_id(rid)
            self._capture_requests.clear()
            self._retire_capture_id(request_id)
            return
        context = self._capture_requests.pop(request_id, None)
        if context is not None:
            self._retire_capture_id(request_id)
            generation, session_id, captured_zone = context
            if generation != self._session_generation or session_id != self._session.session_id:
                return
            self._capture_evidence(image, "camera", False, captured_zone=captured_zone)
            return
        if (
            self._camera is not None
            or self._is_sim_mode
            or request_id in self._retired_capture_ids
            or bool(self._capture_requests)
        ):
            return
        self._capture_evidence(image, "camera", False)

    def _on_capture_error(self, request_id: int, _error, message: str) -> None:
        context = self._capture_requests.pop(request_id, None)
        if request_id >= 0:
            self._retire_capture_id(request_id)
        if self._session is None:
            return
        if context is None:
            if request_id < 0:
                self.show_error(f"Capture failed — {message}")
            return
        generation, session_id, _zone = context
        if generation == self._session_generation and session_id == self._session.session_id:
            self.show_error(f"Capture failed — {message}")

    def _capture_evidence(self, image: QImage, source: str, demo: bool,
                          original: Optional[tuple[bytes, str]] = None,
                          *, captured_zone: Optional[BoxZone] = None) -> None:
        if self._session is None:
            return
        model_error = self._model_assignment_error(demo=demo)
        if model_error:
            self._set_operational_model_warning(model_error)
            self.show_error(model_error)
            return

        # T1.6 / D-026 / 3.4.5.1: Hash SHA-256 on raw image bytes and tag box surface zone
        zone = captured_zone if captured_zone is not None else self.current_capture_zone()
        try:
            item = capture_and_save_evidence(
                raw_image=original[0] if original else image,
                image_format=original[1] if original else "PNG",
                session_id=self._session.session_id,
                sequence=len(self._evidence) + 1,
                is_auto_capture=False,
                settings=self._settings,
                zone=zone,
            )
        except (OSError, ValueError, RuntimeError) as exc:
            self.show_error(f"Could not save original evidence: {exc}")
            return

        item.width_px, item.height_px = image.width(), image.height()
        item.source_kind = source
        item.demo_image = demo
        display_image = image
        self._detection = None
        self._last_container_check = None
        self._capture_analysis_error = None
        try:
            if not demo and self._use_khang_apple_detector():
                try:
                    precheck = self._khang_adapter.check_apple_container(
                        image, scene_condition="single_product"
                    )
                    self._last_container_check = precheck
                    if precheck.status == "MATCH":
                        self.container_advisory_label.setText(
                            f"ResNet18 Pre-Check: {precheck.predicted_label} ({precheck.confidence:.0%}) · advisory"
                        )
                    else:
                        self.container_advisory_label.setText(
                            f"▲ Advisory Pre-Check: predicted '{precheck.predicted_label}' "
                            f"({precheck.confidence:.0%}, {precheck.status}) — verify container is APPLE."
                        )
                    self.container_advisory_label.setVisible(True)
                    self._session_audit.append(
                        AuditEvent(
                            action="Container Pre-Check (ResNet18)",
                            actor=self._session.inspector,
                            role="Inspector",
                            timestamp=item.captured_at,
                            details=(
                                f"status={precheck.status}, label={precheck.predicted_label}, "
                                f"conf={precheck.confidence:.3f} (advisory)"
                            ),
                        )
                    )
                except Exception as exc:
                    self._last_container_check = None
                    self.container_advisory_label.setText(f"ResNet18 Pre-Check skipped: {exc}")
                    self.container_advisory_label.setVisible(True)

                yolo_out = self._khang_apple_engine.infer(image, track=False)
                if self._khang_apple_engine.model_path is not None:
                    item.model_file = self._khang_apple_engine.model_path.name
                item.units = [
                    DetectedUnit(box.x1, box.y1, box.width, box.height, box.label, box.confidence)
                    for box in yolo_out.boxes if box.width > 0 and box.height > 0
                ]
                self._detection = yolo_out.detection
                self.realtime_total.setText(str(yolo_out.detection.total_objects))
                display_image = draw_detections_on_qimage(
                    image,
                    yolo_out.boxes,
                    fps_text=f"Apple ONNX · {yolo_out.inference_ms:.1f} ms",
                )
            elif self._yolo_engine.is_loaded:
                yolo_out = self._yolo_engine.infer(image, track=True)
                if self._yolo_engine.model_path is not None:
                    item.model_file = self._yolo_engine.model_path.name
                item.units = [
                    DetectedUnit(box.x1, box.y1, box.width, box.height, box.label, box.confidence)
                    for box in yolo_out.boxes if box.width > 0 and box.height > 0
                ]
                if yolo_out.detection.total_objects > 0:
                    self._detection = yolo_out.detection
                    display_image = draw_detections_on_qimage(
                        image,
                        yolo_out.boxes,
                        fps_text=f"ONNX · {yolo_out.inference_ms:.1f} ms",
                    )
                else:
                    self._detection = self._fallback_detection() if item.demo_image else yolo_out.detection
            else:
                self._detection = self._fallback_detection() if item.demo_image else DetectionResult(0, {}, 0.0)
        except Exception as exc:
            self._detection = None
            item.units = []
            display_image = image.copy()
            self._capture_analysis_error = f"{type(exc).__name__}: {exc}"

        self._analysis_token += 1
        self._is_analyzing = False
        self._deep_analysis = None
        self.vlm_panel.set_idle()
        self.btn_deep.setText(tr("live.deep_btn"))
        self._evidence.append(item)
        self._images.append(display_image)
        self.evidence_strip.add_thumbnail(item, display_image)
        self._session_audit.append(
            AuditEvent(
                action=f"Evidence Captured ({zone.value.upper()})",
                actor=self._session.inspector,
                role="Inspector",
                timestamp=item.captured_at,
                details=f"SHA-256: {item.sha256[:12]}…" if item.sha256 else "In-memory capture",
            )
        )
        self._refresh_coverage_ui()
        self._advance_to_next_uncovered_zone()

        if self._capture_analysis_error is not None:
            message = (
                "Original evidence saved; detection analysis failed. "
                "Capture again before finishing."
            )
            self._session_audit.append(
                AuditEvent(
                    action="Evidence Analysis Failed",
                    actor=self._session.inspector,
                    role="Inspector",
                    timestamp=datetime.now(),
                    details=f"status=FAILED; zone={zone.value}; error={self._capture_analysis_error}",
                )
            )
            self.realtime_total.setText("—")
            self.vlm_panel.set_idle(message)
            self.deep_suggestion.setText(f"▲ {message}")
            self.deep_suggestion.setVisible(True)
            self.show_error(f"{message} {self._capture_analysis_error}")
            self._update_buttons()
            return

        low_confidence = self._detection.mean_confidence < self._session.product.min_confidence
        count_only = not self._detection.defect_classification_available
        if count_only:
            self.deep_suggestion.setText(
                "▲  Count-only Apple detector active — run Deep Analysis (Qwen-VL) / manual review for defects."
            )
        else:
            self.deep_suggestion.setText("▲  Low detection confidence — deep analysis recommended.")
        self.deep_suggestion.setVisible(low_confidence or count_only)
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
        original = load_evidence_qimage(self._evidence[-1], settings=self._settings)
        if original is None:
            self._on_cancel_deep_analysis()
            self.show_error("Original evidence is unavailable. Capture again.")
            return
        app = QApplication.instance()
        worker = vlm_client.VlmAnalysisThread(app)
        worker.analysis_completed.connect(self._on_deep_analysis_done)
        worker.finished.connect(worker.deleteLater)
        app.aboutToQuit.connect(worker.wait)
        worker.start_request(token, self._session, self._detection, original, self._settings,
                             self.scenario_combo.currentData() if self._demo else None,
                             fallback_to_mock=self._demo)

    def _on_cancel_deep_analysis(self) -> None:
        self._analysis_token += 1          # Late response is ignored (token mismatch)
        self._is_analyzing = False
        self.btn_deep.setText(tr("live.deep_btn"))
        self._update_buttons()
        if self._deep_analysis is not None:
            self.vlm_panel.set_analysis(self._deep_analysis, self._expected_label_values())
        else:
            self.vlm_panel.set_idle("Deep analysis cancelled. Press Deep Analysis to try again.")

    def _on_deep_analysis_done(self, token: int, result: VlmAnalysis) -> None:
        if token != self._analysis_token:
            return                         # Cancelled or superseded
        self._is_analyzing = False
        self.btn_deep.setText(tr("live.deep_btn"))
        self._update_buttons()
        if self._session is None or self._detection is None:
            return
        self._deep_analysis = None if result.is_error else result
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
            self.show_error(
                self._submission_model_error()
                or (
                    "Original evidence saved, but detection analysis failed. Capture again."
                    if self._capture_analysis_error
                    else "Capture at least one evidence image before finishing."
                )
            )
            return
        self._stop_camera()
        self.inspection_finished.emit(record)

    def _on_next_scanned(self) -> None:
        text = self.next_scan_field.text().strip()
        if text:
            model_error = self._submission_model_error()
            if model_error:
                self._set_operational_model_warning(model_error)
                self.show_error(model_error)
                return
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
        import_error = self._model_assignment_error(demo=False)
        capture_error = self._model_assignment_error(demo=self._is_sim_mode)
        self._set_operational_model_warning(self._operational_warning_text())
        self.btn_import.setEnabled(has_session and import_error is None)
        self.btn_capture.setEnabled(has_session and can_capture and capture_error is None)
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
        self._sync_realtime_classes()
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

    def _select_original(self) -> Optional[tuple[QImage, bytes, str]]:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Inspection Sample Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return None
        try:
            data = Path(path).read_bytes()
            buffer = QBuffer()
            buffer.setData(data)
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer)
            reader.setAutoTransform(True)
            fmt = bytes(reader.format()).decode("ascii").lower()
            image = reader.read()
            if fmt not in {"png", "jpeg", "jpg", "bmp", "webp"} or image.isNull():
                raise ValueError("Select a readable PNG, JPEG, BMP or WebP file.")
        except (OSError, ValueError) as exc:
            self.show_error(str(exc))
            return None
        return image, data, fmt

    def _import_original(self) -> None:
        if self._session is not None:
            result = self._select_original()
            if result:
                image, data, fmt = result
                self._capture_evidence(image, "imported_image", False, (data, fmt))

    def _on_browse_custom_image(self) -> None:
        result = self._select_original()
        self._custom_sim_image = None
        self._custom_original = None
        if result:
            self._custom_sim_image, data, fmt = result
            self._custom_original = (data, fmt)
        self._update_sim_frame()

    def _update_sim_frame(self) -> None:
        self._frame_token += 1
        self._sim_frame_token = self._frame_token

        scenario = self.sim_sample_combo.currentData() or "fresh"
        if scenario == "custom":
            if self._custom_sim_image is None:
                self._current_raw_sim_image = self._current_sim_image = None
                self.sim_frame_label.clear()
                return
            raw_img = self._custom_sim_image
        else:
            raw_img = self._render_raw_sim_image(scenario)
        self._current_raw_sim_image = raw_img
        self._show_sim_image(raw_img)
        self._sync_realtime_classes()
        self._submit_preview(raw_img, simulation=True)

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
        if self._yolo_engine.is_loaded and not self._model_assignment_error(demo=True):
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

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt override
        self._stop_camera()
        super().closeEvent(event)
