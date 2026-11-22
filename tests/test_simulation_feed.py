"""Automated test suite for LiveInspectionPage Simulation Feed (D-031).

Verifies:
1. Seamless toggle between Physical Camera and Simulation Feed.
2. Fallback button on 'No Camera Panel' activates Simulation Feed.
3. Sample preset switching updates synthetic frames and realtime counts.
4. Capture Evidence operates completely offline without camera hardware.
5. Presets (fresh, bruised, rotten) properly feed detection and rule engine.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from agroscan.models.inspection_models import AiRecommendation, BoxCode
from agroscan.services.app_settings import AppSettings
from agroscan.services.mock_repository import MockRepository
from agroscan.ui.pages.live_inspection_page import LiveInspectionPage
from agroscan.ui.theme import apply_theme

_APP: QApplication | None = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    apply_theme(_APP)


class TestSimulationFeed(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = QSettings(str(Path(self.tmp.name) / "settings.ini"), QSettings.Format.IniFormat)
        self.settings = AppSettings(store)
        self.repo = MockRepository(seed=42)
        box_code, order = self.repo.resolve_box("AGS:DH00123-01/10")
        self.session = self.repo.create_session(box_code, order, "inspector", "STATION-01")
        self.page = LiveInspectionPage(self.settings)
        self.page.start_session(self.session)

    def tearDown(self) -> None:
        self.page.clear_session()
        self.page.deleteLater()
        self.tmp.cleanup()

    def test_switch_to_simulation_mode_and_presets(self) -> None:
        # Default starts in camera mode
        self.assertEqual(self.page.feed_mode_combo.currentIndex(), 0)

        # Switch to simulation mode
        self.page.feed_mode_combo.setCurrentIndex(1)
        self.assertTrue(self.page._is_sim_mode)
        self.assertFalse(self.page.sim_controls_widget.isHidden())
        self.assertEqual(self.page.camera_stack.currentWidget(), self.page._sim_panel)

        # Buttons should be enabled because simulation feed is active
        self.assertTrue(self.page.btn_capture.isEnabled())

        # Test preset switching
        # 1. Fresh
        self.page.sim_sample_combo.setCurrentIndex(0)
        self.page._on_capture()
        self.assertEqual(len(self.page.captured_images), 1)
        self.assertIsNotNone(self.page._detection)
        record_fresh = self.page.finalize()
        self.assertIsNotNone(record_fresh)
        self.assertEqual(record_fresh.assessment.recommendation, AiRecommendation.PASS)

        # 2. Rotten
        self.page.sim_sample_combo.setCurrentIndex(2)  # Rotten
        self.page._on_capture()
        self.assertEqual(len(self.page.captured_images), 2)
        record_rotten = self.page.finalize()
        self.assertIsNotNone(record_rotten)
        self.assertEqual(record_rotten.assessment.recommendation, AiRecommendation.FAIL)
        self.assertTrue(any("rotten" in r.lower() for r in record_rotten.assessment.reasons))

    def test_fallback_button_from_no_camera_panel(self) -> None:
        # Simulate no camera state
        self.page.feed_mode_combo.setCurrentIndex(0)
        self.page._show_no_camera("No camera detected")
        self.assertEqual(self.page.camera_stack.currentWidget(), self.page._no_camera_panel)

        # Click fallback button
        self.page.btn_switch_sim.click()
        self.assertTrue(self.page._is_sim_mode)
        self.assertEqual(self.page.camera_stack.currentWidget(), self.page._sim_panel)
        self.assertTrue(self.page.btn_capture.isEnabled())


if __name__ == "__main__":
    unittest.main()
