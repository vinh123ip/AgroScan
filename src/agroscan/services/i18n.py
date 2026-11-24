"""Bilingual Internationalization (i18n) Service — English & Vietnamese (3.4.5.2).

Provides instant, zero-restart EN <-> VI switching across all AgroScan desktop screens
via a central ``LanguageManager`` Qt signal (``language_changed``).
Defaults to English (``"en"``) to preserve backward compatibility with all existing specs.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en", "English (EN)"),
    ("vi", "Tiếng Việt (VI)"),
)

_TRANSLATIONS: dict[str, dict[str, str]] = {
    # Navigation & Sections
    "nav.section.OPERATIONS": {"en": "OPERATIONS", "vi": "VẬN HÀNH"},
    "nav.section.RECORDS": {"en": "RECORDS", "vi": "HỒ SƠ & BÁO CÁO"},
    "nav.section.ADMINISTRATION": {"en": "ADMINISTRATION", "vi": "QUẢN TRỊ"},
    "nav.page.dashboard": {"en": "Dashboard", "vi": "Tổng quan"},
    "nav.page.box_intake": {"en": "Box Intake", "vi": "Tiếp nhận hộp"},
    "nav.page.review_queue": {"en": "Review Queue", "vi": "Hàng đợi duyệt"},
    "nav.page.inspection_history": {"en": "Inspection History", "vi": "Lịch sử kiểm định"},
    "nav.page.reports": {"en": "Reports", "vi": "Báo cáo"},
    "nav.page.data_import": {"en": "Data Import", "vi": "Nhập dữ liệu"},
    "nav.page.catalog": {"en": "Catalog & Criteria", "vi": "Danh mục & Tiêu chí"},
    "nav.page.users": {"en": "Users", "vi": "Người dùng"},
    "nav.page.settings": {"en": "Settings", "vi": "Cài đặt"},
    "nav.page.live_inspection": {"en": "Live Inspection", "vi": "Kiểm định trực tiếp"},
    "nav.page.assessment_result": {"en": "Assessment Result", "vi": "Kết quả đánh giá"},

    # Header & Global
    "header.brand_subtitle": {"en": "INSPECTION WORKSTATION", "vi": "TRẠM KIỂM ĐỊNH NÔNG SẢN"},
    "header.session_active": {"en": "●  SESSION ACTIVE", "vi": "●  PHIÊN HOẠT ĐỘNG"},
    "header.session_expired": {"en": "✖  SESSION EXPIRED", "vi": "✖  PHIÊN HẾT HẠN"},
    "header.logout": {"en": "Logout", "vi": "Đăng xuất"},
    "header.language_tooltip": {"en": "Switch display language (English / Vietnamese)", "vi": "Chuyển ngôn ngữ hiển thị (Tiếng Anh / Tiếng Việt)"},

    # Domain Enum Labels
    "status.In Progress": {"en": "In Progress", "vi": "Đang kiểm định"},
    "status.Pending Review": {"en": "Pending Review", "vi": "Chờ phê duyệt"},
    "status.Completed": {"en": "Completed", "vi": "Hoàn tất"},
    "decision.Pass": {"en": "Pass", "vi": "Đạt chuẩn"},
    "decision.Fail": {"en": "Fail", "vi": "Không đạt"},
    "decision.Re-inspect": {"en": "Re-inspect", "vi": "Kiểm tra lại"},
    "rec.Pass": {"en": "Pass", "vi": "Đạt"},
    "rec.Fail": {"en": "Fail", "vi": "Lỗi"},
    "rec.Needs Review": {"en": "Needs Review", "vi": "Cần kiểm duyệt"},
    "role.Admin": {"en": "Admin", "vi": "Quản trị viên"},
    "role.Inspector": {"en": "Inspector", "vi": "Kiểm định viên"},
    "role.Reviewer": {"en": "Reviewer", "vi": "Người phê duyệt"},

    # Box Zones (Whole-Box Coverage)
    "zone.top": {"en": "Top Surface", "vi": "Mặt trên"},
    "zone.left": {"en": "Left Side", "vi": "Mặt trái"},
    "zone.right": {"en": "Right Side", "vi": "Mặt phải"},
    "zone.bottom": {"en": "Bottom", "vi": "Mặt đáy"},
    "zone.inner": {"en": "Inner Layer", "vi": "Lớp trong"},
    "zone.short.top": {"en": "Top", "vi": "Trên"},
    "zone.short.left": {"en": "Left", "vi": "Trái"},
    "zone.short.right": {"en": "Right", "vi": "Phải"},
    "zone.short.bottom": {"en": "Bottom", "vi": "Đáy"},
    "zone.short.inner": {"en": "Inner", "vi": "Trong"},

    # Dashboard (3.4.5.2)
    "dashboard.title": {"en": "Dashboard", "vi": "Bảng điều khiển"},
    "dashboard.subtitle": {
        "en": "Bilingual order progress, review status breakdown, and recent inspection activity.",
        "vi": "Tiến độ đơn hàng song ngữ, trạng thái kiểm duyệt và hoạt động kiểm định gần đây.",
    },
    "dashboard.kpi.today": {"en": "BOXES INSPECTED TODAY", "vi": "HỘP KIỂM ĐỊNH HÔM NAY"},
    "dashboard.kpi.today_note": {"en": "{total} in total", "vi": "Tổng cộng {total} phiên"},
    "dashboard.kpi.pending": {"en": "PENDING REVIEW", "vi": "CHỜ PHÊ DUYỆT"},
    "dashboard.kpi.pending_note": {"en": "Awaiting reviewer · {reinspect} re-inspect", "vi": "Chờ duyệt · {reinspect} kiểm tra lại"},
    "dashboard.kpi.passed": {"en": "PASSED", "vi": "ĐẠT CHUẨN"},
    "dashboard.kpi.failed": {"en": "FAILED", "vi": "KHÔNG ĐẠT"},
    "dashboard.kpi.confirmed": {"en": "Confirmed by reviewer", "vi": "Đã xác nhận bởi người duyệt"},
    "dashboard.review_status_section": {"en": "Review Status Breakdown", "vi": "Phân bổ Trạng thái Kiểm duyệt"},
    "dashboard.review_status.pending": {"en": "Pending First Review: {n}", "vi": "Chờ duyệt lần đầu: {n}"},
    "dashboard.review_status.reinspect": {"en": "Re-inspect Required: {n}", "vi": "Yêu cầu kiểm tra lại: {n}"},
    "dashboard.review_status.passed": {"en": "Approved (Pass): {n}", "vi": "Đã duyệt Đạt: {n}"},
    "dashboard.review_status.failed": {"en": "Rejected (Fail): {n}", "vi": "Đã từ chối (Lỗi): {n}"},
    "dashboard.order_progress_section": {"en": "Order Progress & Review Status", "vi": "Tiến độ Đơn hàng & Trạng thái Duyệt"},
    "dashboard.recent_section": {"en": "Recent Activity", "vi": "Hoạt động Gần đây"},
    "dashboard.col.order": {"en": "Order", "vi": "Mã đơn"},
    "dashboard.col.product": {"en": "Product", "vi": "Sản phẩm"},
    "dashboard.col.supplier": {"en": "Supplier", "vi": "Nhà cung cấp"},
    "dashboard.col.progress": {"en": "Progress", "vi": "Tiến độ"},
    "dashboard.col.passed": {"en": "Passed", "vi": "Đạt"},
    "dashboard.col.failed": {"en": "Failed", "vi": "Lỗi"},
    "dashboard.col.pending": {"en": "Pending", "vi": "Chờ duyệt"},
    "dashboard.col.reinspect": {"en": "Re-inspect", "vi": "Kiểm tra lại"},
    "dashboard.col.remaining": {"en": "Remaining", "vi": "Chưa kiểm"},
    "dashboard.col.completion": {"en": "Completion", "vi": "Hoàn thành"},
    "dashboard.col.session": {"en": "Session", "vi": "Mã phiên"},
    "dashboard.col.box": {"en": "Box", "vi": "Mã hộp"},
    "dashboard.col.status": {"en": "Status", "vi": "Trạng thái"},
    "dashboard.col.result": {"en": "Result", "vi": "Kết quả"},
    "dashboard.col.started": {"en": "Started", "vi": "Bắt đầu"},

    # Live Inspection & Whole-Box Coverage (3.4.5.1)
    "live.title": {"en": "Live Inspection", "vi": "Kiểm định trực tiếp"},
    "live.coverage.title": {"en": "Whole-Box Coverage", "vi": "Độ phủ toàn bộ hộp"},
    "live.coverage.active_side": {"en": "Capture Side:", "vi": "Góc chụp:"},
    "live.coverage.auto_advance": {"en": "Auto-advance side", "vi": "Tự chuyển góc tiếp"},
    "live.coverage.complete": {"en": "✔  100% Complete ({covered}/{total} required sides)", "vi": "✔  Hoàn tất 100% ({covered}/{total} mặt bắt buộc)"},
    "live.coverage.incomplete": {"en": "{pct}% Covered ({covered}/{total} required) — Missing: {missing}", "vi": "Đã phủ {pct}% ({covered}/{total} mặt bắt buộc) — Thiếu: {missing}"},
    "live.capture_btn": {"en": "●  Capture Evidence (F5)", "vi": "●  Chụp bằng chứng (F5)"},
    "live.deep_btn": {"en": "Deep Analysis (Qwen-VL)", "vi": "Phân tích sâu (Qwen-VL)"},
    "live.finish_btn": {"en": "Finish Inspection  →", "vi": "Hoàn tất kiểm định  →"},
    "live.discard_btn": {"en": "Discard Session", "vi": "Hủy phiên"},
    "live.incomplete_dialog.title": {"en": "Incomplete Box Coverage", "vi": "Chưa chụp đủ các mặt của hộp"},
    "live.incomplete_dialog.body": {
        "en": "Whole-box coverage is {pct}% ({covered}/{total} required surfaces).\nMissing side(s): {missing}.\n\nContinue and finish inspection anyway?",
        "vi": "Độ phủ toàn hộp hiện đạt {pct}% ({covered}/{total} mặt bắt buộc).\nCòn thiếu mặt: {missing}.\n\nBạn vẫn muốn tiếp tục hoàn tất phiên kiểm định?",
    },

    # Review Queue (3.4.4.2 / 3.4.6.2)
    "review.title": {"en": "Review Queue", "vi": "Hàng đợi phê duyệt"},
    "review.subtitle": {
        "en": "Sessions waiting for a reviewer decision. Oldest first. Shortcuts: Ctrl+1 Pass · Ctrl+2 Fail · Ctrl+3 Re-inspect.",
        "vi": "Các phiên đang chờ người kiểm duyệt xác nhận (cũ nhất trước). Phím tắt: Ctrl+1 Đạt · Ctrl+2 Lỗi · Ctrl+3 Kiểm lại.",
    },
    "review.pending_count": {"en": "{n} PENDING", "vi": "{n} CHỜ DUYỆT"},
    "review.empty": {"en": "Select a session from the queue to review it.", "vi": "Chọn một phiên trong danh sách để kiểm duyệt."},
    "review.decision_card": {"en": "Your Decision", "vi": "Quyết định phê duyệt"},
    "review.notes_placeholder": {"en": "Optional notes about your decision…", "vi": "Ghi chú thêm về quyết định phê duyệt…"},

    # History Explorer, Versioned History, Audit Detail & Attributed Notes (3.4.5.9)
    "history.title": {"en": "Inspection History", "vi": "Lịch sử kiểm định"},
    "history.subtitle": {
        "en": "Explore versioned box inspections, audit timelines, attributed notes, and PDF certificates.",
        "vi": "Tra cứu lịch sử phiên bản kiểm định theo hộp, nhật ký kiểm toán, ghi chú định danh và xuất biên bản PDF.",
    },
    "history.filter_card": {"en": "Search & Filter", "vi": "Tìm kiếm & Bộ lọc"},
    "history.search_placeholder": {
        "en": "Search by Box Code (e.g. AGS:DH00123-01/10) or Session ID…",
        "vi": "Tìm theo Mã hộp (VD: AGS:DH00123-01/10) hoặc Mã phiên…",
    },
    "history.all_products": {"en": "All Products", "vi": "Tất cả sản phẩm"},
    "history.all_statuses": {"en": "All Statuses", "vi": "Tất cả trạng thái"},
    "history.all_outcomes": {"en": "All Outcomes", "vi": "Tất cả kết quả"},
    "history.view.all": {"en": "All Versions", "vi": "Mọi phiên bản"},
    "history.view.grouped": {"en": "Latest per Box", "vi": "Nhóm theo Hộp"},
    "history.date_filter": {"en": "Date range", "vi": "Lọc ngày"},
    "history.reset": {"en": "Reset", "vi": "Đặt lại"},
    "history.export_cert": {"en": "📄  Export Certificate PDF", "vi": "📄  Xuất biên bản PDF"},
    "history.count_found": {"en": "{n} SESSIONS FOUND ({boxes} BOXES)", "vi": "TÌM THẤY {n} PHIÊN ({boxes} HỘP)"},
    "history.empty": {"en": "Select an inspection session from the table to view full details.", "vi": "Chọn một phiên kiểm định trong bảng để xem chi tiết."},
    "history.col.ver": {"en": "Ver", "vi": "Phiên bản"},
    "history.col.session": {"en": "Session ID", "vi": "Mã phiên"},
    "history.col.box": {"en": "Box Code", "vi": "Mã hộp"},
    "history.col.product": {"en": "Product", "vi": "Sản phẩm"},
    "history.col.status": {"en": "Status", "vi": "Trạng thái"},
    "history.col.outcome": {"en": "Outcome", "vi": "Kết quả"},
    "history.col.started": {"en": "Started", "vi": "Thời gian"},

    # Record Detail (Versions, Audit, Attributed Notes)
    "detail.session": {"en": "Session", "vi": "Thông tin phiên"},
    "detail.versions": {"en": "Box Version History", "vi": "Lịch sử phiên bản của hộp"},
    "detail.versions_diff": {"en": "Comparison vs previous version ({prev} → {curr}): {diff}", "vi": "So sánh với phiên bản trước ({prev} → {curr}): {diff}"},
    "detail.ai_rec": {"en": "AI Recommendation", "vi": "Đề xuất của AI"},
    "detail.detection": {"en": "Detection on Evidence Image", "vi": "Nhận diện trên ảnh bằng chứng"},
    "detail.deep_analysis": {"en": "Deep Analysis (Qwen-VL)", "vi": "Phân tích chuyên sâu (Qwen-VL)"},
    "detail.evidence": {"en": "Evidence Images", "vi": "Ảnh tĩnh bằng chứng"},
    "detail.review": {"en": "Reviewer Decision", "vi": "Quyết định kiểm duyệt"},
    "detail.audit": {"en": "Audit Detail (Event Timeline)", "vi": "Nhật ký kiểm toán (Audit Trail)"},
    "detail.notes": {"en": "Attributed Notes", "vi": "Ghi chú định danh (Attributed Notes)"},
    "detail.notes_placeholder": {"en": "Add an attributed note to this session…", "vi": "Thêm ghi chú mới gắn tên bạn vào phiên này…"},
    "detail.notes_add": {"en": "+  Add Note", "vi": "+  Thêm ghi chú"},
    "detail.notes_empty": {"en": "No attributed notes recorded yet.", "vi": "Chưa có ghi chú nào cho phiên này."},

    # Settings
    "settings.title": {"en": "Settings", "vi": "Cài đặt hệ thống"},
    "settings.subtitle": {
        "en": "Server addresses, AI service, image storage, camera and display language for this workstation.",
        "vi": "Địa chỉ máy chủ, dịch vụ AI, kho lưu ảnh, camera và ngôn ngữ hiển thị cho trạm làm việc.",
    },
    "settings.language_label": {"en": "Display Language", "vi": "Ngôn ngữ hiển thị"},
    "settings.save": {"en": "Save Settings", "vi": "Lưu cài đặt"},
    "settings.revert": {"en": "Revert", "vi": "Hoàn tác"},
    "settings.test_all": {"en": "Test All", "vi": "Kiểm tra tất cả"},
}


class LanguageManager(QObject):
    """Observable singleton managing active UI language (``'en'`` or ``'vi'``)."""

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang: str = "en"

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str) -> str:
        normalized = "vi" if str(lang).strip().lower().startswith("vi") else "en"
        if normalized != self._lang:
            self._lang = normalized
            self.language_changed.emit(self._lang)
        return self._lang

    def toggle_language(self) -> str:
        return self.set_language("vi" if self._lang == "en" else "en")


_MANAGER: Optional[LanguageManager] = None


def language_manager() -> LanguageManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = LanguageManager()
    return _MANAGER


def get_language() -> str:
    return language_manager().language


def set_language(lang: str) -> str:
    return language_manager().set_language(lang)


def tr(key: str, lang: Optional[str] = None, **kwargs: object) -> str:
    """Translate ``key`` into the active language (or explicit ``lang``)."""
    active = lang or get_language()
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key
    template = entry.get(active) or entry.get("en") or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


def translate_enum_value(prefix: str, value: str, lang: Optional[str] = None) -> str:
    key = f"{prefix}.{value}"
    translated = tr(key, lang=lang)
    return value if translated == key else translated

