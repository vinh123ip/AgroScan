# DECISIONS.md — Nhật ký quyết định của AgroScan

Chỉ ghi **quyết định đã được người dùng duyệt**. AI đọc tệp này đầu mỗi phiên; quyết định mới mâu thuẫn quyết định cũ phải chỉ ra rõ và hỏi trước khi thực hiện.

---

## Đã duyệt

| ID | Quyết định | Ngày | Ghi chú |
|---|---|---|---|
| D-001 | Ngôn ngữ chính: Python (3.13) | 10/2026 | Khớp Architecture Design v0.1 |
| D-002 | Giao diện desktop: PySide6 Widgets + QSS | 10/2026 | Khớp Architecture Design v0.1 |
| D-003 | Thị giác máy tính: YOLOv8 ONNX chạy cục bộ trên máy trạm (`onnxruntime`) | 10/2026 | Tránh phụ thuộc PyTorch nặng khi đóng gói |
| D-004 | Mô hình ngôn ngữ-thị giác: Qwen-VL chạy cục bộ/LAN qua HTTP REST | 10/2026 | Bridge `server/qwen_service.py` ↔ LM Studio |
| D-005 | Ưu tiên hoạt động ngoại tuyến, không dùng API AI trực tuyến bên ngoài | 10/2026 | Thêm API cloud cần duyệt riêng |
| D-006 | Môi trường mục tiêu: Windows 10/11 | 10/2026 | Kèm launcher `run.py` tự nhận diện `.venv` |
| D-007 | YOLO (đếm/định vị) + Qwen-VL (phân tích sâu theo yêu cầu) + Python (quyết định nghiệp vụ) | 01/11/2026 | Không thêm AI model thứ 3 |
| D-008 | Lưu ảnh gốc tách biệt và không ghi đè; bảo vệ toàn vẹn bằng SHA-256 | 01/11/2026 | Tính SHA-256 trên byte gốc trước khi vẽ overlay |
| D-009 | LangChain là tùy chọn, chỉ dùng khi có lợi ích kiến trúc rõ ràng | 10/2026 | Hiện chưa cần kích hoạt |
| D-010 | Báo cáo xuất PDF (`reportlab`) và Excel 3-sheet (`openpyxl`) | 10/2026 | Đồng bộ bộ lọc giữa PDF và Excel |
| D-011 | Chat với người dùng bằng tiếng Việt; mã nguồn, comment, docstring, commit bằng tiếng Anh | 29/10/2026 | |
| D-012 | Công cụ AI hỗ trợ: Google Antigravity / Claude Code với bộ quy tắc trong `Prompt, Mindset, Rule/` | 29/10/2026 | |
| D-013 | Xuất báo cáo PDF/Excel và dữ liệu khóa manifest dùng **tiếng Anh** | 29/10/2026 | Cập nhật song ngữ UI ở `D-035` |
| D-014 | Cơ sở dữ liệu chính: **PostgreSQL 18** (`agroscan_dev`, schema `agroscan` v1.2) | 01/11/2026 | Fallback `MockRepository` khi chạy `--demo` |
| D-015 | **Luồng 12 bước là hướng chính của dự án** | 29/10/2026 | |
| D-016 | **Phân vai 2 máy qua LAN:** Server (PC RTX 3060: PostgreSQL, Qwen-VL, SMB/storage) & Workstation (Laptop GTX 1650 Ti: PySide6, Camera, YOLO ONNX, QR Scanner) | 01/11/2026 | Chạy 1 máy qua `127.0.0.1` khi demo |
| D-017 | **Dịch vụ Qwen-VL:** HTTP REST nội bộ (`POST /api/v1/vlm/analyze` hoặc `/v1/chat/completions`), có timeout và không bịa kết quả khi tắt model ở chế độ vận hành | 01/11/2026 | Chỉ gọi khi nhấn nút Deep Analysis |
| D-018 | **Lưu trữ ảnh:** Hỗ trợ đường dẫn SMB share hoặc thư mục cục bộ (`storage_service.py`), DB chỉ lưu `object_key` tương đối + `sha256` | 01/11/2026 | |
| D-019 | **Định danh thùng:** `1 mã = 1 hộp = 1 phiên`, hỗ trợ cả định dạng `AGS:<Mã_Đơn>-<Số_Hộp>/<Tổng>` và UUID `scan_token` | 01/11/2026 | Có bộ sinh nhãn QR ISO/IEC 18004 (`qr_encoder.py`) |
| D-020 | **Quét liên tục (Non-blocking):** Quét mã hộp mới trong lúc đang kiểm hộp hiện tại | 01/11/2026 | |
| D-021 | **Tái kiểm & Khóa mở trùng:** Tái kiểm tạo attempt kế tiếp (`previous_id`), mỗi thùng chỉ có tối đa 1 attempt mở tại 1 thời điểm | 01/11/2026 | |
| D-022 | **Tổng hợp cấp lô/đơn hàng:** Mỗi thùng/slot có kết quả riêng; Dashboard hiển thị tiến độ theo vị trí hiệu lực (`current_selections`) | 01/11/2026 | |
| D-023 | **Rule Engine (`rule_engine.py`):** Đọc ngưỡng từ DB theo profile sản phẩm (`gt`/`ge` và cờ loại trừ `exclusion`). Thứ tự ưu tiên `FAIL > NEEDS_REVIEW > PASS` | 01/11/2026 | Không hardcode ngưỡng trong code |
| D-024 | **Model YOLO chuyên hóa theo sản phẩm** (`fruit_defect.onnx`, `banana_defect.onnx`, `apple_defect.onnx`, `mango_defect.onnx`) | 01/11/2026 | Nạp qua `YoloEngine.load_for_product()` |
| D-025 | **Tracking chống đếm trùng:** `CentroidTracker` gắn `track_id` ổn định trên preview | 01/11/2026 | |
| D-026 | **Realtime vs Chính thức:** Video realtime chỉ để tham khảo; số liệu chính thức chỉ tính từ ảnh tĩnh (`is_count_image = true`) có SHA-256 | 01/11/2026 | |
| D-027 | **Phân quyền RBAC 4 vai trò (`Admin`, `Inspector`, `Reviewer`, `Manager`)** với đăng nhập PostgreSQL (`scrypt`/`pbkdf2`) hoặc Demo RAM | 01/11/2026 | Reviewer là inspector đang hoạt động có `can_review = true` |
| D-028 | **Settings Page:** Cấu hình IP PostgreSQL, URL Qwen-VL, đường dẫn lưu ảnh, thiết bị camera kèm kiểm tra kết nối nền | 01/11/2026 | Đọc ưu tiên env -> `.env` -> `AppSettings` |
| D-029 | **Nhập dữ liệu (`DataImportPage`):** Nhập đơn hàng & danh sách thùng từ CSV/XLSX trong cùng transaction DB | 01/11/2026 | Validate từng dòng và hiển thị preview trước khi commit |
| D-030 | **Chuẩn hóa trạng thái:** `SessionStatus` (`IN_PROGRESS`, `PENDING_REVIEW`, `COMPLETED`), `AiRecommendation` (`PASS`, `FAIL`, `NEEDS_REVIEW`), `ReviewerDecision` (`PASS`, `FAIL`, `RE_INSPECT`) | 01/11/2026 | Map trực tiếp với trạng thái SQL `draft`, `submitted`, `reviewed`, `reinspect` |
| D-031 | **Nguồn ảnh kép:** Live Camera (`QCamera`), Import Original (`imported_image`) và Simulation Feed (`demo_image = true`) | 01/11/2026 | Chế độ vận hành chặn ảnh demo nếu profile không phải scope `demo` |
| D-032 | **Dynamic Role-based UI:** Sidebar tự ẩn hoàn toàn các trang không có quyền và không khởi tạo trang bị cấm | 01/11/2026 | |
| D-033 | **Chuẩn hóa Database Design v1.2:** 15 bảng, 19 khóa ngoại, 3 views (`current_selections`, `latest_lot_decisions`, `box_rule_counts`) và 5 lô fixture `DEMO-V12-01` → `DEMO-V12-05` trong `scripts/db_v1_2/` | 25/11/2026 | Khớp `06 C2SE.07_Database_Design_AgroScan_ver1.2.docx` |
| D-034 | **Độ phủ toàn thùng & Tách thay thùng vs Tái kiểm:** Nộp phiên bắt buộc xác nhận `whole_box_confirmed` và có ảnh đếm phát hiện vật thể; thay thùng lưu ở `sample_selections.replaces_id`, tái kiểm lưu ở `inspections.previous_id` | 25/11/2026 | |
| D-035 | **Giao diện song ngữ EN / VI (`i18n.py`) & Xuất báo cáo tiếng Anh:** Cho phép chuyển đổi EN/VI trực tiếp giữa phiên làm việc mà không mất dữ liệu đang nhập; Excel/PDF luôn xuất cột kết quả chuẩn tiếng Anh | 25/11/2026 | |
| D-036 | **Maker-Checker độc lập & Hồ sơ ký bất biến:** Người nộp thùng không thể tự duyệt thùng đó; `add_attributed_note` chỉ ghi thêm vào `audit_logs` mà không thay đổi `lot_decisions.manifest_bytes` hay chữ ký RSA-PSS/SHA-256 | 25/11/2026 | |
| D-037 | **Tài liệu tập trung duy nhất:** Hợp nhất toàn bộ hướng dẫn cài đặt, DB v1.2, test thủ công/tự động và kịch bản demo về `docs/HUONG_DAN_KIEM_THU.md`; nhánh phát triển duy trì song song `main` và `develop` trên `origin` | 26/11/2026 | |

---

## Mẫu thêm quyết định mới

```markdown
| D-0XX | <quyết định> | <ngày> | <lý do ngắn, ảnh hưởng> |
```
