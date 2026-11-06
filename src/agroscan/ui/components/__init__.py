"""Reusable UI components for AgroScan.

All components are self-contained QWidget subclasses with no business
logic — they only handle presentation and emit signals for parent pages
to handle.
"""

from agroscan.ui.components.loading_screen import LoadingScreen
from agroscan.ui.components.qr_label_dialog import QrCodeWidget, QrLabelDialog
from agroscan.ui.components.stat_card_widget import StatCardWidget
from agroscan.ui.components.vlm_result_panel import VlmResultPanel

__all__ = [
    "LoadingScreen",
    "QrCodeWidget",
    "QrLabelDialog",
    "StatCardWidget",
    "VlmResultPanel",
]
