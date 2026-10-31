"""DEPRECATED — superseded by ``box_intake_page.BoxIntakePage``.

The former ``NewInspectionPage`` (manual session form, M2.1) depended on the
removed ``CommodityType`` enum. Box intake now works by scanning the box QR
code (D-019) and opening the camera-first Live Inspection page (D-031).

The original implementation is preserved in Git history (commit 8bbd8f7).
This module intentionally defines no page so stale imports fail loudly with
a clear message instead of a confusing ``CommodityType`` error.
"""


def __getattr__(name: str):
    if name == "NewInspectionPage":
        raise ImportError(
            "NewInspectionPage was removed; use agroscan.ui.pages.box_intake_page.BoxIntakePage."
        )
    raise AttributeError(name)
